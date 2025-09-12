# Docker Setup for Neo4j with nano-graphrag

## Quick Start

1. **Start Neo4j Enterprise with GDS**:
```bash
docker-compose -f docker-compose-neo4j.yml up -d
```

2. **Verify Neo4j is running**:
```bash
# Check container status
docker-compose -f docker-compose-neo4j.yml ps

# Check logs
docker-compose -f docker-compose-neo4j.yml logs neo4j

# Access Neo4j Browser
open http://localhost:7474
```

3. **Configure nano-graphrag**:
```bash
# Copy example environment file
cp .env.neo4j.example .env.neo4j

# Edit with your password (must match docker-compose)
# The default password is: your-secure-password-change-me
```

4. **Use in Python**:
```python
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig
import os

# Load environment variables
from dotenv import load_dotenv
load_dotenv('.env.neo4j')

config = GraphRAGConfig(
    storage={
        "graph_backend": "neo4j",
        "neo4j_url": os.getenv("NEO4J_URL"),
        "neo4j_username": os.getenv("NEO4J_USERNAME"),
        "neo4j_password": os.getenv("NEO4J_PASSWORD"),
    }
)

rag = GraphRAG(config=config)
```

## Important Notes

### Enterprise Edition Required
This setup uses Neo4j Enterprise Edition which requires a license for production use. The Graph Data Science (GDS) library is **only available in Enterprise Edition**.

### Default Credentials
⚠️ **Security Warning**: The default password is `your-secure-password-change-me`. You MUST change this before using in production:

1. Update the password in `docker-compose-neo4j.yml`
2. Update the password in your `.env.neo4j` file
3. Restart the container: `docker-compose -f docker-compose-neo4j.yml restart`

### Memory Configuration
The default memory settings are:
- Heap: 2-4GB
- Page Cache: 2GB

For production workloads, adjust these in `docker-compose-neo4j.yml` based on your system resources and graph size.

### Data Persistence
All Neo4j data is persisted in Docker volumes:
- `neo4j_data`: Database files
- `neo4j_logs`: Log files
- `neo4j_import`: Import directory
- `neo4j_plugins`: Additional plugins

To completely reset Neo4j:
```bash
docker-compose -f docker-compose-neo4j.yml down -v
```

## Verification

### Check GDS Installation
Access Neo4j Browser at http://localhost:7474 and run:
```cypher
CALL gds.version()
```

You should see the GDS version (2.5.0 or later).

### Test Connection
```python
from nano_graphrag._storage.gdb_neo4j import Neo4jStorage

storage = Neo4jStorage(
    namespace="test",
    global_config={
        "addon_params": {
            "neo4j_url": "neo4j://localhost:7687",
            "neo4j_auth": ("neo4j", "your-secure-password-change-me"),
            "neo4j_database": "neo4j"
        },
        "working_dir": "./test"
    }
)

# This will verify GDS is available
await storage._check_gds_availability()
```

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker-compose -f docker-compose-neo4j.yml logs neo4j

# Common issues:
# - Port 7687 or 7474 already in use
# - Insufficient memory
# - Invalid configuration
```

### GDS Not Available
If GDS is not installed:
1. Ensure you're using the Enterprise image: `neo4j:5-enterprise`
2. Check plugins are specified correctly in environment
3. Restart the container

### Connection Refused
1. Ensure container is running: `docker ps`
2. Check ports are exposed: 7687 for Bolt, 7474 for Browser
3. Verify firewall settings if accessing remotely

### Performance Issues
1. Increase memory allocation in docker-compose
2. Monitor with: `docker stats nano-graphrag-neo4j`
3. Check Neo4j metrics in Browser

## Production Deployment

For production use:

1. **Use TLS**: Configure SSL certificates and use `neo4j+s://` URLs
2. **Set Strong Passwords**: Use secure password generation
3. **Resource Limits**: Set appropriate CPU and memory limits
4. **Monitoring**: Enable metrics export for Prometheus/Grafana
5. **Backups**: Implement regular backup strategy
6. **License**: Obtain valid Neo4j Enterprise license

See the [Neo4j Production Guide](./storage/neo4j_production.md) for detailed configuration options.