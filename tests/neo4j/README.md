# Neo4j Testing Environment

This directory contains the Docker setup for testing nano-graphrag with Neo4j Enterprise Edition including Graph Data Science (GDS).

## Prerequisites

- Docker and Docker Compose installed
- At least 2GB of available RAM for Neo4j

## Starting Neo4j

```bash
# Start Neo4j in the background
docker-compose up -d

# View logs to monitor startup
docker-compose logs -f neo4j

# Wait for the message: "Started"
```

## Verifying Neo4j is Ready

```bash
# Check health status
docker-compose ps

# Test connection with cypher-shell
docker exec -it nano-graphrag-neo4j cypher-shell -u neo4j -p testpassword "RETURN 1"
```

## Running Health Check

Once Neo4j is running:

```bash
cd ../..  # Go back to project root
python tests/health/run_health_check.py --env tests/health/config_neo4j.env
```

## Accessing Neo4j Browser

Open http://localhost:7474 in your browser:
- Username: `neo4j`
- Password: `testpassword`

## Stopping Neo4j

```bash
# Stop and remove containers
docker-compose down

# Stop and remove containers AND volumes (full cleanup)
docker-compose down -v
```

## Troubleshooting

### Neo4j won't start
- Check Docker has enough memory allocated (at least 2GB)
- Check ports 7474 and 7687 are not in use

### Connection refused
- Wait for Neo4j to fully start (check logs)
- Verify Neo4j is healthy: `docker-compose ps`

### GDS not available
- Neo4j Enterprise with GDS is required for clustering
- The docker image includes GDS by default for testing

## License Note

Neo4j Enterprise Edition is used here for testing purposes only. Production use requires a valid license.