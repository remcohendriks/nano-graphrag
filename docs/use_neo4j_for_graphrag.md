# Using Neo4j for GraphRAG in nano-graphrag

## Overview

nano-graphrag supports Neo4j as a production-ready graph storage backend, providing enterprise-grade performance and scalability for knowledge graph operations. This guide will help you get started with Neo4j integration.

## Why Neo4j?

Neo4j offers several advantages over the default NetworkX backend:

- **Scalability**: Handle millions of nodes and relationships efficiently
- **Persistence**: Data survives application restarts
- **Query Performance**: Optimized graph traversals with Cypher
- **Graph Algorithms**: Advanced clustering via Graph Data Science (GDS) library
- **Production Ready**: Battle-tested in enterprise environments
- **Visualization**: Built-in browser for exploring your knowledge graph

## Prerequisites

### Neo4j Enterprise Edition
**Important**: Neo4j Enterprise Edition is required. The Graph Data Science (GDS) library needed for clustering algorithms is only available in Enterprise Edition.

- **Version**: Neo4j 5.x or later
- **Edition**: Enterprise (Community Edition is NOT supported)
- **License**: Valid Neo4j Enterprise license for production use

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Start Neo4j Enterprise with GDS
docker-compose -f docker-compose-neo4j.yml up -d

# Verify it's running
docker-compose -f docker-compose-neo4j.yml ps

# Access Neo4j Browser
open http://localhost:7474
# Login: neo4j / your-secure-password-change-me
```

### Option 2: Manual Installation

1. Install [Neo4j Enterprise](https://neo4j.com/docs/operations-manual/current/installation/) (version 5.x)
2. Install [Neo4j GDS plugin](https://neo4j.com/docs/graph-data-science/current/installation/neo4j-server/)
3. Start Neo4j server
4. Note your connection details:
   - URL: `neo4j://localhost:7687` (default)
   - Username: `neo4j` (default)
   - Password: Your configured password

### Install nano-graphrag with Neo4j

```bash
pip install nano-graphrag[neo4j]
```

## Configuration

### Using Environment Variables

```bash
# Required
export NEO4J_URL="neo4j://localhost:7687"
export NEO4J_USERNAME="neo4j"
export NEO4J_PASSWORD="your-secure-password"

# Optional (with defaults)
export NEO4J_DATABASE="neo4j"                    # Target database
export NEO4J_MAX_CONNECTION_POOL_SIZE=50         # Connection pool size
export NEO4J_CONNECTION_TIMEOUT=30.0             # Timeout in seconds
export NEO4J_BATCH_SIZE=1000                     # Batch size for imports
```

### Python Configuration

```python
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig

# Basic configuration
config = GraphRAGConfig(
    storage={
        "graph_backend": "neo4j",
        "neo4j_url": "neo4j://localhost:7687",
        "neo4j_username": "neo4j",
        "neo4j_password": "your-secure-password",
    }
)

# Initialize GraphRAG
rag = GraphRAG(config=config)

# Insert documents
with open("./book.txt") as f:
    rag.insert(f.read())

# Query
response = rag.query("What are the main themes?")
print(response)
```

### Advanced Configuration

```python
config = GraphRAGConfig(
    storage={
        # Required
        "graph_backend": "neo4j",
        "neo4j_url": "neo4j+s://production.example.com:7687",  # TLS enabled
        "neo4j_username": "neo4j",
        "neo4j_password": "secure-password",
        
        # Optional performance tuning
        "neo4j_database": "graphrag",              # Custom database name
        "neo4j_max_connection_pool_size": 100,     # For high concurrency
        "neo4j_connection_timeout": 60.0,          # Longer timeout
        "neo4j_batch_size": 5000,                  # Larger batches for big imports
        "neo4j_max_transaction_retry_time": 60.0,  # Retry duration
    }
)
```

## TLS/SSL Configuration

The system automatically detects encryption from the URL scheme:

- `neo4j://` or `bolt://` → TLS disabled (development)
- `neo4j+s://` or `bolt+s://` → TLS enabled (production)

For production, always use TLS:

```python
config = GraphRAGConfig(
    storage={
        "graph_backend": "neo4j",
        "neo4j_url": "neo4j+s://production.example.com:7687",  # TLS automatically enabled
        "neo4j_username": "neo4j",
        "neo4j_password": "secure-password",
    }
)
```

## Working with Your Graph

### Exploring in Neo4j Browser

Access Neo4j Browser at http://localhost:7474 to visualize and query your knowledge graph:

```cypher
-- View entities and relationships
MATCH (n:Entity)-[r:RELATED]-(m:Entity)
RETURN n, r, m
LIMIT 100

-- Find specific entities
MATCH (n:Entity)
WHERE n.name CONTAINS 'search_term'
RETURN n

-- Explore communities
MATCH (n:Entity)
WHERE n.community_id IS NOT NULL
RETURN n.community_id, collect(n.name) as entities
ORDER BY n.community_id
```

### Monitoring Performance

```python
# Get connection pool statistics
stats = await rag._graph_storage.get_pool_stats()
print(f"Pool size: {stats['max_size']}")
print(f"Database: {stats['database']}")
print(f"Operations: {stats['operation_counts']}")
```

## Performance Optimization

### Large Document Processing

For large documents or batch imports:

```python
config = GraphRAGConfig(
    storage={
        "graph_backend": "neo4j",
        "neo4j_url": "neo4j://localhost:7687",
        "neo4j_username": "neo4j",
        "neo4j_password": "password",
        "neo4j_batch_size": 5000,  # Increase batch size
        "neo4j_max_connection_pool_size": 100,  # More connections
    }
)
```

### Memory Configuration (Docker)

Edit `docker-compose-neo4j.yml`:

```yaml
environment:
  NEO4J_server_memory_heap_initial__size: 4G
  NEO4J_server_memory_heap_max__size: 8G
  NEO4J_server_memory_pagecache_size: 4G
```

## Troubleshooting

### Common Issues

#### "Neo4j Graph Data Science (GDS) library is required"
- **Cause**: GDS plugin not installed or using Community Edition
- **Solution**: Use Neo4j Enterprise with GDS plugin (included in docker-compose)

#### "Connection refused"
- **Cause**: Neo4j not running or incorrect connection details
- **Solution**: 
  1. Check Neo4j is running: `docker ps` or `neo4j status`
  2. Verify URL and port (default: 7687)
  3. Check credentials

#### "Out of memory during import"
- **Cause**: Batch size too large or insufficient heap memory
- **Solution**:
  1. Reduce batch size: `neo4j_batch_size=500`
  2. Increase Neo4j heap memory
  3. Process documents in smaller chunks

#### "TLS handshake failed"
- **Cause**: Mismatched TLS configuration
- **Solution**:
  1. For local development: use `neo4j://` (no TLS)
  2. For production: use `neo4j+s://` with proper certificates

## Migration from NetworkX

If you have existing data in the default NetworkX backend:

```python
# Note: You'll need to re-index your documents with Neo4j
# The graph structure will be rebuilt in Neo4j

# Step 1: Configure Neo4j backend
config = GraphRAGConfig(
    storage={
        "graph_backend": "neo4j",
        "neo4j_url": "neo4j://localhost:7687",
        "neo4j_username": "neo4j",
        "neo4j_password": "password",
    }
)

# Step 2: Create new GraphRAG instance
rag_neo4j = GraphRAG(config=config)

# Step 3: Re-index your documents
with open("./documents.txt") as f:
    rag_neo4j.insert(f.read())
```

## Production Checklist

- [ ] Use Neo4j Enterprise Edition with valid license
- [ ] Configure TLS with `neo4j+s://` URLs
- [ ] Set strong passwords and rotate regularly
- [ ] Adjust memory settings based on workload
- [ ] Configure appropriate batch sizes
- [ ] Set up monitoring and alerting
- [ ] Implement backup strategy
- [ ] Test failover and recovery

## Advanced Usage

### Custom Cypher Queries

```python
storage = rag._graph_storage

async with storage.async_driver.session(database=storage.neo4j_database) as session:
    result = await session.run("""
        MATCH (n:Entity {entity_type: 'PERSON'})
        RETURN n.name, n.description
        LIMIT 10
    """)
    
    async for record in result:
        print(record['n.name'], record['n.description'])
```

### Using Additional GDS Algorithms

```python
async with storage.async_driver.session(database=storage.neo4j_database) as session:
    # Create graph projection
    await session.run("""
        CALL gds.graph.project(
            'myGraph',
            'Entity',
            'RELATED'
        )
    """)
    
    # Run PageRank
    await session.run("""
        CALL gds.pageRank.write('myGraph', {
            writeProperty: 'pagerank'
        })
    """)
    
    # Clean up projection
    await session.run("CALL gds.graph.drop('myGraph')")
```

## Resources

- **Full Production Guide**: [Neo4j Production Guide](./storage/neo4j_production.md)
- **Docker Setup**: [Docker Neo4j Setup](./docker-neo4j-setup.md)
- **Neo4j Documentation**: [neo4j.com/docs](https://neo4j.com/docs/)
- **GDS Documentation**: [neo4j.com/docs/graph-data-science](https://neo4j.com/docs/graph-data-science/current/)
- **Issues**: [GitHub Issues](https://github.com/gusye1234/nano-graphrag/issues)