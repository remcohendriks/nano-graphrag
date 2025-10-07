# CLAUDE.md - nano-graphrag Documentation

## Overview

This is the latest version of nano-graphrag, a simple and hackable GraphRAG implementation for knowledge graph-based retrieval augmented generation. This fork represents the clean, unmodified version directly from the upstream repository.

## Architecture Components

### Core Framework
- **Base Framework**: nano-graphrag v0.1.0
- **Primary Language**: Python 3.9+
- **Async Support**: Full async/await implementation using asyncio
- **Web Framework**: FastAPI (for modified version in parent directory)

### LLM Integration

#### Default LLM Providers
The system supports multiple LLM providers with hot-swappable configurations:

1. **OpenAI Models** (Default)
   - Best Model: `gpt-5` 
   - Cheap Model: `gpt-5-mini`
   - Functions: `gpt_4o_complete()`, `gpt_4o_mini_complete()`
   - Location: `nano_graphrag/_llm.py:154-175`

2. **Azure OpenAI** 
   - Enabled via: `using_azure_openai=True`
   - Best Model: `gpt-5` deployment
   - Cheap Model: `gpt-5-mini` deployment  
   - Functions: `azure_gpt_4o_complete()`, `azure_gpt_4o_mini_complete()`
   - Location: `nano_graphrag/_llm.py:259-280`

3. **Amazon Bedrock**
   - Enabled via: `using_amazon_bedrock=True`
   - Best Model ID: `us.anthropic.claude-3-sonnet-20240229-v1:0`
   - Cheap Model ID: `us.anthropic.claude-3-haiku-20240307-v1:0`
   - Dynamic function creation via factory pattern
   - Location: `nano_graphrag/_llm.py:124-151`

4. **Custom Integration Support**
   - DeepSeek models (via examples)
   - Ollama local models
   - Any OpenAI-compatible API

#### LLM Configuration
- **Max Token Sizes**: 32768 tokens (configurable)
- **Max Async Connections**: 16 concurrent requests
- **Response Caching**: Built-in LLM response caching via `llm_response_cache`
- **Retry Logic**: Tenacity-based retry with exponential backoff
- **Community Report Token Management**:
  - `community_report_token_budget_ratio`: Use portion of model capacity (default: 0.75)
  - `community_report_chat_overhead`: Reserve tokens for chat template (default: 1000)

### Embedding Systems

#### Default Embedders
1. **OpenAI Embeddings** (Default)
   - Model: `text-embedding-3-small`
   - Dimensions: 1536
   - Max Token Size: 8192
   - Function: `openai_embedding()`
   - Location: `nano_graphrag/_llm.py:207-218`

2. **Azure OpenAI Embeddings**
   - Same model as OpenAI
   - Function: `azure_openai_embedding()`
   - Location: `nano_graphrag/_llm.py:283-294`

3. **Amazon Bedrock Embeddings**
   - Model: `amazon.titan-embed-text-v2:0`
   - Dimensions: 1024
   - Function: `amazon_bedrock_embedding()`
   - Location: `nano_graphrag/_llm.py:178-204`

#### Embedding Configuration
- **Batch Processing**: 32 texts per batch
- **Max Async**: 16 concurrent embedding requests
- **Wrapped with Attributes**: Dimension and token size metadata

### Vector Storage Systems

#### 1. QdrantVectorStorage (Production-Grade, First-Class)
- **Library**: qdrant-client
- **Location**: `nano_graphrag/_storage/vdb_qdrant.py`
- **Status**: **First-class citizen** with full backup/restore support
- **Key Features**:
  - Production-grade vector search
  - Distributed and scalable
  - HTTP REST API support
  - API key authentication
  - Snapshot-based backup/restore
- **Configuration**:
  ```python
  url: "http://localhost:6333"
  api_key: Optional[str]  # For authenticated instances
  collection_name: str
  ```

#### 2. HNSWVectorStorage (Hierarchical Navigable Small World)
- **Library**: hnswlib
- **Location**: `nano_graphrag/_storage/vdb_hnswlib.py`
- **Key Features**:
  - Approximate nearest neighbor search
  - Cosine similarity metric
  - Persistent index storage
  - Metadata pickle storage
- **Configuration**:
  ```python
  ef_construction: 100  # Build-time accuracy/speed tradeoff
  M: 16                 # Number of connections per layer
  max_elements: 1000000 # Maximum vectors
  ef_search: 50         # Search-time accuracy
  num_threads: -1       # Use all CPU cores
  ```

#### 3. NanoVectorDBStorage (Default)
- **Library**: nano-vectordb
- **Location**: `nano_graphrag/_storage/vdb_nanovectordb.py`
- **Features**:
  - Lightweight in-memory vector database
  - Exact nearest neighbor search
  - JSON-based persistence

#### 4. Additional Vector DB Support
- **Milvus**: Via examples
- **FAISS**: Via examples

### Graph Storage Systems

#### 1. Neo4jStorage (Production-Grade, First-Class)
- **Library**: neo4j-python-driver
- **Location**: `nano_graphrag/_storage/gdb_neo4j.py`
- **Status**: **First-class citizen** with full backup/restore support
- **Key Features**:
  - Production-grade graph database
  - Cypher query language support
  - APOC export/import via shared Docker volumes
  - Scalable and persistent
  - Batch transaction support (connection pool optimization)
- **Configuration**:
  ```python
  url: "neo4j://localhost:7687"
  user: "neo4j"
  password: str
  database: "neo4j"
  ```

#### 2. NetworkXStorage (Default)
- **Library**: NetworkX
- **Location**: `nano_graphrag/_storage/gdb_networkx.py`
- **Features**:
  - In-memory graph storage
  - GraphML export/import
  - Rich graph algorithms via NetworkX
  - Community detection (Leiden algorithm)

### Key-Value Storage

#### 1. RedisKVStorage (Production-Grade, First-Class)
- **Library**: redis (async)
- **Location**: `nano_graphrag/_storage/kv_redis.py`
- **Status**: **First-class citizen** with full backup/restore support
- **Key Features**:
  - Production-grade key-value store
  - Async operations
  - Namespace-based organization
  - TTL support per namespace
  - JSON serialization with proper encoding
- **Namespaces**:
  - `full_docs`: Complete documents
  - `text_chunks`: Chunked text segments
  - `community_reports`: Graph community summaries
  - `llm_response_cache`: Cached LLM responses
- **Configuration**:
  ```python
  url: "redis://localhost:6379"
  namespace: str
  global_config: dict  # TTL configuration per namespace
  ```

#### 2. JsonKVStorage (Default)
- **Location**: `nano_graphrag/_storage/kv_json.py`
- **Purpose**: Store documents, chunks, reports, and cache
- **Features**:
  - File-based JSON storage
  - Simple and portable
  - No external dependencies

## Entity Extraction

### DSPy Integration
- **Module**: `TypedEntityRelationshipExtractor`
- **Location**: `nano_graphrag/entity_extraction/`
- **Features**:
  - Self-refining entity extraction
  - Typed entities and relationships
  - Compilable DSPy modules for optimization
  - Dataset generation for fine-tuning

### Extraction Process
1. Text chunking (1200 tokens default, 100 token overlap)
2. Entity and relationship extraction via DSPy
3. Entity deduplication and merging
4. Graph construction
5. Community detection
6. Report generation

## Query Modes

### 1. Local Query
- Searches within specific graph communities
- Best for detailed, specific questions
- Uses vector similarity for entity retrieval

### 2. Global Query  
- Searches across all community reports
- Best for high-level, thematic questions
- Leverages community summaries

### 3. Naive RAG Query
- Simple vector similarity search
- No graph structure utilization
- Fallback option

## Backup & Restore System (NGRAF-023)

### Overview
Production-ready unified backup/restore system for all GraphRAG storage backends with robust integrity validation.

**Status**: Production-ready (Expert-cleared after 6 rounds of code review)
**Location**: `nano_graphrag/backup/`
**API**: `nano_graphrag/api/routers/backup.py`

### Features

#### Complete Storage Backend Coverage
- **Neo4j**: Cypher export/import via APOC with shared Docker volumes
- **Qdrant**: Snapshot API with HTTP REST and authentication support
- **Redis KV**: All namespaces (docs, chunks, reports, cache)

#### Archive Format
- **Extension**: `.ngbak` (tar.gz)
- **Contents**:
  - `neo4j/` - Cypher dump files
  - `qdrant/` - Vector collection snapshots
  - `kv/` - JSON exports per namespace
  - `config/` - GraphRAG configuration
  - `manifest.json` - Metadata, statistics, and checksum

#### Integrity Validation
- **Checksum Strategy**: SHA-256 hash of payload directory contents
- **Implementation**: Excludes checksum field from manifest during hashing to avoid circular dependency
- **Verification**: Symmetric logic in backup and restore
- **Files**: External `.checksum` file + embedded in manifest
- **Self-Validating**: Archives contain complete integrity information

#### Dashboard UI
- Create backups with one click (background jobs)
- List all available backups with auto-refresh
- Download backups (.ngbak files)
- Upload and restore from file
- Delete backups with confirmation
- **Location**: `nano_graphrag/api/templates/dashboard.html` (Backups tab)

### API Endpoints

```python
POST   /api/v1/backup              # Create backup (background job)
GET    /api/v1/backup              # List all backups
POST   /api/v1/backup/restore      # Restore from uploaded file
GET    /api/v1/backup/{id}/download  # Download .ngbak archive
DELETE /api/v1/backup/{id}         # Delete backup
```

### Usage Example

```python
from nano_graphrag.backup import BackupManager
from nano_graphrag import GraphRAG

# Initialize
graphrag = GraphRAG(
    working_dir="./nano_graphrag_cache",
    # ... storage backends configuration ...
)
backup_manager = BackupManager(graphrag, backup_dir="./backups")

# Create backup
metadata = await backup_manager.create_backup()
print(f"Backup created: {metadata.backup_id}")
print(f"Size: {metadata.size_bytes} bytes")

# List backups
backups = await backup_manager.list_backups()
for backup in backups:
    print(f"{backup.backup_id}: {backup.created_at}")

# Restore backup
await backup_manager.restore_backup(backup_id="snapshot_2025-10-06T12-00-00Z")
```

### Docker Configuration

**Shared Volume for Neo4j APOC** (`docker-compose-api.yml`):
```yaml
volumes:
  neo4j_import:  # Shared between API and Neo4j containers

services:
  api:
    volumes:
      - neo4j_import:/neo4j_import
    environment:
      NEO4J_IMPORT_DIR: /neo4j_import

  neo4j:
    volumes:
      - neo4j_import:/var/lib/neo4j/import
```

### Performance

**Backup** (23MB dataset):
- Neo4j export: ~2s
- Qdrant download: ~0.2s
- Redis export: ~0.5s
- Archive creation: ~1s
- **Total: ~4s**

**Restore** (23MB dataset):
- Archive extraction: ~1s
- Neo4j restore: ~8s
- Qdrant upload: ~0.3s
- Redis restore: ~0.5s
- **Total: ~10s**

### Architecture Details

**Exporters** (`nano_graphrag/backup/exporters/`):
- `Neo4jExporter`: APOC Cypher export with shared volume coordination
- `QdrantExporter`: HTTP REST API for snapshot download/upload with auth
- `KVExporter`: JSON export with proper serialization (Redis/JSON agnostic)

**Manager** (`nano_graphrag/backup/manager.py`):
- Orchestrates backup/restore across all backends
- Handles manifest creation with payload checksum
- Archive creation and extraction
- Integrity verification

**Models** (`nano_graphrag/backup/models.py`):
- `BackupManifest`: Metadata, statistics, checksum
- `BackupMetadata`: API response format

**Utils** (`nano_graphrag/backup/utils.py`):
- `compute_directory_checksum()`: Deterministic payload hashing
- `create_archive()`, `extract_archive()`: Tar.gz operations
- `save_manifest()`, `load_manifest()`: JSON serialization

### Implementation Journey

This system underwent **6 rounds of expert code review** resolving:
- Round 1: Initial implementation
- Round 2: Checksum bugs, Qdrant API, chunks VDB, Dashboard UI (4 issues)
- Round 3: Runtime integration (9 issues)
- Round 4: Qdrant authentication, manifest checksum attempt (2 issues)
- Round 5: Checksum self-reference paradox fix
- Round 6: Manifest timing bug fix → **Expert cleared**

**Final Status**: All critical issues resolved, production-ready

### Testing

**Test Coverage**: 15 tests passing
- `tests/backup/test_manager.py`: Core backup/restore logic (6 tests)
- `tests/backup/test_router_logic.py`: API integration (5 tests)
- `tests/backup/test_utils.py`: Utility functions (4 tests)
- **Regression test included**: Validates checksum timing (CODEX-012)

### Security Considerations

- ✅ API key authentication for Qdrant
- ✅ XSS protection in dashboard UI
- ✅ File validation (.ngbak extension)
- ✅ Checksum integrity verification
- ✅ No credentials stored in backup manifest

## Tokenization Support

The fresh fork includes improved tokenization:
- **tiktoken**: For OpenAI models (default)
- **Hugging Face**: For custom models
- Configurable via `tokenizer_type` parameter

## Modified Version Differences

The modified version in `./nano-graphrag` includes:

### 1. DeepSeek Integration
- Custom DeepSeek model functions
- Streaming support for DeepSeek
- Executive order knowledge injection
- Located in: `deepseek.py`

### 2. FastAPI Application
- REST API endpoints for document insertion
- Streaming query responses  
- Federal Register API integration
- Redis caching layer
- Located in: `app.py`

### 3. Redis Caching
- Optional Redis integration (`ENABLE_REDIS_CACHE`)
- Query result caching with 12-hour TTL
- Rate limiting per user
- Cache invalidation endpoints

### 4. Production Features
- API token authentication
- CORS middleware
- Docker support
- SSL/TLS configuration
- Multi-instance load balancing

## Environment Variables

```bash
# LLM Configuration
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=sk-...
AZURE_OPENAI_API_KEY=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1

# Community Report Token Management
COMMUNITY_REPORT_TOKEN_BUDGET_RATIO=0.75  # Use 75% of model capacity
COMMUNITY_REPORT_CHAT_OVERHEAD=1000       # Reserve tokens for chat template

# DeepSeek Models (modified version)
DEEPSEEK_GREAT_MODEL=deepseek-reasoner
DEEPSEEK_GOOD_MODEL=deepseek-chat

# Storage
NEO4J_URL=neo4j://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...

# Redis (modified version)
ENABLE_REDIS_CACHE=false
REDIS_URL=redis://redis:6379

# API (modified version)
API_TOKEN=...
```

## Refactoring Recommendations

### 1. LLM Provider Abstraction
Create a unified LLM interface:
```python
class BaseLLMProvider:
    async def complete(prompt, **kwargs)
    async def stream(prompt, **kwargs)
    async def embed(texts)
```

### 2. Storage Layer Consolidation
Implement storage factory pattern:
```python
class StorageFactory:
    @staticmethod
    def create_vector_storage(type: str, **kwargs)
    @staticmethod
    def create_graph_storage(type: str, **kwargs)
```

### 3. Configuration Management
Move from dataclass to configuration files:
```yaml
llm:
  provider: deepseek
  model: deepseek-chat
  max_tokens: 32768
  
embedding:
  provider: openai
  model: text-embedding-3-small
  
storage:
  vector: hnswlib
  graph: networkx
```

### 4. Modular Entity Extraction
Separate extraction strategies:
- DSPy-based extraction
- Prompt-based extraction
- Custom extractors

### 5. Query Pipeline Enhancement
- Add query rewriting
- Implement hybrid search
- Support multi-hop reasoning

## Testing

The fresh fork includes comprehensive tests:
- Entity extraction tests
- Storage backend tests
- LLM integration tests
- JSON parsing tests
- Graph operations tests

Located in: `tests/` directory

## Dependencies

Core dependencies (requirements.txt):
- future>=1.0.0
- openai
- tiktoken
- networkx
- graspologic
- nano-vectordb
- hnswlib
- xxhash
- tenacity
- dspy-ai
- neo4j
- aioboto3

Additional in modified version:
- fastapi
- uvicorn
- redis
- httpx
- pydantic
- python-dotenv

## Performance Optimizations

1. **Async Everything**: Full async/await support
2. **Batched Operations**: Embedding and LLM calls
3. **Caching**: Multiple levels (LLM, embeddings, results)
4. **Index Persistence**: HNSW indexes saved to disk
5. **Parallel Processing**: Concurrent chunk processing
6. **Connection Pooling**: Reused client connections

## Best Practices

1. **Chunking**: Adjust chunk size based on document type
2. **Model Selection**: Use cheap models for extraction, best for queries
3. **Storage Choice**: HNSW for large-scale, NanoDB for prototyping
4. **Caching**: Enable LLM cache for development
5. **Community Size**: Keep max_graph_cluster_size reasonable (10-20)
6. **Token Management**: For local LLMs with smaller context windows:
   - Set `COMMUNITY_REPORT_TOKEN_BUDGET_RATIO=0.5` for very conservative usage
   - Increase `COMMUNITY_REPORT_CHAT_OVERHEAD` if using complex chat templates
   - Monitor logs for token truncation warnings

## Troubleshooting

### Token Limit Errors
If you encounter errors like "Token limit exceeded" during community report generation:

1. **Symptoms**:
   - Error: `Trying to keep the first X tokens when context overflows`
   - Community processing fails partway through (e.g., at 70/300 communities)

2. **Solutions**:
   - Reduce `COMMUNITY_REPORT_TOKEN_BUDGET_RATIO` to 0.5 or lower
   - Increase `COMMUNITY_REPORT_CHAT_OVERHEAD` to 2000 or more
   - Reduce `max_graph_cluster_size` to create smaller communities
   - Use a model with larger context window

3. **Example Configuration for 32k Context Models**:
   ```bash
   COMMUNITY_REPORT_TOKEN_BUDGET_RATIO=0.5  # Conservative 50% usage
   COMMUNITY_REPORT_CHAT_OVERHEAD=2000      # Large safety margin
   LLM_MAX_TOKENS=32000                     # Your model's limit
   ```

## Migration Path

To refactor from modified to clean version:
1. Extract business logic from `app.py`
2. Create provider interfaces for LLMs
3. Implement storage adapters
4. Separate API layer from core logic
5. Add comprehensive configuration management
6. Implement proper dependency injection

### When updating infrastructure:
- ive added a dir ./llm/nano-graphrag/tickets - which is going to serve as project tickets store. inside, markdown documents reside, each detailing a JIRA-style ticket resembling a development/code change into the project. except for user story and detailed code change proposal, it should also include feature branch name, and details what the pull request should contain/
- all the jira-style tickets you are to make, are aimed for claude code to implement. hence, you can detail it such for claude code easy to understand. you can leave out strict details like story points, implementation time paths, you can just stick to the technicalities.
- with defining jira tickets, add definitions-of-done, which should be unit tests with pytorch, unless other suggested or specified by the user.
- aim for least complexity and good user-readability. the repository contains novel techniques with complex programming. ensure python typings are in order. add comments conservatively, mainly to explain function uses and hard-to-understand complex items. do NOT use comments to denote changes from the past. do NOT use comments where typings suffice.
- in unit testing llm-depdendent programming, you are allowed to use an openai mini model for testing, where applicable
- the openai models available are gpt-5 and gpt-5-mini
- use context7 mcp copiously to inform yourself about the latest package definitions and api's
- for tests, put testing files in a `tests` folder adjacent to the file to be tested

## Module Structure (Post NGRAF-006 Refactoring)

The codebase has been refactored to decompose the monolithic `_op.py` file into focused modules:

### Core Operation Modules
- **`_chunking.py`**: Text chunking operations
  - `chunking_by_token_size`: Token-based text chunking
  - `chunking_by_separators`: Separator-based text chunking  
  - `get_chunks`: Process documents into chunks
  - `get_chunks_v2`: Clean API for chunking

- **`_extraction.py`**: Entity and relationship extraction
  - `extract_entities`: Main entity extraction with storage
  - `extract_entities_from_chunks`: Entity extraction without side effects
  - Helper functions for entity/relationship processing

- **`_community.py`**: Community detection and report generation
  - `generate_community_report`: Generate hierarchical community reports
  - `summarize_community`: Summarize single community
  - Community packing and description functions

- **`_query.py`**: Query operations
  - `local_query`: Execute local graph query
  - `global_query`: Execute global community query
  - `naive_query`: Execute simple RAG query
  - Helper functions for finding related communities and entities

### Migration from Legacy Code
- **`_op.py`**: Now a backward compatibility layer that re-exports from the new modules
- Shows deprecation warning when imported
- Migrate imports from `_op.py` to specific modules for better performance and clarity

### Import Examples
```python
# Old way (deprecated)
from nano_graphrag._op import local_query

# New way (recommended)
from nano_graphrag._query import local_query
from nano_graphrag._chunking import chunking_by_token_size
from nano_graphrag._extraction import extract_entities
from nano_graphrag._community import generate_community_report
```