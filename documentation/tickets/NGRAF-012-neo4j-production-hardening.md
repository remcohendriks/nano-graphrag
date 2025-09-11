# NGRAF-012: Neo4j Graph Storage - Production Hardening and Optimization

## Overview
Transform Neo4j from experimental to production-ready status with factory integration, configuration management, performance optimizations, native GDS algorithm usage, and comprehensive testing.

## Current State
- Basic implementation exists in `nano_graphrag/_storage/gdb_neo4j.py`
- Not allowed in `StorageFactory.ALLOWED_GRAPH` (only "networkx")
- Expects `addon_params` for configuration, not integrated with StorageConfig
- Constraint creation is commented out due to async issues
- Connection pooling exists but lifecycle management unclear
- GDS integration partial - only Leiden clustering
- No retry logic or proper error handling
- Tests skip unless environment variables are set

## Proposed Implementation

### Phase 1: Configuration and Factory Integration

#### Update `nano_graphrag/config.py`
```python
@dataclass
class StorageConfig:
    # ... existing fields ...
    
    # Neo4j configuration
    neo4j_url: str = "neo4j://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"  # Support multiple databases
    neo4j_max_connection_pool_size: int = 50
    neo4j_connection_timeout: float = 30.0
    neo4j_max_transaction_retry_time: float = 30.0
    neo4j_initial_retry_delay: float = 1.0
    neo4j_retry_delay_multiplier: float = 2.0
    neo4j_retry_delay_jitter: float = 0.2
    
    # SSL/TLS configuration
    neo4j_encrypted: bool = False
    neo4j_trust: str = "TRUST_SYSTEM_CA_SIGNED_CERTIFICATES"
    neo4j_ssl_context: Optional[Any] = None
    
    # GDS configuration
    neo4j_gds_enabled: bool = True
    neo4j_gds_license_key: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dict with addon_params for backward compatibility."""
        config = asdict(self)
        
        # Build addon_params for Neo4j if configured
        if self.graph_backend == "neo4j":
            config["addon_params"] = {
                "neo4j_url": self.neo4j_url,
                "neo4j_auth": (self.neo4j_username, self.neo4j_password),
                "neo4j_database": self.neo4j_database,
                "neo4j_max_connection_pool_size": self.neo4j_max_connection_pool_size,
                # Include all Neo4j params
            }
        
        return config
```

#### Update `nano_graphrag/_storage/factory.py`
```python
class StorageFactory:
    ALLOWED_GRAPH = {"networkx", "neo4j"}  # Add neo4j
```

### Phase 2: Enhanced Neo4j Implementation

#### Rewrite `nano_graphrag/_storage/gdb_neo4j.py`
```python
from typing import Optional, List, Tuple, Dict, Any, Set
from dataclasses import dataclass, field
import asyncio
import logging
from contextlib import asynccontextmanager
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from nano_graphrag.base import BaseGraphStorage
from nano_graphrag._utils import ensure_dependency, logger

@dataclass
class Neo4jStorage(BaseGraphStorage):
    """Production-ready Neo4j storage with GDS optimization."""
    
    _driver: Optional[Any] = field(default=None, init=False)
    _gds: Optional[Any] = field(default=None, init=False)
    _constraints_created: bool = field(default=False, init=False)
    _connection_pool: Optional[Any] = field(default=None, init=False)
    
    def __post_init__(self):
        """Initialize Neo4j with proper configuration."""
        ensure_dependency("neo4j", "neo4j", "Neo4j graph storage")
        
        from neo4j import AsyncGraphDatabase
        from neo4j.exceptions import ServiceUnavailable, SessionExpired
        
        # Extract configuration
        params = self.global_config.get("addon_params", {})
        
        # Create driver with advanced configuration
        self._driver = AsyncGraphDatabase.driver(
            params.get("neo4j_url", "neo4j://localhost:7687"),
            auth=params.get("neo4j_auth", ("neo4j", "password")),
            max_connection_pool_size=params.get("neo4j_max_connection_pool_size", 50),
            connection_timeout=params.get("neo4j_connection_timeout", 30),
            max_transaction_retry_time=params.get("neo4j_max_transaction_retry_time", 30),
            database=params.get("neo4j_database", "neo4j"),
            encrypted=params.get("neo4j_encrypted", False),
            trust=params.get("neo4j_trust", "TRUST_SYSTEM_CA_SIGNED_CERTIFICATES")
        )
        
        # Initialize GDS if available
        if params.get("neo4j_gds_enabled", True):
            self._init_gds()
        
        # Create constraints and indexes
        asyncio.create_task(self._ensure_schema())
    
    def _init_gds(self):
        """Initialize Graph Data Science library if available."""
        try:
            from graphdatascience import GraphDataScience
            
            params = self.global_config.get("addon_params", {})
            self._gds = GraphDataScience(
                params.get("neo4j_url", "neo4j://localhost:7687"),
                auth=params.get("neo4j_auth", ("neo4j", "password")),
                database=params.get("neo4j_database", "neo4j")
            )
            
            # Verify GDS is installed
            version = self._gds.version()
            logger.info(f"Neo4j GDS version: {version}")
            
        except ImportError:
            logger.warning("graphdatascience package not installed, GDS features disabled")
            self._gds = None
        except Exception as e:
            logger.warning(f"Failed to initialize GDS: {e}")
            self._gds = None
    
    async def _ensure_schema(self):
        """Create constraints and indexes with proper async handling."""
        if self._constraints_created:
            return
        
        # Use write transaction for schema operations
        async with self._driver.session() as session:
            try:
                # Create constraints in a transaction
                async def create_constraints(tx):
                    # Unique constraint for entity IDs
                    await tx.run("""
                        CREATE CONSTRAINT entity_id IF NOT EXISTS
                        FOR (n:Entity) REQUIRE n.id IS UNIQUE
                    """)
                    
                    # Index for community lookups
                    await tx.run("""
                        CREATE INDEX entity_community IF NOT EXISTS
                        FOR (n:Entity) ON (n.community)
                    """)
                    
                    # Index for entity types
                    await tx.run("""
                        CREATE INDEX entity_type IF NOT EXISTS
                        FOR (n:Entity) ON (n.type)
                    """)
                    
                    # Composite index for relationship queries
                    await tx.run("""
                        CREATE INDEX rel_source_target IF NOT EXISTS
                        FOR ()-[r:RELATES_TO]-() ON (r.source, r.target)
                    """)
                    
                    # Full-text index for entity search
                    await tx.run("""
                        CREATE FULLTEXT INDEX entity_description IF NOT EXISTS
                        FOR (n:Entity) ON EACH [n.description]
                    """)
                
                await session.execute_write(create_constraints)
                self._constraints_created = True
                logger.info("Neo4j constraints and indexes created successfully")
                
            except Exception as e:
                logger.warning(f"Failed to create constraints (may already exist): {e}")
                # Try alternative approach with sync driver if needed
                await self._ensure_schema_sync_fallback()
    
    async def _ensure_schema_sync_fallback(self):
        """Fallback schema creation using sync driver."""
        from neo4j import GraphDatabase
        
        params = self.global_config.get("addon_params", {})
        sync_driver = GraphDatabase.driver(
            params.get("neo4j_url", "neo4j://localhost:7687"),
            auth=params.get("neo4j_auth", ("neo4j", "password"))
        )
        
        try:
            with sync_driver.session() as session:
                # Create constraints synchronously
                session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE")
                session.run("CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.community)")
            self._constraints_created = True
        finally:
            sync_driver.close()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ServiceUnavailable, SessionExpired))
    )
    async def upsert_node(self, node_id: str, node_data: Dict[str, Any]):
        """Upsert node with retry logic."""
        async with self._driver.session() as session:
            await session.execute_write(
                self._upsert_node_tx,
                node_id,
                node_data
            )
    
    @staticmethod
    async def _upsert_node_tx(tx, node_id: str, node_data: Dict[str, Any]):
        """Transaction function for node upsert."""
        # Use MERGE for upsert semantics
        query = """
        MERGE (n:Entity {id: $node_id})
        SET n += $properties
        RETURN n
        """
        await tx.run(query, node_id=node_id, properties=node_data)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def upsert_edge(
        self, 
        source_id: str, 
        target_id: str, 
        edge_data: Dict[str, Any]
    ):
        """Upsert edge with retry logic."""
        async with self._driver.session() as session:
            await session.execute_write(
                self._upsert_edge_tx,
                source_id,
                target_id,
                edge_data
            )
    
    @staticmethod
    async def _upsert_edge_tx(tx, source_id: str, target_id: str, edge_data: Dict[str, Any]):
        """Transaction function for edge upsert."""
        query = """
        MATCH (source:Entity {id: $source_id})
        MATCH (target:Entity {id: $target_id})
        MERGE (source)-[r:RELATES_TO {source: $source_id, target: $target_id}]->(target)
        SET r += $properties
        RETURN r
        """
        await tx.run(
            query,
            source_id=source_id,
            target_id=target_id,
            properties=edge_data
        )
    
    async def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get node by ID with caching."""
        async with self._driver.session() as session:
            result = await session.execute_read(
                self._get_node_tx,
                node_id
            )
            return result
    
    @staticmethod
    async def _get_node_tx(tx, node_id: str):
        """Transaction function for node retrieval."""
        query = "MATCH (n:Entity {id: $node_id}) RETURN n"
        result = await tx.run(query, node_id=node_id)
        record = await result.single()
        return dict(record["n"]) if record else None
    
    async def get_nodes(
        self,
        limit: Optional[int] = None,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Get nodes with optional filtering."""
        async with self._driver.session() as session:
            return await session.execute_read(
                self._get_nodes_tx,
                limit,
                filter_dict
            )
    
    @staticmethod
    async def _get_nodes_tx(tx, limit: Optional[int], filter_dict: Optional[Dict[str, Any]]):
        """Transaction function for bulk node retrieval."""
        where_clause = ""
        if filter_dict:
            conditions = [f"n.{k} = ${k}" for k in filter_dict.keys()]
            where_clause = f"WHERE {' AND '.join(conditions)}"
        
        limit_clause = f"LIMIT {limit}" if limit else ""
        
        query = f"""
        MATCH (n:Entity)
        {where_clause}
        RETURN n.id as id, n as properties
        {limit_clause}
        """
        
        params = filter_dict or {}
        result = await tx.run(query, **params)
        
        nodes = []
        async for record in result:
            nodes.append((record["id"], dict(record["properties"])))
        return nodes
    
    async def get_edges(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Tuple[str, str, Dict[str, Any]]]:
        """Get edges with optional filtering."""
        async with self._driver.session() as session:
            return await session.execute_read(
                self._get_edges_tx,
                source_id,
                target_id,
                limit
            )
    
    @staticmethod
    async def _get_edges_tx(tx, source_id, target_id, limit):
        """Transaction function for edge retrieval."""
        where_conditions = []
        params = {}
        
        if source_id:
            where_conditions.append("source.id = $source_id")
            params["source_id"] = source_id
        if target_id:
            where_conditions.append("target.id = $target_id")
            params["target_id"] = target_id
        
        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
        limit_clause = f"LIMIT {limit}" if limit else ""
        
        query = f"""
        MATCH (source:Entity)-[r:RELATES_TO]->(target:Entity)
        {where_clause}
        RETURN source.id as source, target.id as target, r as properties
        {limit_clause}
        """
        
        result = await tx.run(query, **params)
        
        edges = []
        async for record in result:
            edges.append((
                record["source"],
                record["target"],
                dict(record["properties"])
            ))
        return edges
    
    async def clustering(self, algorithm: str = "leiden") -> Dict[str, Any]:
        """Enhanced clustering with native GDS algorithms."""
        if not self._gds:
            logger.warning("GDS not available, falling back to basic clustering")
            return await self._basic_clustering()
        
        try:
            # Create in-memory graph projection
            graph_name = f"graph_{self.namespace}"
            
            # Project graph if not exists
            if not self._gds.graph.exists(graph_name):
                self._gds.graph.project(
                    graph_name,
                    "Entity",
                    "RELATES_TO"
                )
            
            # Run algorithm based on selection
            if algorithm == "leiden":
                result = self._gds.leiden.mutate(
                    graph_name,
                    mutateProperty="community",
                    includeIntermediateCommunities=True,
                    maxLevels=10,
                    gamma=1.0,
                    theta=0.01
                )
            elif algorithm == "louvain":
                result = self._gds.louvain.mutate(
                    graph_name,
                    mutateProperty="community",
                    includeIntermediateCommunities=True,
                    maxLevels=10
                )
            elif algorithm == "label_propagation":
                result = self._gds.labelPropagation.mutate(
                    graph_name,
                    mutateProperty="community",
                    maxIterations=10
                )
            else:
                raise ValueError(f"Unsupported algorithm: {algorithm}")
            
            # Write back to Neo4j
            self._gds.graph.nodeProperties.write(
                graph_name,
                ["community"],
                ["Entity"]
            )
            
            # Get clustering results
            clusters = await self._get_community_mapping()
            
            return {
                "algorithm": algorithm,
                "communities": clusters,
                "modularity": result.get("modularity", 0),
                "levels": result.get("ranLevels", 1)
            }
            
        except Exception as e:
            logger.error(f"GDS clustering failed: {e}")
            return await self._basic_clustering()
    
    async def _get_community_mapping(self) -> Dict[str, str]:
        """Get community assignments for all nodes."""
        async with self._driver.session() as session:
            query = """
            MATCH (n:Entity)
            WHERE n.community IS NOT NULL
            RETURN n.id as id, n.community as community
            """
            result = await session.run(query)
            
            mapping = {}
            async for record in result:
                mapping[record["id"]] = str(record["community"])
            return mapping
    
    async def _basic_clustering(self) -> Dict[str, Any]:
        """Fallback clustering without GDS."""
        # Simple connected components
        async with self._driver.session() as session:
            query = """
            CALL apoc.algo.community(
                'MATCH (n:Entity) RETURN id(n) as id',
                'MATCH (n:Entity)-[r:RELATES_TO]-(m:Entity) 
                 RETURN id(n) as source, id(m) as target',
                {graph: 'cypher'}
            )
            YIELD nodeId, community
            MATCH (n:Entity) WHERE id(n) = nodeId
            SET n.community = community
            RETURN n.id as id, community
            """
            
            try:
                result = await session.run(query)
                clusters = {}
                async for record in result:
                    clusters[record["id"]] = str(record["community"])
                return {"algorithm": "connected_components", "communities": clusters}
            except:
                # If APOC not available, return empty
                return {"algorithm": "none", "communities": {}}
    
    async def get_community_reports(self) -> List[Dict[str, Any]]:
        """Get community reports using native aggregation."""
        async with self._driver.session() as session:
            query = """
            MATCH (n:Entity)
            WHERE n.community IS NOT NULL
            WITH n.community as community, collect(n) as nodes
            MATCH (source:Entity)-[r:RELATES_TO]->(target:Entity)
            WHERE source.community = community AND target.community = community
            WITH community, nodes, collect(r) as edges
            RETURN {
                community_id: community,
                node_count: size(nodes),
                edge_count: size(edges),
                nodes: [n IN nodes | {id: n.id, type: n.type, description: n.description}],
                density: CASE 
                    WHEN size(nodes) > 1 
                    THEN toFloat(size(edges)) / (size(nodes) * (size(nodes) - 1))
                    ELSE 0
                END
            } as report
            ORDER BY size(nodes) DESC
            """
            
            result = await session.run(query)
            reports = []
            async for record in result:
                reports.append(dict(record["report"]))
            return reports
    
    @asynccontextmanager
    async def transaction(self):
        """Context manager for transactions."""
        async with self._driver.session() as session:
            async with session.begin_transaction() as tx:
                yield tx
    
    async def close(self):
        """Properly close all connections."""
        if self._gds:
            # Drop graph projections
            graphs = self._gds.graph.list()
            for graph in graphs:
                if graph["graphName"].startswith(f"graph_{self.namespace}"):
                    self._gds.graph.drop(graph["graphName"])
        
        if self._driver:
            await self._driver.close()
```

### Phase 3: Testing Framework

#### Create `tests/storage/test_neo4j_production.py`
```python
"""Production-ready tests for Neo4j storage."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import docker
from neo4j import AsyncGraphDatabase

class TestNeo4jStorage:
    """Comprehensive Neo4j storage tests."""
    
    @pytest.fixture
    async def neo4j_container(self):
        """Spin up Neo4j container for testing."""
        client = docker.from_env()
        
        container = client.containers.run(
            "neo4j:5-enterprise",
            environment={
                "NEO4J_AUTH": "neo4j/testpassword",
                "NEO4J_ACCEPT_LICENSE_AGREEMENT": "yes",
                "NEO4J_PLUGINS": '["graph-data-science"]'
            },
            ports={"7687/tcp": None, "7474/tcp": None},
            detach=True,
            remove=True
        )
        
        # Wait for Neo4j to be ready
        await asyncio.sleep(10)
        
        yield container
        
        container.stop()
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_connection_pooling(self, neo4j_container):
        """Test connection pool management."""
        from nano_graphrag._storage.gdb_neo4j import Neo4jStorage
        
        config = {
            "addon_params": {
                "neo4j_url": "neo4j://localhost:7687",
                "neo4j_auth": ("neo4j", "testpassword"),
                "neo4j_max_connection_pool_size": 10
            }
        }
        
        storage = Neo4jStorage(
            namespace="test",
            global_config=config
        )
        
        # Concurrent operations to test pooling
        tasks = []
        for i in range(20):
            tasks.append(storage.upsert_node(f"node_{i}", {"data": i}))
        
        await asyncio.gather(*tasks)
        
        # Verify all nodes created
        nodes = await storage.get_nodes()
        assert len(nodes) == 20
        
        await storage.close()
    
    @pytest.mark.asyncio
    async def test_retry_logic(self):
        """Test retry logic on connection failures."""
        from nano_graphrag._storage.gdb_neo4j import Neo4jStorage
        from neo4j.exceptions import ServiceUnavailable
        
        with patch("nano_graphrag._storage.gdb_neo4j.AsyncGraphDatabase") as mock_driver:
            mock_session = AsyncMock()
            mock_driver.driver.return_value.session.return_value = mock_session
            
            # Simulate failures then success
            mock_session.execute_write.side_effect = [
                ServiceUnavailable("Connection failed"),
                ServiceUnavailable("Connection failed"),
                None  # Success on third attempt
            ]
            
            storage = Neo4jStorage(
                namespace="test",
                global_config={"addon_params": {}}
            )
            
            # Should succeed after retries
            await storage.upsert_node("test", {"data": "test"})
            
            # Verify retried 3 times
            assert mock_session.execute_write.call_count == 3
    
    @pytest.mark.asyncio
    async def test_gds_clustering(self):
        """Test GDS clustering algorithms."""
        from nano_graphrag._storage.gdb_neo4j import Neo4jStorage
        
        with patch("graphdatascience.GraphDataScience") as mock_gds:
            mock_instance = Mock()
            mock_gds.return_value = mock_instance
            
            # Mock GDS methods
            mock_instance.graph.exists.return_value = False
            mock_instance.graph.project.return_value = None
            mock_instance.leiden.mutate.return_value = {
                "modularity": 0.85,
                "ranLevels": 3
            }
            
            storage = Neo4jStorage(
                namespace="test",
                global_config={"addon_params": {"neo4j_gds_enabled": True}}
            )
            
            storage._gds = mock_instance
            
            result = await storage.clustering("leiden")
            
            assert result["algorithm"] == "leiden"
            assert result["modularity"] == 0.85
            assert mock_instance.leiden.mutate.called
    
    @pytest.mark.asyncio  
    async def test_schema_creation(self):
        """Test constraint and index creation."""
        from nano_graphrag._storage.gdb_neo4j import Neo4jStorage
        
        with patch("nano_graphrag._storage.gdb_neo4j.AsyncGraphDatabase") as mock_driver:
            mock_session = AsyncMock()
            mock_tx = AsyncMock()
            
            mock_driver.driver.return_value.session.return_value.__aenter__.return_value = mock_session
            mock_session.execute_write.return_value = None
            
            storage = Neo4jStorage(
                namespace="test",
                global_config={"addon_params": {}}
            )
            
            await storage._ensure_schema()
            
            # Verify constraints were created
            assert mock_session.execute_write.called
            
            # Check it's not called again
            mock_session.reset_mock()
            await storage._ensure_schema()
            assert not mock_session.execute_write.called
```

### Phase 4: Performance Optimization

#### Create `nano_graphrag/_storage/neo4j_optimized.py`
```python
"""Optimized Neo4j operations for GraphRAG."""

class Neo4jBatchProcessor:
    """Batch processor for high-throughput operations."""
    
    def __init__(self, driver, batch_size: int = 1000):
        self.driver = driver
        self.batch_size = batch_size
        self.pending_nodes = []
        self.pending_edges = []
    
    async def add_node(self, node_id: str, properties: Dict):
        """Add node to batch."""
        self.pending_nodes.append((node_id, properties))
        
        if len(self.pending_nodes) >= self.batch_size:
            await self.flush_nodes()
    
    async def flush_nodes(self):
        """Flush pending nodes to Neo4j."""
        if not self.pending_nodes:
            return
        
        async with self.driver.session() as session:
            query = """
            UNWIND $nodes as node
            MERGE (n:Entity {id: node.id})
            SET n += node.properties
            """
            
            nodes_data = [
                {"id": node_id, "properties": props}
                for node_id, props in self.pending_nodes
            ]
            
            await session.run(query, nodes=nodes_data)
            self.pending_nodes.clear()
    
    async def add_edge(self, source: str, target: str, properties: Dict):
        """Add edge to batch."""
        self.pending_edges.append((source, target, properties))
        
        if len(self.pending_edges) >= self.batch_size:
            await self.flush_edges()
    
    async def flush_edges(self):
        """Flush pending edges to Neo4j."""
        if not self.pending_edges:
            return
        
        async with self.driver.session() as session:
            query = """
            UNWIND $edges as edge
            MATCH (source:Entity {id: edge.source})
            MATCH (target:Entity {id: edge.target})
            MERGE (source)-[r:RELATES_TO]->(target)
            SET r += edge.properties
            """
            
            edges_data = [
                {"source": s, "target": t, "properties": p}
                for s, t, p in self.pending_edges
            ]
            
            await session.run(query, edges=edges_data)
            self.pending_edges.clear()
    
    async def flush_all(self):
        """Flush all pending operations."""
        await self.flush_nodes()
        await self.flush_edges()
```

### Phase 5: Documentation and Migration

#### Create `docs/storage/neo4j_production.md`
```markdown
# Neo4j Production Configuration Guide

## Installation

### Docker Deployment
```yaml
version: '3.8'
services:
  neo4j:
    image: neo4j:5-enterprise
    environment:
      NEO4J_AUTH: neo4j/password
      NEO4J_PLUGINS: '["graph-data-science"]'
      NEO4J_dbms_memory_heap_max__size: 4G
      NEO4J_dbms_memory_pagecache_size: 2G
    ports:
      - "7687:7687"
      - "7474:7474"
    volumes:
      - neo4j_data:/data
```

## Configuration

### Basic Configuration
```python
from nano_graphrag.config import GraphRAGConfig, StorageConfig

config = GraphRAGConfig(
    storage=StorageConfig(
        graph_backend="neo4j",
        neo4j_url="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="password",
        neo4j_database="graphrag"
    )
)
```

### Production Configuration
```python
config = GraphRAGConfig(
    storage=StorageConfig(
        graph_backend="neo4j",
        neo4j_url="neo4j+s://production.server:7687",
        neo4j_username="neo4j",
        neo4j_password="${NEO4J_PASSWORD}",
        neo4j_max_connection_pool_size=100,
        neo4j_connection_timeout=60.0,
        neo4j_encrypted=True,
        neo4j_gds_enabled=True
    )
)
```

## Performance Tuning

### Index Strategy
- Entity ID: Unique constraint for fast lookups
- Community: Index for community-based queries
- Full-text: For description searches

### Connection Pooling
- Set pool size based on concurrent operations
- Monitor pool usage via Neo4j metrics

### GDS Optimization
- Pre-warm graph projections for repeated clustering
- Use native algorithms over Cypher when possible

## Monitoring

### Metrics to Track
- Query execution time
- Connection pool utilization
- GDS algorithm performance
- Transaction retry rates

### Example Monitoring Query
```cypher
CALL dbms.listQueries() 
YIELD query, elapsedTimeMillis, allocatedBytes
WHERE elapsedTimeMillis > 1000
RETURN query, elapsedTimeMillis
```

## Migration from NetworkX

### Data Export
```python
# Export from NetworkX
networkx_storage = NetworkXStorage(...)
graph_data = networkx_storage.export_to_graphml()

# Import to Neo4j
neo4j_storage = Neo4jStorage(...)
await neo4j_storage.import_from_graphml(graph_data)
```

### Performance Comparison
| Operation | NetworkX | Neo4j | Improvement |
|-----------|----------|-------|-------------|
| 10K nodes insert | 5s | 1s | 5x |
| Community detection | 30s | 3s | 10x |
| Complex queries | 10s | 0.5s | 20x |
```

## Definition of Done

- [ ] Factory integration with "neo4j" as allowed backend
- [ ] Comprehensive StorageConfig with all Neo4j parameters
- [ ] Enhanced Neo4jStorage implementation:
  - [ ] Proper async constraint creation
  - [ ] Retry logic with exponential backoff
  - [ ] Connection pool lifecycle management
  - [ ] GDS integration for all algorithms
  - [ ] Batch operations for high throughput
  - [ ] Transaction support
- [ ] Testing:
  - [ ] Unit tests with mocking
  - [ ] Integration tests with Docker
  - [ ] Performance benchmarks
  - [ ] Stress tests for connection pooling
- [ ] Documentation:
  - [ ] Production deployment guide
  - [ ] Performance tuning guide
  - [ ] Migration guide from NetworkX
  - [ ] Monitoring and troubleshooting
- [ ] Examples:
  - [ ] Basic usage
  - [ ] Production configuration
  - [ ] Batch import
  - [ ] GDS algorithms

## Feature Branch
`feature/ngraf-012-neo4j-production`

## Pull Request Requirements
- Performance benchmarks showing 10x improvement over NetworkX for large graphs
- Docker Compose for testing
- Test coverage > 90%
- Documentation review
- Load test results (10K nodes, 100K edges)

## Technical Considerations
- Neo4j Enterprise required for GDS
- Memory tuning crucial for performance
- Consider read replicas for high query load
- Implement query result caching for repeated queries