# Health Check for nano-graphrag

This directory contains end-to-end health checks for validating nano-graphrag functionality with different configurations.

## Quick Start

Run the health check with default settings:
```bash
python tests/health/run_health_check.py
```

## Configuration Options

### Storage Backends

The health check supports different storage backends through configuration files:

1. **Default (Nano VectorDB)**
   ```bash
   python tests/health/run_health_check.py --env tests/health/config_openai.env
   ```

2. **Qdrant Vector Storage**
   ```bash
   # First, start Qdrant Docker container
   docker run -p 6333:6333 -p 6334:6334 \
     -v $(pwd)/qdrant_storage:/qdrant/storage:z \
     qdrant/qdrant
   
   # Then run health check with Qdrant config
   python tests/health/run_health_check.py \
     --env tests/health/config_qdrant.env \
     --workdir .health/qdrant \
     --fresh
   ```

3. **LMStudio (Local LLM)**
   ```bash
   # Ensure LMStudio is running locally
   python tests/health/run_health_check.py --env tests/health/config_lmstudio.env
   ```

## Command Line Options

- `--env CONFIG_FILE`: Specify configuration file (e.g., `config_openai.env`, `config_qdrant.env`)
- `--workdir DIR`: Set working directory for cache (default: `.health/dickens`)
- `--fresh`: Clear working directory before starting
- `--history`: Show historical health check results
- `--mode {openai,lmstudio}`: Quick mode selection (alternative to --env)

## Testing Qdrant Integration

To test the Qdrant vector storage integration:

1. **Start Qdrant**
   ```bash
   docker run -p 6333:6333 -p 6334:6334 \
     -v $(pwd)/qdrant_storage:/qdrant/storage:z \
     qdrant/qdrant
   ```

2. **Verify Qdrant is running**
   ```bash
   curl http://localhost:6333/health
   ```

3. **Run health check with Qdrant backend**
   ```bash
   python tests/health/run_health_check.py \
     --env tests/health/config_qdrant.env \
     --workdir .health/qdrant \
     --fresh
   ```

The health check will:
- Insert test documents into Qdrant
- Build a knowledge graph
- Test query modes (local, global, naive)
- Validate reload from cache
- Report success/failure

## Configuration Files

Configuration files are located in `tests/health/` and use environment variable format:

- `config_openai.env`: OpenAI with default Nano vector storage
- `config_qdrant.env`: OpenAI with Qdrant vector storage
- `config_lmstudio.env`: Local LLM with default storage

### Key Configuration Variables

```bash
# LLM Settings
LLM_PROVIDER=openai
LLM_MODEL=gpt-5-mini

# Storage Backend
STORAGE_VECTOR_BACKEND=qdrant  # or "nano", "hnswlib"
STORAGE_GRAPH_BACKEND=networkx  # or "neo4j"

# Qdrant Specific (when using qdrant backend)
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your-api-key  # Optional, for Qdrant Cloud

# Test Settings
TEST_DATA_LINES=1000  # Number of lines to process
```

## Health Check Output

The health check validates:
1. **Document insertion**: Creates graph from test data
2. **Query modes**: Tests local, global, and naive RAG queries
3. **Persistence**: Validates reload from cached state
4. **Performance**: Tracks timing for all operations

Results are saved to `tests/health/reports/latest.json` with historical data.

## Troubleshooting

### Qdrant Connection Issues
- Ensure Docker is running
- Check port 6333 is not in use: `lsof -i :6333`
- Verify Qdrant health: `curl http://localhost:6333/health`

### Missing Dependencies
- Install Qdrant support: `pip install nano-graphrag[qdrant]`
- Install all extras: `pip install -e ".[qdrant]"`

### Performance Issues
- Reduce TEST_DATA_LINES in config file for faster testing
- Enable LLM_CACHE_ENABLED for repeated runs
- Use smaller models (gpt-5-mini) for testing

## Viewing Results

Check historical results:
```bash
python tests/health/run_health_check.py --history
```

View latest report:
```bash
cat tests/health/reports/latest.json | python -m json.tool
```