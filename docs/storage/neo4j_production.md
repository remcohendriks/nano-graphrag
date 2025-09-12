# Neo4j Production Guide for nano-graphrag

## Overview

This guide covers the production deployment of nano-graphrag with Neo4j as the graph storage backend. Neo4j provides enterprise-grade graph database capabilities with full Graph Data Science (GDS) support for advanced clustering algorithms.

## Requirements

### Neo4j Enterprise Edition
- **Version**: Neo4j 5.x or later
- **Edition**: Enterprise Edition (required for GDS)
- **License**: Valid Neo4j Enterprise license
- **GDS Plugin**: Graph Data Science library 2.5.0+

> **Important**: Neo4j Community Edition is NOT supported. The GDS library required for clustering is only available in Enterprise Edition. Users needing Community Edition compatibility should use the default `networkx` graph backend.

## Installation

### Install nano-graphrag with Neo4j support
```bash
pip install nano-graphrag[neo4j]
```

### Set up Neo4j Enterprise with Docker
```yaml
# docker-compose.yml
version: '3.8'

services:
  neo4j:
    image: neo4j:5-enterprise
    environment:
      # Authentication
      NEO4J_AUTH: neo4j/your-secure-password
      
      # Accept Enterprise License
      NEO4J_ACCEPT_LICENSE_AGREEMENT: "yes"
      
      # Install plugins (fixed in Round 2)
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
      
      # Memory configuration
      NEO4J_server_memory_heap_initial__size: 2G
      NEO4J_server_memory_heap_max__size: 4G
      NEO4J_server_memory_pagecache_size: 2G
      
    ports:
      - "7474:7474"  # Browser
      - "7687:7687"  # Bolt
      
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

volumes:
  neo4j_data:
  neo4j_logs:
```

## Configuration

### Environment Variables

```bash
# Basic connection
export NEO4J_URL="neo4j://localhost:7687"  # Use neo4j+s:// for TLS
export NEO4J_USERNAME="neo4j"
export NEO4J_PASSWORD="your-secure-password"
export NEO4J_DATABASE="neo4j"  # Optional, defaults to 'neo4j'

# Production tuning (all optional with sensible defaults)
export NEO4J_MAX_CONNECTION_POOL_SIZE=100  # Default: 50
export NEO4J_CONNECTION_TIMEOUT=60.0       # Default: 30.0 seconds
export NEO4J_ENCRYPTED=true                # Auto-inferred from URL scheme
export NEO4J_MAX_TRANSACTION_RETRY_TIME=60.0  # Default: 30.0 seconds
export NEO4J_BATCH_SIZE=2000               # Default: 1000
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
        "neo4j_password": "your-password",
    }
)

# Advanced configuration with all parameters
config = GraphRAGConfig(
    storage={
        "graph_backend": "neo4j",
        "neo4j_url": "neo4j+s://production.example.com:7687",  # TLS enabled
        "neo4j_username": "neo4j",
        "neo4j_password": "secure-password",
        "neo4j_database": "graphrag",
        "neo4j_max_connection_pool_size": 100,
        "neo4j_connection_timeout": 60.0,
        "neo4j_encrypted": True,  # Auto-detected from URL
        "neo4j_max_transaction_retry_time": 60.0,
        "neo4j_batch_size": 5000,  # For large imports
    }
)

rag = GraphRAG(config=config)
```

## TLS/SSL Configuration

The Neo4j backend intelligently infers encryption settings from the URL scheme:

- `neo4j://` or `bolt://` → TLS disabled (default for local development)
- `neo4j+s://` or `bolt+s://` → TLS enabled (for production)

You can override with the `NEO4J_ENCRYPTED` environment variable if needed.

## Performance Tuning

### Batch Processing
Large imports are automatically chunked to prevent memory issues:
- Default batch size: 1000 nodes/edges per transaction
- Configurable via `NEO4J_BATCH_SIZE`
- Recommended: 1000-5000 depending on node complexity

### Connection Pooling
```bash
# For high-concurrency applications
NEO4J_MAX_CONNECTION_POOL_SIZE=200
NEO4J_CONNECTION_TIMEOUT=120.0
```

### Memory Configuration
Neo4j requires proper memory allocation for optimal performance:
```yaml
# docker-compose.yml
NEO4J_server_memory_heap_initial__size: 4G
NEO4J_server_memory_heap_max__size: 8G
NEO4J_server_memory_pagecache_size: 4G
```

## Monitoring

### Connection Pool Statistics
```python
# Get runtime statistics
stats = await storage.get_pool_stats()
print(f"Max pool size: {stats['max_size']}")
print(f"Database: {stats['database']}")
print(f"Encrypted: {stats['encrypted']}")
print(f"Operations: {stats['operation_counts']}")
```

### Neo4j Browser
Access the Neo4j Browser at http://localhost:7474 to:
- Monitor database performance
- Run Cypher queries
- Visualize the knowledge graph
- Check GDS algorithm results

## Troubleshooting

### Common Issues

#### GDS Not Available
**Error**: "Neo4j Graph Data Science (GDS) library is required for Neo4j backend"

**Solution**: 
1. Ensure you're using Neo4j Enterprise Edition
2. Verify GDS plugin is installed: `CALL gds.version()`
3. Consider switching to `networkx` backend if Enterprise is not available

#### Connection Refused
**Error**: "Cannot connect to Neo4j"

**Solution**:
1. Check Neo4j is running: `docker ps`
2. Verify ports are exposed: 7687 for Bolt
3. Check authentication credentials
4. Ensure database parameter matches

#### TLS Handshake Failed
**Error**: "TLS handshake failed"

**Solution**:
1. URL scheme matches server configuration
2. Use `neo4j://` for non-TLS local development
3. Use `neo4j+s://` for TLS production deployments

#### Out of Memory During Import
**Error**: "Java heap space" or timeouts

**Solution**:
1. Reduce batch size: `NEO4J_BATCH_SIZE=500`
2. Increase Neo4j heap memory
3. Process data in smaller chunks

## Migration from NetworkX

To migrate from the default NetworkX backend to Neo4j:

```python
# 1. Export from NetworkX
graphrag_networkx = GraphRAG(config={"graph_backend": "networkx"})
# ... perform indexing ...

# 2. Switch to Neo4j
graphrag_neo4j = GraphRAG(config={
    "graph_backend": "neo4j",
    "neo4j_url": "neo4j://localhost:7687",
    # ... other Neo4j config
})

# 3. Re-index with Neo4j backend
# The graph will be rebuilt in Neo4j
```

## Best Practices

### Production Deployment
1. **Always use TLS** in production (`neo4j+s://`)
2. **Set strong passwords** and rotate regularly
3. **Monitor connection pools** to prevent exhaustion
4. **Configure appropriate memory** based on graph size
5. **Regular backups** using Neo4j backup tools

### Development vs Production
```bash
# Development
NEO4J_URL=neo4j://localhost:7687
NEO4J_ENCRYPTED=false
NEO4J_BATCH_SIZE=100

# Production
NEO4J_URL=neo4j+s://prod.example.com:7687
NEO4J_ENCRYPTED=true
NEO4J_BATCH_SIZE=5000
NEO4J_MAX_CONNECTION_POOL_SIZE=200
```

### Health Checks
```python
async def health_check():
    try:
        # Check Neo4j connectivity
        await storage._init_workspace()
        
        # Verify GDS availability
        await storage._check_gds_availability()
        
        return {"status": "healthy", "backend": "neo4j"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

## Advanced Features

### Custom Cypher Queries
```python
async with storage.async_driver.session(database=storage.neo4j_database) as session:
    result = await session.run("""
        MATCH (n:Entity)-[r:RELATED]-(m:Entity)
        WHERE n.type = 'PERSON'
        RETURN n, r, m
        LIMIT 100
    """)
    
    async for record in result:
        print(record)
```

### GDS Algorithm Access
The Neo4j backend uses GDS Leiden algorithm for clustering. You can run additional GDS algorithms:

```python
async with storage.async_driver.session(database=storage.neo4j_database) as session:
    # Run PageRank
    await session.run("""
        CALL gds.pageRank.write('myGraph', {
            writeProperty: 'pagerank'
        })
    """)
```

## Support

For issues specific to Neo4j integration:
1. Check this documentation
2. Review [Neo4j documentation](https://neo4j.com/docs/)
3. Open an issue on [nano-graphrag GitHub](https://github.com/gusye1234/nano-graphrag/issues)

For Neo4j Enterprise licensing:
- Contact [Neo4j Sales](https://neo4j.com/contact-us/)