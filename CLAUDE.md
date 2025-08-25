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
   - Best Model: `gpt-4o` 
   - Cheap Model: `gpt-4o-mini` (actually uses `gpt-4.1-mini`)
   - Functions: `gpt_4o_complete()`, `gpt_4o_mini_complete()`
   - Location: `nano_graphrag/_llm.py:154-175`

2. **Azure OpenAI** 
   - Enabled via: `using_azure_openai=True`
   - Best Model: `gpt-4o` deployment
   - Cheap Model: `gpt-4o-mini` deployment  
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

#### 1. HNSWVectorStorage (Hierarchical Navigable Small World)
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

#### 2. NanoVectorDBStorage (Default)
- **Library**: nano-vectordb
- **Location**: `nano_graphrag/_storage/vdb_nanovectordb.py`
- **Features**:
  - Lightweight in-memory vector database
  - Exact nearest neighbor search
  - JSON-based persistence

#### 3. Additional Vector DB Support
- **Milvus**: Via examples
- **FAISS**: Via examples
- **Qdrant**: Via examples (in fresh fork)

### Graph Storage Systems

#### 1. NetworkXStorage (Default)
- **Library**: NetworkX
- **Location**: `nano_graphrag/_storage/gdb_networkx.py`
- **Features**:
  - In-memory graph storage
  - GraphML export/import
  - Rich graph algorithms via NetworkX
  - Community detection (Leiden algorithm)

#### 2. Neo4jStorage
- **Library**: neo4j-python-driver
- **Location**: `nano_graphrag/_storage/gdb_neo4j.py`
- **Features**:
  - Production-grade graph database
  - Cypher query support
  - Scalable and persistent

### Key-Value Storage

#### JsonKVStorage (Default)
- **Location**: `nano_graphrag/_storage/kv_json.py`
- **Purpose**: Store documents, chunks, reports, and cache
- **Namespaces**:
  - `full_docs`: Complete documents
  - `text_chunks`: Chunked text segments
  - `community_reports`: Graph community summaries
  - `llm_response_cache`: Cached LLM responses

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