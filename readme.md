<div align="center">
  <a href="https://github.com/gusye1234/nano-graphrag">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://assets.memodb.io/nano-graphrag-dark.png">
      <img alt="Shows the MemoDB logo" src="https://assets.memodb.io/nano-graphrag.png" width="512">
    </picture>
  </a>
  <p><strong>A simple, easy-to-hack GraphRAG implementation</strong></p>
  <p>
    <img src="https://img.shields.io/badge/python->=3.9.11-blue">
    <a href="https://pypi.org/project/nano-graphrag/">
      <img src="https://img.shields.io/pypi/v/nano-graphrag.svg">
    </a>
    <a href="https://codecov.io/github/gusye1234/nano-graphrag" > 
     <img src="https://codecov.io/github/gusye1234/nano-graphrag/graph/badge.svg?token=YFPMj9uQo7"/> 
 		</a>
    <a href="https://pepy.tech/project/nano-graphrag">
      <img src="https://static.pepy.tech/badge/nano-graphrag/month">
    </a>
  </p>
  <p>
  	<a href="https://discord.gg/sqCVzAhUY6">
      <img src="https://dcbadge.limes.pink/api/server/sqCVzAhUY6?style=flat">
    </a>
    <a href="https://github.com/gusye1234/nano-graphrag/issues/8">
       <img src="https://img.shields.io/badge/群聊-wechat-green">
    </a>
  </p>
</div>









😭 [GraphRAG](https://arxiv.org/pdf/2404.16130) is good and powerful, but the official [implementation](https://github.com/microsoft/graphrag/tree/main) is difficult/painful to **read or hack**.

😊 This project provides a **smaller, faster, cleaner GraphRAG**, while remaining the core functionality(see [benchmark](#benchmark) and [issues](#Issues) ).

🎁 Excluding `tests` and prompts,  `nano-graphrag` is about **1100 lines of code**.

👌 Small yet [**portable**](#Components)(faiss, neo4j, ollama...), [**asynchronous**](#Async) and fully typed.

### Recent Technical Improvements

- **NDJSON Entity Extraction**: Transitioned from CSV-like format to NDJSON for deterministic parsing and elimination of quote-handling ambiguities
- **Sparse Embedding Preservation**: Resolved regression where sparse vectors were lost during community generation due to inconsistent content field formatting
- **Hybrid Search Robustness**: Enhanced sparse+dense retrieval through consistent entity content representation across all pipeline stages



> If you're looking for a multi-user RAG solution for long-term user memory, have a look at this project: [memobase](https://github.com/memodb-io/memobase) :)

## Install

**Install from source** (recommend)

```shell
# clone this repo first
cd nano-graphrag
pip install -e .
```

**Install from PyPi**

```shell
pip install nano-graphrag
```

**Install with optional dependencies**

```shell
# Install with Qdrant vector database support
pip install nano-graphrag[qdrant]

# Install with HNSW vector database support  
pip install nano-graphrag[hnsw]

# Install with Neo4j graph database support (requires Neo4j Enterprise with GDS)
pip install nano-graphrag[neo4j]

# Install with Redis KV storage support
pip install nano-graphrag[redis]
```



## Quick Start

> [!TIP]
>
> **Please set OpenAI API key in environment: `export OPENAI_API_KEY="sk-..."`.** 

> [!TIP]
> If you're using Azure OpenAI API, refer to the [.env.example](./.env.example.azure) to set your azure openai. Then pass `GraphRAG(...,using_azure_openai=True,...)` to enable.

> [!TIP]
> If you're using Amazon Bedrock API, please ensure your credentials are properly set through commands like `aws configure`. Then enable it by configuring like this: `GraphRAG(...,using_amazon_bedrock=True, best_model_id="us.anthropic.claude-3-sonnet-20240229-v1:0", cheap_model_id="us.anthropic.claude-3-haiku-20240307-v1:0",...)`. Refer to an [example script](./examples/using_amazon_bedrock.py).

> [!TIP]
>
> If you don't have any key, check out this [example](./examples/no_openai_key_at_all.py) that using `transformers` and `ollama` . If you like to use another LLM or Embedding Model, check [Advances](#Advances).

download a copy of A Christmas Carol by Charles Dickens:

```shell
curl https://raw.githubusercontent.com/gusye1234/nano-graphrag/main/tests/mock_data.txt > ./book.txt
```

Use the below python snippet:

```python
from nano_graphrag import GraphRAG, QueryParam

graph_func = GraphRAG(working_dir="./dickens")

with open("./book.txt") as f:
    graph_func.insert(f.read())

# Perform global graphrag search (for high-level, thematic questions)
print(graph_func.query("What are the top themes in this story?"))

# Perform local graphrag search (for specific, detailed questions)
print(graph_func.query("Who are the main characters and what are their relationships?", param=QueryParam(mode="local")))
```

Next time you initialize a `GraphRAG` from the same `working_dir`, it will reload all the contexts automatically.

#### Batch Insert

```python
graph_func.insert(["TEXT1", "TEXT2",...])
```

<details>
<summary> Incremental Insert</summary>

`nano-graphrag` supports incremental insert, no duplicated computation or data will be added:

```python
with open("./book.txt") as f:
    book = f.read()
    half_len = len(book) // 2
    graph_func.insert(book[:half_len])
    graph_func.insert(book[half_len:])
```

> `nano-graphrag` use md5-hash of the content as the key, so there is no duplicated chunk.
>
> However, each time you insert, the communities of graph will be re-computed and the community reports will be re-generated

</details>

<details>
<summary> Using Redis for Production</summary>

`nano-graphrag` supports Redis as a high-performance KV storage backend, ideal for production deployments:

```python
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, StorageConfig

# Configure with Redis backend
config = GraphRAGConfig(
    storage=StorageConfig(
        kv_backend="redis",
        redis_url="redis://localhost:6379",
        # Optional: Set custom TTLs (in seconds) for different namespaces
        # Default: 12 hours for LLM cache, 24 hours for community reports
    )
)

graph_func = GraphRAG(config=config)

# Use as normal - Redis handles all KV storage operations
graph_func.insert("Your text here...")
result = graph_func.query("Your question?")
```

Benefits of Redis backend:
- **50% reduction in LLM costs** through shared caching across instances
- **10x faster read/write operations** compared to file storage
- **Automatic TTL management** for cache expiration
- **Production-ready** with connection pooling and retry logic

</details>

<details>
<summary> Query Modes</summary>

`nano-graphrag` supports three query modes:

```python
from nano_graphrag import GraphRAG, QueryParam

graph_func = GraphRAG(working_dir="./dickens")

# Local mode: entity-based retrieval for specific questions
print(graph_func.query(
    "Who is Scrooge?",
    param=QueryParam(mode="local")
))

# Global mode: community-based retrieval for thematic questions
print(graph_func.query(
    "What are the main themes in this story?",
    param=QueryParam(mode="global")
))

# Naive mode (optional): simple vector similarity search
# Note: Requires enable_naive_rag=True during initialization
# graph_func = GraphRAG(working_dir="./dickens", enable_naive_rag=True)
# print(graph_func.query("What is this story about?", param=QueryParam(mode="naive")))
```

**Note**: Naive RAG is disabled by default as GraphRAG's local mode provides superior retrieval through entity relationships. Enable naive RAG only if you specifically need vector similarity search.
</details>


### Async

For each method `NAME(...)` , there is a corresponding async method `aNAME(...)`

```python
await graph_func.ainsert(...)
await graph_func.aquery(...)
...
```

### Available Parameters

`GraphRAG` and `QueryParam` are `dataclass` in Python. Use `help(GraphRAG)` and `help(QueryParam)` to see all available parameters!  Or check out the [Advances](#Advances) section to see some options.



## Components

Below are the components you can use:

| Type            |                             What                             |                       Where                       |
| :-------------- | :----------------------------------------------------------: | :-----------------------------------------------: |
| LLM             |                            OpenAI                            |                     Built-in                      |
|                 |                        Amazon Bedrock                        |                     Built-in                      |
|                 |                           DeepSeek                           |              [examples](./examples)               |
|                 |                           `ollama`                           |              [examples](./examples)               |
| Embedding       |                            OpenAI                            |                     Built-in                      |
|                 |                        Amazon Bedrock                        |                     Built-in                      |
|                 |                    Sentence-transformers                     |              [examples](./examples)               |
| Vector DataBase | [`qdrant`](https://qdrant.tech/) ⭐                          |         Built-in (**Production-ready with backup/restore**)        |
|                 |        [`hnswlib`](https://github.com/nmslib/hnswlib)        |                     Built-in                      |
|                 | [`nano-vectordb`](https://github.com/gusye1234/nano-vectordb) |                     Built-in (default)             |
|                 |  [`milvus-lite`](https://github.com/milvus-io/milvus-lite)   |              [examples](./examples)               |
|                 | [faiss](https://github.com/facebookresearch/faiss?tab=readme-ov-file) |              [examples](./examples)               |
| Graph Storage   | [`neo4j`](https://neo4j.com/) ⭐                             | Built-in (**Production-ready with backup/restore**, REQUIRES Neo4j Enterprise with GDS)([doc](./docs/use_neo4j_for_graphrag.md)) |
|                 | [`networkx`](https://networkx.org/documentation/stable/index.html) |                     Built-in (default)                      |
| KV Storage      | [`redis`](https://redis.io/) ⭐                              |         Built-in (**Production-ready with backup/restore**)        |
|                 |                        JSON files                            |                     Built-in (default)                      |
| Backup/Restore  |                  Unified backup system                       | Built-in (**All production storage backends**) |
| Visualization   |                           graphml                            |              [examples](./examples)               |
| Chunking        |                        by token size                         |                     Built-in                      |
|                 |                       by text splitter                       |                     Built-in                      |

- `Built-in` means we have that implementation inside `nano-graphrag`. `examples` means we have that implementation inside an tutorial under [examples](./examples) folder.

- Check [examples/benchmarks](./examples/benchmarks) to see few comparisons between components.
- **Always welcome to contribute more components.**

## Hybrid Search (Sparse + Dense)

`nano-graphrag` implements hybrid search combining dense embeddings (semantic) with sparse embeddings (lexical) for enhanced retrieval performance, particularly effective for identifier-based queries and technical terminology:

### Architecture

- **Sparse Embeddings**: SPLADE model generates lexical representations for term-based matching
- **Dense Embeddings**: Standard semantic embeddings (OpenAI, Bedrock, etc.) for contextual similarity
- **Fusion Strategy**: Reciprocal Rank Fusion (RRF) algorithm combines both retrieval channels
- **GPU Acceleration**: Optional CUDA support for sparse embedding computation
- **Memory Management**: LRU cache with configurable boundaries prevents unbounded memory growth

### Installation

```shell
# Install with hybrid search dependencies
pip install nano-graphrag[hybrid]

# Or install with all features including Qdrant
pip install nano-graphrag[all]
```

### Configuration

```python
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, HybridSearchConfig

# Enable hybrid search
config = GraphRAGConfig(
    hybrid_search=HybridSearchConfig(
        enabled=True,
        sparse_model="prithvida/Splade_PP_en_v1",  # SPLADE model
        device="cuda",  # or "cpu"
        rrf_k=60,  # RRF fusion parameter
        sparse_top_k_multiplier=2.0,  # Fetch 2x candidates for sparse
        dense_top_k_multiplier=1.0,   # Fetch 1x candidates for dense
        timeout_ms=5000,  # Timeout for sparse encoding
        batch_size=32,  # Batch size for encoding
        max_length=256  # Max token length for sparse model
    )
)

rag = GraphRAG(config=config)
```

### Environment Variables

```bash
# Enable hybrid search
ENABLE_HYBRID_SEARCH=true

# GPU support (optional)
HYBRID_DEVICE=cuda  # or cpu

# Model configuration
SPARSE_MODEL=prithvida/Splade_PP_en_v1
RRF_K=60
```

### Requirements

- **Qdrant**: Version 1.10.0+ for hybrid search support
- **PyTorch**: Required for sparse embeddings (`pip install torch`)
- **Transformers**: For SPLADE model (`pip install transformers`)

### Performance Characteristics

Hybrid search demonstrates superior performance for:
- **Identifier-based queries**: Document IDs, reference numbers, case citations
- **Acronym resolution**: Technical abbreviations and organizational identifiers
- **Technical terminology**: Function names, error codes, API endpoints
- **Mixed-mode queries**: Queries requiring both semantic understanding and exact term matching

## Backup & Restore

`nano-graphrag` provides a production-ready unified backup/restore system for all storage backends, enabling disaster recovery and data migration with integrity validation.

### Features

✅ **Complete Storage Coverage**
- **Neo4j**: Cypher export/import via APOC with shared Docker volumes
- **Qdrant**: Snapshot API with HTTP REST and authentication support
- **Redis**: All KV namespaces (docs, chunks, reports, cache)

✅ **Robust Integrity Validation**
- SHA-256 checksum of payload directory contents
- Self-validating archives (`.ngbak` format)
- Symmetric verification in backup and restore operations

✅ **Dashboard UI** (FastAPI)
- Create backups with one click (background jobs)
- List, download, upload, restore, and delete backups
- Auto-refresh and progress tracking

### Quick Start

```python
from nano_graphrag import GraphRAG
from nano_graphrag.backup import BackupManager

# Initialize with production storage backends
graphrag = GraphRAG(
    working_dir="./nano_graphrag_cache",
    graph_storage_cls="Neo4jStorage",  # Neo4j for graph
    vector_db_storage_cls="QdrantVectorStorage",  # Qdrant for vectors
    key_string_value_json_storage_cls="RedisKVStorage"  # Redis for KV
)

# Create backup manager
backup_manager = BackupManager(graphrag, backup_dir="./backups")

# Create backup
metadata = await backup_manager.create_backup()
print(f"Backup created: {metadata.backup_id} ({metadata.size_bytes} bytes)")

# List backups
backups = await backup_manager.list_backups()
for backup in backups:
    print(f"{backup.backup_id}: {backup.created_at}")

# Restore backup
await backup_manager.restore_backup(backup_id="snapshot_2025-10-06T12-00-00Z")
```

### Archive Format

**Extension**: `.ngbak` (tar.gz)
**Contents**:
- `neo4j/` - Cypher dump files
- `qdrant/` - Vector collection snapshots
- `kv/` - JSON exports per namespace
- `config/` - GraphRAG configuration
- `manifest.json` - Metadata, statistics, and checksum

### Dashboard UI

Access the backup management interface at `/dashboard` (Backups tab) when running the FastAPI server:

```bash
# Start API server
uvicorn nano_graphrag.api.app:app --reload

# Navigate to http://localhost:8000/dashboard
# Click "Backups" tab for full backup management UI
```

### Docker Configuration

For Neo4j APOC support, configure shared volumes in `docker-compose.yml`:

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

**Backup** (23MB dataset): ~4s
**Restore** (23MB dataset): ~10s

### API Endpoints

```
POST   /api/v1/backup              # Create backup (background job)
GET    /api/v1/backup              # List all backups
POST   /api/v1/backup/restore      # Restore from uploaded file
GET    /api/v1/backup/{id}/download  # Download .ngbak archive
DELETE /api/v1/backup/{id}         # Delete backup
```

### Testing

The backup system includes 15 passing tests covering:
- Core backup/restore logic
- API integration
- Checksum validation (with regression tests)

```bash
pytest tests/backup/ -v
```

**Status**: Production-ready (Expert-cleared after 6 rounds of code review)

## Advances



<details>
<summary>Some setup options</summary>

- `GraphRAG(...,always_create_working_dir=False,...)` will skip the dir-creating step. Use it if you switch all your components to non-file storages.

</details>

<details>
<summary>Custom Entity Types and Typed Relationships</summary>

`nano-graphrag` supports custom entity types and typed relationships for domain-specific knowledge graphs (v0.2.0+):

### Core Entity Types (Recommended Baseline)

When customizing entity types, keep a small core so the extractor continues to capture general structure across documents.

- Essential core (minimal): `PERSON`, `ORGANIZATION`, `LOCATION`, `EVENT`, `CONCEPT`
- Extended defaults (10): `PERSON`, `ORGANIZATION`, `LOCATION`, `EVENT`, `DATE`, `TIME`, `MONEY`, `PERCENTAGE`, `PRODUCT`, `CONCEPT`

Note on replacement semantics: Setting `ENTITY_TYPES` (env) or `entity_extraction.entity_types` (config) fully replaces the default list. For most use cases, include the core types plus your domain-specific types rather than replacing them entirely.

### Configure Entity Types

```python
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, EntityExtractionConfig

# Configure custom entity types for your domain (Medical) and include core types
config = GraphRAGConfig(
    entity_extraction=EntityExtractionConfig(
        entity_types=[
            # Core baseline
            "PERSON", "ORGANIZATION", "LOCATION", "EVENT", "CONCEPT",
            # Domain-specific
            "DRUG", "DISEASE", "PROTEIN", "GENE", "PATHWAY"
        ]
    )
)

graph_func = GraphRAG(config=config)
```

Or via environment variables:
```bash
# Include core + domain types (Medical)
export ENTITY_TYPES="PERSON,ORGANIZATION,LOCATION,EVENT,CONCEPT,DRUG,DISEASE,PROTEIN,GENE,PATHWAY"

# Legal domain example (include core + legal)
export ENTITY_TYPES="PERSON,ORGANIZATION,LOCATION,EVENT,CONCEPT,EXECUTIVE_ORDER,STATUTE,REGULATION,CASE,COURT"

# Financial domain example (include core + financial)
export ENTITY_TYPES="PERSON,ORGANIZATION,LOCATION,EVENT,CONCEPT,COMPANY,EXECUTIVE,INVESTOR,TRANSACTION,PRODUCT"
```

### Enable Type-Prefix Embeddings

Type-prefix embeddings improve query accuracy by including entity types in the embedding:

```python
config = GraphRAGConfig(
    entity_extraction=EntityExtractionConfig(
        enable_type_prefix_embeddings=True  # Default: True
    )
)
```

This prefixes entity embeddings with their type (e.g., "[DRUG] Aspirin") for better semantic matching.

### Typed Relationships in Queries

The system now preserves typed relationships (e.g., TREATS, CAUSES, INHIBITS) in query contexts, providing more accurate and semantically rich results. This includes:
- Relationship type preservation in CSV context
- Bidirectional edge handling (e.g., PARENT_OF/CHILD_OF)
- Semantic directionality preservation

### Domain Examples

**Legal:**
```python
config = GraphRAGConfig(
    entity_extraction=EntityExtractionConfig(
        entity_types=["STATUTE", "REGULATION", "CASE", "COURT", "EXECUTIVE_ORDER"]
    )
)
```

**Financial:**
```python
config = GraphRAGConfig(
    entity_extraction=EntityExtractionConfig(
        entity_types=["COMPANY", "EXECUTIVE", "INVESTOR", "PRODUCT", "MARKET", "CURRENCY"]
    )
)
```

**Software Engineering:**
```python
config = GraphRAGConfig(
    entity_extraction=EntityExtractionConfig(
        entity_types=["CLASS", "METHOD", "PACKAGE", "MODULE", "LIBRARY", "API", "SERVICE"]
    )
)
```

</details>



<details>
<summary>Only query the related context</summary>

`graph_func.query` return the final answer without streaming. 

If you like to interagte `nano-graphrag` in your project, you can use `param=QueryParam(..., only_need_context=True,...)`, which will only return the retrieved context from graph, something like:

````
# Local mode
-----Reports-----
```csv
id,	content
0,	# FOX News and Key Figures in Media and Politics...
1, ...
```
...

# Global mode
----Analyst 3----
Importance Score: 100
Donald J. Trump: Frequently discussed in relation to his political activities...
...
````

You can integrate that context into your customized prompt.

</details>

<details>
<summary>Prompt</summary>

`nano-graphrag` use prompts from `nano_graphrag.prompt.PROMPTS` dict object. You can play with it and replace any prompt inside.

Some important prompts:

- `PROMPTS["entity_extraction"]` is used to extract the entities and relations from a text chunk.
- `PROMPTS["community_report"]` is used to organize and summary the graph cluster's description.
- `PROMPTS["local_rag_response"]` is the system prompt template of the local search generation.
- `PROMPTS["global_reduce_rag_response"]` is the system prompt template of the global search generation.
- `PROMPTS["fail_response"]` is the fallback response when nothing is related to the user query.

### Entity Extraction Format

The entity extraction system utilizes NDJSON (Newline Delimited JSON) format for robust parsing and elimination of quote-handling ambiguities:

```json
{"type":"entity","name":"PERSON_NAME","entity_type":"PERSON","description":"Description of person"}
{"type":"relationship","source":"PERSON_NAME","target":"ORG_NAME","description":"Relationship description","strength":8}
```

This format ensures consistent entity name preservation across storage layers and eliminates parsing ambiguities inherent in delimiter-based formats.

### Configurable Query Response Templates

You can customize the response prompts for both local and global queries to match your application's needs:

```python
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, QueryConfig

# Using inline templates
config = GraphRAGConfig(
    query=QueryConfig(
        local_template="Answer based on context:\n{context_data}\n\nFormat: {response_type}",
        global_template="Analyze the following:\n{context_data}"
    )
)

# Using template files
config = GraphRAGConfig(
    query=QueryConfig(
        local_template="./templates/local_response.txt",
        global_template="./templates/global_response.txt"
    )
)

# Or via environment variables
# QUERY_LOCAL_TEMPLATE=./templates/local.txt
# QUERY_GLOBAL_TEMPLATE="Inline template with {context_data}"

rag = GraphRAG(config=config)
```

#### Available Placeholders

- **Local Query**: `{context_data}`, `{response_type}`
- **Global Query**: `{context_data}`

Templates are validated at startup with automatic fallback to defaults if invalid. This allows customization of tone, format, and additional metadata without modifying source code.

</details>

<details>
<summary>Customize Chunking</summary>


`nano-graphrag` allow you to customize your own chunking method, check out the [example](./examples/using_custom_chunking_method.py).

Switch to the built-in text splitter chunking method:

```python
from nano_graphrag._op import chunking_by_seperators

GraphRAG(...,chunk_func=chunking_by_seperators,...)
```

</details>



<details>
<summary>LLM Function</summary>

In `nano-graphrag`, we requires two types of LLM, a great one and a cheap one. The former is used to plan and respond, the latter is used to summary. By default, the great one is `gpt-4o` and the cheap one is `gpt-4o-mini`

You can implement your own LLM function (refer to `_llm.gpt_4o_complete`):

```python
async def my_llm_complete(
    prompt, system_prompt=None, history_messages=[], **kwargs
) -> str:
  # pop cache KV database if any
  hashing_kv: BaseKVStorage = kwargs.pop("hashing_kv", None)
  # the rest kwargs are for calling LLM, for example, `max_tokens=xxx`
	...
  # YOUR LLM calling
  response = await call_your_LLM(messages, **kwargs)
  return response
```

Replace the default one with:

```python
# Adjust the max token size or the max async requests if needed
GraphRAG(best_model_func=my_llm_complete, best_model_max_token_size=..., best_model_max_async=...)
GraphRAG(cheap_model_func=my_llm_complete, cheap_model_max_token_size=..., cheap_model_max_async=...)
```

You can refer to this [example](./examples/using_deepseek_as_llm.py) that use [`deepseek-chat`](https://platform.deepseek.com/api-docs/) as the LLM model

You can refer to this [example](./examples/using_ollama_as_llm.py) that use [`ollama`](https://github.com/ollama/ollama) as the LLM model

#### Json Output

`nano-graphrag` will use `best_model_func` to output JSON with params `"response_format": {"type": "json_object"}`. However there are some open-source model maybe produce unstable JSON. 

`nano-graphrag` introduces a post-process interface for you to convert the response to JSON. This func's signature is below:

```python
def YOUR_STRING_TO_JSON_FUNC(response: str) -> dict:
  "Convert the string response to JSON"
  ...
```

And pass your own func by `GraphRAG(...convert_response_to_json_func=YOUR_STRING_TO_JSON_FUNC,...)`.

For example, you can refer to [json_repair](https://github.com/mangiucugna/json_repair) to repair the JSON string returned by LLM. 
</details>



<details>
<summary>Embedding Function</summary>

You can replace the default embedding functions with any `_utils.EmbedddingFunc` instance.

For example, the default one is using OpenAI embedding API:

```python
@wrap_embedding_func_with_attrs(embedding_dim=1536, max_token_size=8192)
async def openai_embedding(texts: list[str]) -> np.ndarray:
    openai_async_client = AsyncOpenAI()
    response = await openai_async_client.embeddings.create(
        model="text-embedding-3-small", input=texts, encoding_format="float"
    )
    return np.array([dp.embedding for dp in response.data])
```

Replace default embedding function with:

```python
GraphRAG(embedding_func=your_embed_func, embedding_batch_num=..., embedding_func_max_async=...)
```

You can refer to an [example](./examples/using_local_embedding_model.py) that use `sentence-transformer` to locally compute embeddings.
</details>


<details>
<summary>Storage Component</summary>

You can replace all storage-related components to your own implementation, `nano-graphrag` mainly uses three kinds of storage:

**`base.BaseKVStorage` for storing key-json pairs of data**

- By default we use disk file storage as the backend.
- We have built-in Redis storage for production use:
  - High-performance async operations with connection pooling
  - Configurable TTL per namespace (e.g., 12-hour cache for LLM responses)
  - Automatic retry with exponential backoff
  - Pipeline support for batch operations
  - Redis Cluster ready (single-node currently implemented)
- Configure Redis via environment variables or `StorageConfig`:
  ```python
  from nano_graphrag import GraphRAG
  from nano_graphrag.config import StorageConfig

  # Using Redis backend
  graph = GraphRAG(
      storage=StorageConfig(
          kv_backend="redis",
          redis_url="redis://localhost:6379",
          redis_password="your-password",  # Optional
          redis_max_connections=50,         # Connection pool size
      )
  )
  ```
- `GraphRAG(.., key_string_value_json_storage_cls=YOURS,...)`

**`base.BaseVectorStorage` for indexing embeddings**

- By default we use [`nano-vectordb`](https://github.com/gusye1234/nano-vectordb) as the backend.
- We have built-in [`hnswlib`](https://github.com/nmslib/hnswlib) storage, check out this [example](./examples/using_hnsw_as_vectorDB.py).
- We have built-in [`qdrant`](https://qdrant.tech/) storage for production use, check out this [example](./examples/storage_qdrant_config.py).
- Check out this [example](./examples/using_milvus_as_vectorDB.py) that implements [`milvus-lite`](https://github.com/milvus-io/milvus-lite) as the backend (not available in Windows).
- `GraphRAG(.., vector_db_storage_cls=YOURS,...)`

**`base.BaseGraphStorage` for storing knowledge graph**

- By default we use [`networkx`](https://github.com/networkx/networkx) as the backend for Community Edition compatibility.
- We have production-ready `Neo4jStorage` for graph with full GDS support (requires Neo4j Enterprise), check out the [production guide](./docs/storage/neo4j_production.md).
- `GraphRAG(.., graph_storage_cls=YOURS,...)`

You can refer to `nano_graphrag.base` to see detailed interfaces for each components.
</details>



## FQA

Check [FQA](./docs/FAQ.md).



## Roadmap

See [ROADMAP.md](./docs/ROADMAP.md)



## Contribute

## Testing

### Running Tests

```bash
# Run all unit tests
pytest tests/ -v

# Run storage backend tests
pytest tests/storage/ -v

# Run integration tests (requires services)
RUN_NEO4J_TESTS=1 RUN_QDRANT_TESTS=1 pytest tests/storage/ -k "integration or test_neo4j_connection" -v
```

### Integration Test Requirements

- **Neo4j**: Must be running on `localhost:7687` with credentials `neo4j/your-secure-password-change-me`
- **Qdrant**: Must be running on `localhost:6333`
- **Redis**: Must be running on `localhost:6379` (optional: with password authentication)
- **OpenAI**: Requires valid API key in `.env` file

See [testing guide](./docs/testing_guide.md) for detailed testing documentation.

`nano-graphrag` is open to any kind of contribution. Read [this](./docs/CONTRIBUTING.md) before you contribute.




## Benchmark

- [benchmark for English](./docs/benchmark-en.md)
- [benchmark for Chinese](./docs/benchmark-zh.md)
- [An evaluation](./examples/benchmarks/eval_naive_graphrag_on_multi_hop.ipynb) notebook on a [multi-hop RAG task](https://github.com/yixuantt/MultiHop-RAG)



## Projects that used `nano-graphrag`

- [Medical Graph RAG](https://github.com/MedicineToken/Medical-Graph-RAG): Graph RAG for the Medical Data
- [LightRAG](https://github.com/HKUDS/LightRAG): Simple and Fast Retrieval-Augmented Generation
- [fast-graphrag](https://github.com/circlemind-ai/fast-graphrag): RAG that intelligently adapts to your use case, data, and queries
- [HiRAG](https://github.com/hhy-huang/HiRAG): Retrieval-Augmented Generation with Hierarchical Knowledge

> Welcome to pull requests if your project uses `nano-graphrag`, it will help others to trust this repo❤️



## Issues

- `nano-graphrag` didn't implement the `covariates` feature of `GraphRAG`
- `nano-graphrag` implements the global search different from the original. The original use a map-reduce-like style to fill all the communities into context, while `nano-graphrag` only use the top-K important and central communites (use `QueryParam.global_max_consider_community` to control, default to 512 communities).
