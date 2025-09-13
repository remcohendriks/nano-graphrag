import json
import asyncio
import re
from collections import defaultdict
from typing import List, TYPE_CHECKING, Optional, Any, Union
from dataclasses import dataclass, field
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

if TYPE_CHECKING:
    from neo4j import AsyncGraphDatabase
from ..base import BaseGraphStorage, SingleCommunitySchema
from .._utils import logger
from ..prompt import GRAPH_FIELD_SEP


@dataclass
class Neo4jStorage(BaseGraphStorage):
    _neo4j_module: Optional[Any] = field(init=False, default=None)
    
    @property
    def neo4j(self):
        """Lazy load neo4j module."""
        if self._neo4j_module is None:
            from nano_graphrag._utils import ensure_dependency
            ensure_dependency(
                "neo4j",
                "neo4j",
                "Neo4j graph storage"
            )
            import neo4j
            self._neo4j_module = neo4j
        return self._neo4j_module
    
    def __post_init__(self):
        # Get configuration from addon_params
        self.neo4j_url = self.global_config["addon_params"].get("neo4j_url", None)
        self.neo4j_auth = self.global_config["addon_params"].get("neo4j_auth", None)
        self.neo4j_database = self.global_config["addon_params"].get("neo4j_database", "neo4j")
        
        # Get production configuration parameters
        self.neo4j_max_connection_pool_size = self.global_config["addon_params"].get(
            "neo4j_max_connection_pool_size", 50
        )
        self.neo4j_connection_timeout = self.global_config["addon_params"].get(
            "neo4j_connection_timeout", 30.0
        )
        self.neo4j_encrypted = self.global_config["addon_params"].get(
            "neo4j_encrypted", True
        )
        self.neo4j_max_transaction_retry_time = self.global_config["addon_params"].get(
            "neo4j_max_transaction_retry_time", 30.0
        )
        self.neo4j_batch_size = self.global_config["addon_params"].get(
            "neo4j_batch_size", 1000
        )
        
        # Create a cleaner label using environment variable or default
        # Users can set NEO4J_GRAPH_NAMESPACE to customize the namespace
        import os
        custom_namespace = os.getenv("NEO4J_GRAPH_NAMESPACE")
        if custom_namespace:
            # Use custom namespace from environment
            self.namespace = custom_namespace
        else:
            # Default: GraphRAG_{namespace} where namespace is cleaned
            clean_namespace = self.namespace.replace("/", "_").replace("-", "_").replace(".", "_")
            self.namespace = f"GraphRAG_{clean_namespace}"
        logger.info(f"Using the label {self.namespace} for Neo4j as identifier")
        if self.neo4j_url is None or self.neo4j_auth is None:
            raise ValueError("Missing neo4j_url or neo4j_auth in addon_params")
        
        # Setup retry exceptions - will be imported when needed
        self._retry_exceptions = None
        
        # Cache retry decorator to avoid recreation overhead
        self._retry_decorator = self._get_retry_decorator()
        
        # Initialize operation metrics
        from collections import defaultdict
        self._operation_counts = defaultdict(int)
        
        # Initialize driver without database parameter (CODEX-001 fix)
        self.async_driver = self.neo4j.AsyncGraphDatabase.driver(
            self.neo4j_url, 
            auth=self.neo4j_auth, 
            max_connection_pool_size=self.neo4j_max_connection_pool_size,
            connection_timeout=self.neo4j_connection_timeout,
            encrypted=self.neo4j_encrypted,
            max_transaction_retry_time=self.neo4j_max_transaction_retry_time
        )

    def _get_retry_decorator(self):
        """Get retry decorator with Neo4j exceptions."""
        try:
            from neo4j.exceptions import ServiceUnavailable, SessionExpired
            return retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_exception_type((ServiceUnavailable, SessionExpired))
            )
        except ImportError:
            # If exceptions not available, just retry on any exception
            return retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=10)
            )
    
    def _sanitize_label(self, label: str) -> str:
        """Sanitize label to prevent injection attacks."""
        if not label:
            return "UNKNOWN"
        # Allow only alphanumeric and underscore
        sanitized = re.sub(r'[^A-Za-z0-9_]', '_', label)
        # Ensure it starts with a letter or underscore
        if sanitized and not sanitized[0].isalpha() and sanitized[0] != '_':
            sanitized = '_' + sanitized
        return sanitized or "UNKNOWN"
    
    async def _check_gds_availability(self):
        """Check if Graph Data Science library is available."""
        async with self.async_driver.session(database=self.neo4j_database) as session:
            try:
                result = await session.run("CALL gds.version()")
                record = await result.single()
                version = record.get("version") if record else None
                logger.info(f"Neo4j GDS version {version} is available")
                return True
            except Exception as e:
                error_msg = (
                    "Neo4j Graph Data Science (GDS) library is required for Neo4j backend. "
                    "Please use Neo4j Enterprise Edition with GDS installed, or switch to "
                    "'networkx' graph backend for Community Edition compatibility. "
                    f"Error: {e}"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)
    
    async def _ensure_constraints(self):
        """Create constraints and indexes with proper async handling."""
        async with self.async_driver.session(database=self.neo4j_database) as session:
            async def create_constraints(tx):
                # Check existing constraints
                result = await tx.run("SHOW CONSTRAINTS")
                existing_constraints = set()
                async for record in result:
                    labels = record.get("labelsOrTypes", [])
                    props = record.get("properties", [])
                    if self.namespace in labels:
                        existing_constraints.add(tuple(props))
                
                # Create uniqueness constraint (also creates index)
                if ("id",) not in existing_constraints:
                    await tx.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS "
                        f"FOR (n:`{self.namespace}`) "
                        f"REQUIRE n.id IS UNIQUE"
                    )
                    logger.info(f"Created uniqueness constraint for {self.namespace}.id")
                
                # Check existing indexes
                result = await tx.run("SHOW INDEXES")
                existing_indexes = set()
                async for record in result:
                    labels = record.get("labelsOrTypes", [])
                    props = record.get("properties", [])
                    if self.namespace in labels:
                        existing_indexes.add(tuple(props))
                
                # Create additional indexes for performance (skip ID as constraint creates it)
                indexes_to_create = [
                    ("entity_type",),  # For filtering by type
                    ("communityIds",),  # For clustering queries
                    ("source_id",)  # For chunk tracking
                ]
                
                for index_props in indexes_to_create:
                    if index_props not in existing_indexes and index_props != ("id",):
                        prop_name = index_props[0]
                        await tx.run(
                            f"CREATE INDEX IF NOT EXISTS "
                            f"FOR (n:`{self.namespace}`) "
                            f"ON (n.{prop_name})"
                        )
                        logger.info(f"Created index for {self.namespace}.{prop_name}")
            
            try:
                await session.execute_write(create_constraints)
            except Exception as e:
                # Only suppress already-exists errors, re-raise others
                error_msg = str(e).lower()
                if "already exists" in error_msg or "equivalent constraint already exists" in error_msg:
                    logger.debug(f"Constraint/index already exists (expected): {e}")
                else:
                    logger.error(f"Failed to create constraints/indexes: {e}")
                    raise

    async def _init_workspace(self):
        await self.async_driver.verify_authentication()
        await self.async_driver.verify_connectivity()
        # Create constraints with proper async handling
        await self._ensure_constraints()

    async def index_start_callback(self):
        logger.info("Init Neo4j workspace")
        await self._init_workspace()
        
        # Check GDS availability (fail fast if not available)
        await self._check_gds_availability()

    async def has_node(self, node_id: str) -> bool:
        async with self.async_driver.session(database=self.neo4j_database) as session:
            result = await session.run(
                f"MATCH (n:`{self.namespace}`) WHERE n.id = $node_id RETURN COUNT(n) > 0 AS exists",
                node_id=node_id,
            )
            record = await result.single()
            return record["exists"] if record else False

    async def has_edge(self, source_node_id: str, target_node_id: str) -> bool:
        async with self.async_driver.session(database=self.neo4j_database) as session:
            result = await session.run(
                f"""
                MATCH (s:`{self.namespace}`)
                WHERE s.id = $source_id
                MATCH (t:`{self.namespace}`)
                WHERE t.id = $target_id
                RETURN EXISTS((s)-[]->(t)) AS exists
                """,
                source_id=source_node_id,
                target_id=target_node_id,
            )
    
            record = await result.single()
            return record["exists"] if record else False

    async def node_degree(self, node_id: str) -> int:
        results = await self.node_degrees_batch([node_id])
        return results[0] if results else 0
        
    async def node_degrees_batch(self, node_ids: List[str]) -> List[int]:
        if not node_ids:
            return []
                    
        result_dict = {node_id: 0 for node_id in node_ids}
        async with self.async_driver.session(database=self.neo4j_database) as session:
            result = await session.run(
                f"""
                UNWIND $node_ids AS node_id
                MATCH (n:`{self.namespace}`)
                WHERE n.id = node_id
                OPTIONAL MATCH (n)-[]-(m:`{self.namespace}`)
                RETURN node_id, COUNT(m) AS degree
                """,
                node_ids=node_ids
            )
                
            async for record in result:
                result_dict[record["node_id"]] = record["degree"]
                
        return [result_dict[node_id] for node_id in node_ids]
    
    async def edge_degree(self, src_id: str, tgt_id: str) -> int:
        results = await self.edge_degrees_batch([(src_id, tgt_id)])
        return results[0] if results else 0

    async def edge_degrees_batch(self, edge_pairs: list[tuple[str, str]]) -> list[int]:
        if not edge_pairs:
            return []
        
        result_dict = {tuple(edge_pair): 0 for edge_pair in edge_pairs}
        
        edges_params = [{"src_id": src, "tgt_id": tgt} for src, tgt in edge_pairs]
        
        try:
            async with self.async_driver.session(database=self.neo4j_database) as session:
                result = await session.run(
                    f"""
                    UNWIND $edges AS edge
                    
                    MATCH (s:`{self.namespace}`)
                    WHERE s.id = edge.src_id
                    WITH edge, s
                    OPTIONAL MATCH (s)-[]-(n1:`{self.namespace}`)
                    WITH edge, COUNT(n1) AS src_degree
                    
                    MATCH (t:`{self.namespace}`)
                    WHERE t.id = edge.tgt_id
                    WITH edge, src_degree, t
                    OPTIONAL MATCH (t)-[]-(n2:`{self.namespace}`)
                    WITH edge.src_id AS src_id, edge.tgt_id AS tgt_id, src_degree, COUNT(n2) AS tgt_degree
                    
                    RETURN src_id, tgt_id, src_degree + tgt_degree AS degree
                    """,
                    edges=edges_params
                )
                
                async for record in result:
                    src_id = record["src_id"]
                    tgt_id = record["tgt_id"]
                    degree = record["degree"]
                    
                    # 更新结果字典
                    edge_pair = (src_id, tgt_id)
                    result_dict[edge_pair] = degree
            
            return [result_dict[tuple(edge_pair)] for edge_pair in edge_pairs]
        except Exception as e:
            logger.error(f"Error in batch edge degree calculation: {e}")
            return [0] * len(edge_pairs)



    async def get_node(self, node_id: str) -> Union[dict, None]:
        # Apply cached retry decorator for resilience
        retried_func = self._retry_decorator(self.get_nodes_batch)
        result = await retried_func([node_id])
        return result[0] if result else None

    async def get_nodes_batch(self, node_ids: list[str]) -> list[Union[dict, None]]:
        if not node_ids:
            return []
            
        result_dict = {node_id: None for node_id in node_ids}

        try:
            async with self.async_driver.session(database=self.neo4j_database) as session:
                result = await session.run(
                    f"""
                    UNWIND $node_ids AS node_id
                    MATCH (n:`{self.namespace}`)
                    WHERE n.id = node_id
                    RETURN node_id, properties(n) AS node_data
                    """,
                    node_ids=node_ids
                )
                
                async for record in result:
                    node_id = record["node_id"]
                    raw_node_data = record["node_data"]
                    
                    if raw_node_data:
                        raw_node_data["clusters"] = json.dumps(
                            [
                                {
                                    "level": index,
                                    "cluster": cluster_id,
                                }
                                for index, cluster_id in enumerate(
                                    raw_node_data.get("communityIds", [])
                                )
                            ]
                        )
                        result_dict[node_id] = raw_node_data
            return [result_dict[node_id] for node_id in node_ids]
        except Exception as e:
            logger.error(f"Error in batch node retrieval: {e}")
            raise e

    async def get_edge(
        self, source_node_id: str, target_node_id: str
    ) -> Union[dict, None]:
        # Apply cached retry decorator for resilience
        retried_func = self._retry_decorator(self.get_edges_batch)
        results = await retried_func([(source_node_id, target_node_id)])
        return results[0] if results else None

    async def get_edges_batch(
        self, edge_pairs: list[tuple[str, str]]
    ) -> list[Union[dict, None]]:
        if not edge_pairs:
            return []
            
        result_dict = {tuple(edge_pair): None for edge_pair in edge_pairs}
        
        edges_params = [{"source_id": src, "target_id": tgt} for src, tgt in edge_pairs]
        
        try:
            async with self.async_driver.session(database=self.neo4j_database) as session:
                result = await session.run(
                    f"""
                    UNWIND $edges AS edge
                    MATCH (s:`{self.namespace}`)-[r]->(t:`{self.namespace}`)
                    WHERE s.id = edge.source_id AND t.id = edge.target_id
                    RETURN edge.source_id AS source_id, edge.target_id AS target_id, properties(r) AS edge_data
                    """,
                    edges=edges_params
                )
                
                async for record in result:
                    source_id = record["source_id"]
                    target_id = record["target_id"]
                    edge_data = record["edge_data"]

                    # Keep numeric types as-is for consistency
                    # Note: If specific consumers need string conversion,
                    # they should handle it at their boundary

                    edge_pair = (source_id, target_id)
                    result_dict[edge_pair] = edge_data
            
            return [result_dict[tuple(edge_pair)] for edge_pair in edge_pairs]
        except Exception as e:
            logger.error(f"Error in batch edge retrieval: {e}")
            return [None] * len(edge_pairs)

    async def get_node_edges(
        self, source_node_id: str
    ) -> list[tuple[str, str]]:
        results = await self.get_nodes_edges_batch([source_node_id])
        return results[0] if results else []

    async def get_nodes_edges_batch(
        self, node_ids: list[str]
    ) -> list[list[tuple[str, str]]]:
        if not node_ids:
            return []
            
        result_dict = {node_id: [] for node_id in node_ids}
        
        try:
            async with self.async_driver.session(database=self.neo4j_database) as session:
                result = await session.run(
                    f"""
                    UNWIND $node_ids AS node_id
                    MATCH (s:`{self.namespace}`)-[r]->(t:`{self.namespace}`)
                    WHERE s.id = node_id
                    RETURN s.id AS source_id, t.id AS target_id
                    """,
                    node_ids=node_ids
                )
                
                async for record in result:
                    source_id = record["source_id"]
                    target_id = record["target_id"]
                    
                    if source_id in result_dict:
                        result_dict[source_id].append((source_id, target_id))
            
            return [result_dict[node_id] for node_id in node_ids]
        except Exception as e:
            logger.error(f"Error in batch node edges retrieval: {e}")
            return [[] for _ in node_ids]

    async def upsert_node(self, node_id: str, node_data: dict[str, str]):
        # Track operation
        self._operation_counts['upsert_node'] += 1
        # Apply cached retry decorator
        retried_func = self._retry_decorator(self.upsert_nodes_batch)
        await retried_func([(node_id, node_data)])

    async def upsert_nodes_batch(self, nodes_data: list[tuple[str, dict[str, str]]]):
        if not nodes_data:
            return []
        
        # Track operation
        self._operation_counts['upsert_nodes_batch'] += 1
        
        # Process in chunks to prevent OOM
        batch_size = self.neo4j_batch_size
        for i in range(0, len(nodes_data), batch_size):
            chunk = nodes_data[i:i + batch_size]
            await self._process_nodes_chunk(chunk)
    
    async def _process_nodes_chunk(self, nodes_data: list[tuple[str, dict[str, str]]]):
        """Process a chunk of nodes."""
        nodes_by_type = {}
        for node_id, node_data in nodes_data:
            # Sanitize entity_type to prevent injection attacks
            raw_type = node_data.get("entity_type", "UNKNOWN").strip('"')
            node_type = self._sanitize_label(raw_type)
            if node_type not in nodes_by_type:
                nodes_by_type[node_type] = []
            nodes_by_type[node_type].append((node_id, node_data))
        
        async with self.async_driver.session(database=self.neo4j_database) as session:
            for node_type, type_nodes in nodes_by_type.items():
                params = [{"id": node_id, "data": node_data} for node_id, node_data in type_nodes]
                
                await session.run(
                    f"""
                    UNWIND $nodes AS node
                    MERGE (n:`{self.namespace}`:`{node_type}` {{id: node.id}})
                    SET n += node.data
                    """,
                    nodes=params
                )
        
    async def upsert_edge(
        self, source_node_id: str, target_node_id: str, edge_data: dict[str, str]
    ):
        # Track operation
        self._operation_counts['upsert_edge'] += 1
        # Apply cached retry decorator
        retried_func = self._retry_decorator(self.upsert_edges_batch)
        await retried_func([(source_node_id, target_node_id, edge_data)])


    async def upsert_edges_batch(
        self, edges_data: list[tuple[str, str, dict[str, str]]]
    ):
        if not edges_data:
            return
        
        edges_params = []
        for source_id, target_id, edge_data in edges_data:
            edge_data_copy = edge_data.copy()
            # Ensure weight is numeric for GDS compatibility
            if "weight" in edge_data_copy:
                try:
                    edge_data_copy["weight"] = float(edge_data_copy["weight"])
                except (ValueError, TypeError):
                    edge_data_copy["weight"] = 0.0
            else:
                edge_data_copy.setdefault("weight", 0.0)

            edges_params.append({
                "source_id": source_id,
                "target_id": target_id,
                "edge_data": edge_data_copy
            })
        
        async with self.async_driver.session(database=self.neo4j_database) as session:
            await session.run(
                f"""
                UNWIND $edges AS edge
                MATCH (s:`{self.namespace}`)
                WHERE s.id = edge.source_id
                WITH edge, s
                MATCH (t:`{self.namespace}`)
                WHERE t.id = edge.target_id
                MERGE (s)-[r:RELATED]->(t)
                SET r += edge.edge_data
                """,
                edges=edges_params
            )
        



    async def clustering(self, algorithm: str):
        if algorithm != "leiden":
            raise ValueError(
                f"Clustering algorithm {algorithm} not supported in Neo4j implementation"
            )

        random_seed = self.global_config["graph_cluster_seed"]
        max_level = self.global_config["max_graph_cluster_size"]
        graph_created = False
        
        async with self.async_driver.session(database=self.neo4j_database) as session:
            try:
                # Check if graph already exists and drop it if so
                graph_name = f'graph_{self.namespace}'
                exists_result = await session.run(
                    f"CALL gds.graph.exists('{graph_name}') YIELD exists"
                )
                exists_record = await exists_result.single()
                if exists_record and exists_record['exists']:
                    await session.run(f"CALL gds.graph.drop('{graph_name}')")
                    logger.info(f"Dropped existing GDS projection '{graph_name}'")
                
                # Project the graph with undirected relationships
                await session.run(
                    f"""
                    CALL gds.graph.project(
                        '{graph_name}',
                        ['{self.namespace}'],
                        {{
                            RELATED: {{
                                orientation: 'UNDIRECTED',
                                properties: ['weight']
                            }}
                        }}
                    )
                    """
                )
                graph_created = True

                # Run Leiden algorithm
                result = await session.run(
                    f"""
                    CALL gds.leiden.write(
                        '{graph_name}',
                        {{
                            writeProperty: 'communityIds',
                            includeIntermediateCommunities: True,
                            relationshipWeightProperty: "weight",
                            maxLevels: {max_level},
                            tolerance: 0.0001,
                            gamma: 1.0,
                            theta: 0.01,
                            randomSeed: {random_seed}
                        }}
                    )
                    YIELD communityCount, modularities;
                    """
                )
                result = await result.single()
                community_count: int = result["communityCount"] if result else 0
                modularities = result["modularities"] if result else []
                logger.info(
                    f"Performed graph clustering with {community_count} communities and modularities {modularities}"
                )

                # Retrieve the node->community mapping
                mapping_result = await session.run(
                    f"""
                    MATCH (n:`{self.namespace}`)
                    WHERE n.communityIds IS NOT NULL
                    RETURN n.id AS nodeId, n.communityIds[-1] AS communityId
                    """
                )

                # Build communities dictionary
                communities = {}
                async for record in mapping_result:
                    node_id = record["nodeId"]
                    # The last element of communityIds is the final community
                    community_id = int(record["communityId"])
                    communities[node_id] = community_id

                # Return clustering results in expected format
                return {
                    "communities": communities,
                    "community_count": community_count,
                    "modularities": modularities
                }
            except Exception as e:
                logger.error(f"Error during GDS clustering: {e}")
                raise
            finally:
                # Only drop the projected graph if it was successfully created
                if graph_created:
                    try:
                        await session.run(f"CALL gds.graph.drop('{graph_name}')")
                    except Exception as e:
                        logger.warning(f"Failed to drop projected graph: {e}")

    async def community_schema(self) -> dict[str, SingleCommunitySchema]:
        results = defaultdict(
            lambda: dict(
                level=None,
                title=None,
                edges=set(),
                nodes=set(),
                chunk_ids=set(),
                occurrence=0.0,
                sub_communities=[],
            )
        )

        async with self.async_driver.session(database=self.neo4j_database) as session:
            # Fetch community data
            result = await session.run(
                f"""
                MATCH (n:`{self.namespace}`)
                WITH n, n.communityIds AS communityIds, [(n)-[]-(m:`{self.namespace}`) | m.id] AS connected_nodes
                RETURN n.id AS node_id, n.source_id AS source_id, 
                       communityIds AS cluster_key,
                       connected_nodes
                """
            )

            # records = await result.fetch()

            max_num_ids = 0
            async for record in result:
                # Guard against None values
                cluster_keys = record.get("cluster_key")
                if cluster_keys is None:
                    continue
                    
                node_id = str(record.get("node_id", ""))
                source_id = record.get("source_id")
                connected_nodes = record.get("connected_nodes", [])
                
                for index, c_id in enumerate(cluster_keys):
                    level = index
                    cluster_key = str(c_id)

                    results[cluster_key]["level"] = level
                    results[cluster_key]["title"] = f"Cluster {cluster_key}"
                    results[cluster_key]["nodes"].add(node_id)
                    
                    # Add edges if we have connected nodes
                    if connected_nodes:
                        results[cluster_key]["edges"].update(
                            [
                                tuple(sorted([node_id, str(connected)]))
                                for connected in connected_nodes
                                if connected and connected != node_id
                            ]
                        )
                    
                    # Add chunk IDs if source_id exists
                    if source_id:
                        chunk_ids = source_id.split(GRAPH_FIELD_SEP)
                        results[cluster_key]["chunk_ids"].update(chunk_ids)
                        max_num_ids = max(
                            max_num_ids, len(results[cluster_key]["chunk_ids"])
                        )

            # Process results
            for k, v in results.items():
                v["edges"] = [list(e) for e in v["edges"]]
                v["nodes"] = list(v["nodes"])
                v["chunk_ids"] = list(v["chunk_ids"])
                v["occurrence"] = len(v["chunk_ids"]) / max_num_ids

            # Compute sub-communities (this is a simplified approach)
            for cluster in results.values():
                cluster["sub_communities"] = [
                    sub_key
                    for sub_key, sub_cluster in results.items()
                    if sub_cluster["level"] > cluster["level"]
                    and set(sub_cluster["nodes"]).issubset(set(cluster["nodes"]))
                ]

        return dict(results)

    async def get_pool_stats(self) -> dict:
        """Get connection pool statistics for monitoring."""
        return {
            "max_size": self.neo4j_max_connection_pool_size,
            "database": self.neo4j_database,
            "encrypted": self.neo4j_encrypted,
            "operation_counts": dict(self._operation_counts)
        }
    
    async def index_done_callback(self):
        await self.async_driver.close()

    async def _debug_delete_all_node_edges(self):
        async with self.async_driver.session(database=self.neo4j_database) as session:
            try:
                # Delete all relationships in the namespace
                await session.run(f"MATCH (n:`{self.namespace}`)-[r]-() DELETE r")

                # Delete all nodes in the namespace
                await session.run(f"MATCH (n:`{self.namespace}`) DELETE n")

                logger.info(
                    f"All nodes and edges in namespace '{self.namespace}' have been deleted."
                )
            except Exception as e:
                logger.error(f"Error deleting nodes and edges: {str(e)}")
                raise
