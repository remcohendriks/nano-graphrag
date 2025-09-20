# NGRAF-020: Implement Sparse+Dense Hybrid Search for Qdrant

## Summary
Add sparse vector support alongside existing dense embeddings to enable hybrid search in Qdrant, improving retrieval accuracy for ID-based and exact-match queries (e.g., "EO 14282", document numbers, citations).

## Feature Branch
`feature/ngraf-020-sparse-dense-hybrid-search`

## Background
Current dense-only embeddings struggle with exact matches and ID-based queries. Executive orders and similar documents contain precise identifiers that have poor semantic similarity to user queries. Sparse vectors excel at exact token matching, making hybrid search ideal for this use case.

## User Story
As a user querying for specific documents by ID or citation, I want the system to accurately retrieve documents using both semantic (dense) and lexical (sparse) matching, so that queries like "EO 14282" reliably return Executive Order 14282.

## Performance Considerations

### Resource Requirements
- **Model Loading**: SPLADE model (~500MB) loads once per process, cached as singleton
- **CPU Performance**: ~100-200ms per document (acceptable for batch insert)
- **GPU Performance**: ~10-20ms per document (recommended for production)
- **Memory Usage**: ~1.5GB for SPLADE model + torch
- **Startup Impact**: Model loads on first use, not application start (lazy loading)

### Environment Variables for Resource Control
```bash
SPARSE_DEVICE=cpu  # or cuda for GPU acceleration
SPARSE_BATCH_SIZE=32  # Batch encoding for efficiency
SPARSE_MODEL_CACHE=true  # Reuse model instance across calls
SPARSE_TIMEOUT_MS=5000  # Fallback to dense if sparse encoding is slow
```

### Low-Resource Fallback
If sparse encoding fails or times out, system logs warning and continues with dense-only search to ensure availability.

## Chunk & Payload Optimization

For optimal hybrid search performance:

1. **Clean Text in Chunks**: Strip HTML tags, normalize whitespace before indexing
2. **Separate ID Fields in Payload**: Store canonical IDs as distinct fields for better sparse matching
   ```python
   payload = {
       "content": "Full document text...",
       "doc_id": "14282",  # Sparse-friendly numeric ID
       "canonical_name": "EXECUTIVE ORDER 14282"  # Exact match field
   }
   ```
3. **Consistent Chunk Size**: Keep chunks at 1-2K tokens for stronger sparse signals (large chunks dilute exact matches)

## Observability & Tuning

### Rank Position Logging
Log rank positions from both modalities for future optimization:
```python
logger.info(f"Hybrid query '{query[:50]}': dense_rank={dense_ranks}, sparse_rank={sparse_ranks}, fused_rank={final_ranks}")
```

This enables:
- A/B testing different fusion weights
- Identifying where each modality excels or fails
- Data-driven transition to weighted fusion in future

### Fusion Method Evolution
- Start with RRF (simple, no tuning required)
- Collect rank position metrics for 2-4 weeks
- Use data to implement weighted fusion in NGRAF-021 if needed

## Technical Specification

### 1. Add Sparse Embedding Provider with Singleton Pattern

#### File: `nano_graphrag/llm/providers/sparse.py` (new)
```python
import os
import asyncio
from typing import List, Dict, Any, Optional
import logging
from ...base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)

# Global model cache for singleton pattern
_model_cache = {}
_model_lock = asyncio.Lock()

class SparseEmbeddingProvider(BaseEmbeddingProvider):
    """SPLADE sparse embedding provider for hybrid search with singleton caching."""

    def __init__(self, model_name: str = None):
        self.model_name = model_name or os.getenv("SPARSE_MODEL", "prithvida/Splade_PP_en_v1")
        self.device = os.getenv("SPARSE_DEVICE", "cpu")
        self.batch_size = int(os.getenv("SPARSE_BATCH_SIZE", "32"))
        self.max_length = int(os.getenv("SPARSE_MAX_LENGTH", "256"))
        self.timeout_ms = int(os.getenv("SPARSE_TIMEOUT_MS", "5000"))
        self.cache_enabled = os.getenv("SPARSE_MODEL_CACHE", "true").lower() == "true"

        self.tokenizer = None
        self.model = None
        self._initialized = False

    async def _initialize(self):
        """Lazy load model on first use with singleton pattern."""
        if self._initialized:
            return

        async with _model_lock:
            # Check cache if enabled
            if self.cache_enabled and self.model_name in _model_cache:
                logger.info(f"Reusing cached SPLADE model: {self.model_name}")
                self.tokenizer, self.model = _model_cache[self.model_name]
                self._initialized = True
                return

            try:
                logger.info(f"Loading SPLADE model: {self.model_name} on {self.device}")
                from transformers import AutoTokenizer, AutoModel
                import torch

                self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self.model = AutoModel.from_pretrained(self.model_name)

                if self.device == "cuda" and torch.cuda.is_available():
                    self.model = self.model.cuda()

                self.model.eval()

                # Cache the model if enabled
                if self.cache_enabled:
                    _model_cache[self.model_name] = (self.tokenizer, self.model)

                self._initialized = True
                logger.info(f"Successfully loaded SPLADE model on {self.device}")

            except Exception as e:
                logger.error(f"Failed to load SPLADE model: {e}")
                raise

    async def embed(self, texts: List[str]) -> Dict[str, Any]:
        """Generate sparse embeddings with timeout and error handling."""
        await self._initialize()

        if not self.model or not self.tokenizer:
            logger.error("Sparse model not initialized, returning empty embeddings")
            return {"embeddings": [{"indices": [], "values": []} for _ in texts]}

        try:
            # Apply timeout
            import asyncio
            result = await asyncio.wait_for(
                self._embed_batch(texts),
                timeout=self.timeout_ms / 1000.0
            )
            return result

        except asyncio.TimeoutError:
            logger.warning(f"Sparse embedding timed out after {self.timeout_ms}ms, returning empty")
            return {"embeddings": [{"indices": [], "values": []} for _ in texts]}
        except Exception as e:
            logger.error(f"Sparse embedding failed: {e}")
            return {"embeddings": [{"indices": [], "values": []} for _ in texts]}

    async def _embed_batch(self, texts: List[str]) -> Dict[str, Any]:
        """Actual embedding logic with batching."""
        import torch
        sparse_embeddings = []

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]

            with torch.no_grad():
                inputs = self.tokenizer(
                    batch_texts,
                    return_tensors="pt",
                    max_length=self.max_length,
                    truncation=True,
                    padding=True
                )

                if self.device == "cuda":
                    inputs = {k: v.cuda() for k, v in inputs.items()}

                outputs = self.model(**inputs)
                logits = outputs.logits if hasattr(outputs, 'logits') else outputs.last_hidden_state

                # Process each item in batch
                for j in range(len(batch_texts)):
                    # Max pooling over sequence dimension for this item
                    item_logits = logits[j]
                    pooled = torch.max(item_logits, dim=0).values

                    # Apply log(1 + ReLU(x)) sparsification
                    sparse = torch.log1p(torch.relu(pooled))

                    # Convert to sparse format
                    nonzero = torch.nonzero(sparse).squeeze()
                    if nonzero.numel() > 0:
                        indices = nonzero.cpu().tolist()
                        if not isinstance(indices, list):
                            indices = [indices]
                        values = sparse[nonzero].cpu().tolist()
                        if not isinstance(values, list):
                            values = [values]
                    else:
                        indices = []
                        values = []

                    sparse_embeddings.append({
                        "indices": indices,
                        "values": values
                    })

        return {"embeddings": sparse_embeddings}
```

### 2. Update Qdrant Storage for Hybrid Vectors

#### File: `nano_graphrag/_storage/vdb_qdrant.py`

Add sparse vector support to existing Qdrant storage:

```python
# In __post_init__, add sparse config from environment
self._enable_hybrid = self.global_config.get(
    "enable_hybrid_search",
    os.getenv("ENABLE_HYBRID_SEARCH", "false").lower() == "true"
)
self._sparse_model = self.global_config.get(
    "sparse_model",
    os.getenv("SPARSE_MODEL", "prithvida/Splade_PP_en_v1")
)
# Hybrid search fusion method
self._fusion_method = self.global_config.get(
    "hybrid_fusion_method",
    os.getenv("HYBRID_FUSION_METHOD", "rrf")  # rrf or weighted
)

# Modify _ensure_collection to support both dense and sparse
async def _ensure_collection(self):
    """Ensure collection exists with hybrid vector configuration."""
    if self._collection_initialized:
        return

    client = await self._get_client()
    collections = await client.get_collections()
    exists = any(c.name == self.namespace for c in collections.collections)

    if not exists:
        logger.info(f"Creating Qdrant collection with hybrid search: {self.namespace}")

        vectors_config = {}

        # Dense vector configuration
        vectors_config["dense"] = self._models.VectorParams(
            size=self.embedding_func.embedding_dim,
            distance=self._models.Distance.COSINE
        )

        # Sparse vector configuration if enabled
        if self._enable_hybrid:
            vectors_config["sparse"] = self._models.SparseVectorParams(
                index=self._models.SparseIndexParams(
                    on_disk=os.getenv("SPARSE_INDEX_ON_DISK", "false").lower() == "true",
                    full_scan_threshold=int(os.getenv("SPARSE_FULL_SCAN_THRESHOLD", "10000"))
                )
            )
            logger.info(f"Hybrid search enabled with sparse model: {self._sparse_model}")

        await client.create_collection(
            collection_name=self.namespace,
            vectors_config=vectors_config,
            **self._collection_params
        )
        logger.info(f"Created {'hybrid' if self._enable_hybrid else 'dense-only'} Qdrant collection: {self.namespace}")
```

Update upsert method to handle both vector types:

```python
async def upsert(self, data: Dict[str, Dict]):
    """Upsert dense and sparse vectors to Qdrant collection."""
    if not data:
        return

    await self._ensure_collection()
    client = await self._get_client()

    # Generate dense embeddings as before
    contents = [v["content"] for v in data.values()]
    dense_embeddings = await self.embedding_func(contents)

    # Generate sparse embeddings if hybrid enabled
    sparse_embeddings = None
    if self._enable_hybrid:
        from ..llm.providers.sparse import SparseEmbeddingProvider
        sparse_provider = SparseEmbeddingProvider(self._sparse_model)
        sparse_result = await sparse_provider.embed(contents)
        sparse_embeddings = sparse_result["embeddings"]
        logger.debug(f"Generated sparse embeddings for {len(contents)} documents")

    # Build points with both vectors
    points = []
    for idx, (doc_id, doc_data) in enumerate(data.items()):
        vector_data = {"dense": dense_embeddings[idx]}

        if sparse_embeddings:
            vector_data["sparse"] = self._models.SparseVector(
                indices=sparse_embeddings[idx]["indices"],
                values=sparse_embeddings[idx]["values"]
            )

        points.append(self._models.PointStruct(
            id=self._hash_to_id(doc_id),
            vector=vector_data,
            payload={"id": doc_id, **doc_data}
        ))

    await client.upsert(
        collection_name=self.namespace,
        points=points,
        wait=True
    )
    logger.info(f"Upserted {len(points)} points with {'hybrid' if self._enable_hybrid else 'dense-only'} vectors")
```

Update query method for hybrid search:

```python
async def query(self, query: str, top_k: int = 5, **kwargs) -> List[Dict[str, Any]]:
    """Query using hybrid dense+sparse search with fusion."""
    await self._ensure_collection()
    client = await self._get_client()

    # Get top_k from environment if not specified
    top_k = kwargs.get("top_k", int(os.getenv("HYBRID_SEARCH_TOP_K", str(top_k))))

    # Generate dense query embedding
    dense_embedding = (await self.embedding_func([query]))[0]

    # Prepare query request
    if self._enable_hybrid:
        # Generate sparse query embedding
        from ..llm.providers.sparse import SparseEmbeddingProvider
        sparse_provider = SparseEmbeddingProvider(self._sparse_model)
        sparse_result = await sparse_provider.embed([query])
        sparse_data = sparse_result["embeddings"][0]

        logger.debug(f"Hybrid search with {len(sparse_data['indices'])} sparse dimensions")

        # Use Qdrant's Query API for hybrid search with fusion
        from qdrant_client.models import FusionQuery, NamedSparseVector

        # Determine fusion method
        if self._fusion_method == "rrf":
            fusion = FusionQuery.RRF
        else:
            # Future: support weighted fusion with configurable weights
            fusion = FusionQuery.RRF

        results = await client.query(
            collection_name=self.namespace,
            query=[
                # Dense vector query
                self._models.NamedVector(
                    name="dense",
                    vector=dense_embedding
                ),
                # Sparse vector query
                NamedSparseVector(
                    name="sparse",
                    vector=self._models.SparseVector(
                        indices=sparse_data["indices"],
                        values=sparse_data["values"]
                    )
                )
            ],
            fusion=fusion,
            limit=top_k,
            with_payload=True
        )
        logger.info(f"Hybrid query returned {len(results)} results using {self._fusion_method} fusion")
    else:
        # Fallback to dense-only search
        results = await client.search(
            collection_name=self.namespace,
            query_vector=("dense", dense_embedding),
            limit=top_k,
            with_payload=True
        )
        logger.debug(f"Dense-only query returned {len(results)} results")

    return self._extract_results(results)
```

### 3. Configuration Updates

#### File: `nano_graphrag/config.py`

Add hybrid search configuration with environment variable support:

```python
@dataclass(frozen=True)
class StorageConfig:
    # ... existing fields ...
    enable_hybrid_search: bool = False
    sparse_model: str = "prithvida/Splade_PP_en_v1"
    hybrid_fusion_method: str = "rrf"
    sparse_index_on_disk: bool = False
    sparse_full_scan_threshold: int = 10000
    sparse_max_length: int = 256
    hybrid_search_top_k: int = 20

    @classmethod
    def from_env(cls) -> 'StorageConfig':
        # ... existing code ...
        return cls(
            # ... existing fields ...
            enable_hybrid_search=os.getenv("ENABLE_HYBRID_SEARCH", "false").lower() == "true",
            sparse_model=os.getenv("SPARSE_MODEL", "prithvida/Splade_PP_en_v1"),
            hybrid_fusion_method=os.getenv("HYBRID_FUSION_METHOD", "rrf"),
            sparse_index_on_disk=os.getenv("SPARSE_INDEX_ON_DISK", "false").lower() == "true",
            sparse_full_scan_threshold=int(os.getenv("SPARSE_FULL_SCAN_THRESHOLD", "10000")),
            sparse_max_length=int(os.getenv("SPARSE_MAX_LENGTH", "256")),
            hybrid_search_top_k=int(os.getenv("HYBRID_SEARCH_TOP_K", "20"))
        )
```

### 4. Docker Compose Environment

#### File: `docker-compose-api.yml`

Add comprehensive environment variables:

```yaml
# In api service environment section
# Hybrid search configuration
ENABLE_HYBRID_SEARCH: "true"
SPARSE_MODEL: "prithvida/Splade_PP_en_v1"
HYBRID_FUSION_METHOD: "rrf"  # rrf or weighted (future)
SPARSE_INDEX_ON_DISK: "false"  # Set to true for large collections
SPARSE_FULL_SCAN_THRESHOLD: "10000"  # When to switch to full scan
SPARSE_MAX_LENGTH: "256"  # Max tokens for sparse encoding
HYBRID_SEARCH_TOP_K: "20"  # Default top-k for hybrid queries
```

### 5. Dependencies Update

#### File: `requirements.txt`

Add sparse embedding dependencies:

```
transformers>=4.36.0
torch>=2.0.0
```

## Graceful Degradation & Fallback Behavior

### Fallback Scenarios
1. **Sparse model fails to load**: Log warning, continue with dense-only (system remains functional)
2. **Sparse encoding times out**: Use dense-only for that specific query
3. **Qdrant hybrid query fails**: Automatic fallback to dense search
4. **ENABLE_HYBRID_SEARCH=false**: System behaves identically to current implementation

### Error Handling in Qdrant Storage
```python
# In query method
if self._enable_hybrid:
    try:
        # Attempt hybrid search
        results = await client.query(...)
    except Exception as e:
        logger.warning(f"Hybrid search failed, falling back to dense: {e}")
        # Fallback to dense-only
        results = await client.search(
            collection_name=self.namespace,
            query_vector=("dense", dense_embedding),
            limit=top_k
        )
```

## Testing

### Unit Test: Sparse Embedding Provider

#### File: `tests/test_sparse_embedding.py`

```python
import pytest
import os
from nano_graphrag.llm.providers.sparse import SparseEmbeddingProvider

@pytest.mark.asyncio
async def test_sparse_embedding_generation():
    provider = SparseEmbeddingProvider()
    texts = ["Executive Order 14282", "EO 14282", "what about eo 14282"]

    result = await provider.embed(texts)
    embeddings = result["embeddings"]

    assert len(embeddings) == 3
    for embedding in embeddings:
        assert "indices" in embedding
        assert "values" in embedding
        assert len(embedding["indices"]) == len(embedding["values"])
        assert len(embedding["indices"]) > 0  # Should have non-zero elements

@pytest.mark.asyncio
async def test_abbreviation_variants():
    """Test that abbreviation variants match correctly."""
    provider = SparseEmbeddingProvider()

    variants = [
        "EO 14282",
        "E.O. 14282",
        "eo14282",
        "Executive Order 14282"
    ]

    results = await provider.embed(variants)
    embeddings = results["embeddings"]

    # All variants should share the "14282" token
    all_indices = [set(emb["indices"]) for emb in embeddings]
    common_indices = all_indices[0]
    for indices_set in all_indices[1:]:
        common_indices = common_indices.intersection(indices_set)

    assert len(common_indices) > 0, "Variants should share common tokens"

@pytest.mark.asyncio
async def test_pure_numeric_query():
    """Test that pure numeric queries work."""
    provider = SparseEmbeddingProvider()

    result = await provider.embed(["14282"])
    embedding = result["embeddings"][0]

    assert len(embedding["indices"]) > 0
    assert len(embedding["values"]) > 0

@pytest.mark.asyncio
async def test_semantic_preservation():
    """Test that semantic queries still get reasonable sparse representations."""
    provider = SparseEmbeddingProvider()

    semantic_query = "transparency and accountability in universities"
    result = await provider.embed([semantic_query])
    embedding = result["embeddings"][0]

    # Should have multiple tokens for semantic content
    assert len(embedding["indices"]) > 5

@pytest.mark.asyncio
async def test_fallback_on_timeout(monkeypatch):
    """Test graceful degradation on timeout."""
    monkeypatch.setenv("SPARSE_TIMEOUT_MS", "1")  # Impossibly short timeout

    provider = SparseEmbeddingProvider()
    result = await provider.embed(["test text"])

    # Should return empty embeddings on timeout
    assert result["embeddings"][0]["indices"] == []
    assert result["embeddings"][0]["values"] == []

@pytest.mark.asyncio
async def test_singleton_caching():
    """Test that model is cached and reused."""
    provider1 = SparseEmbeddingProvider()
    await provider1._initialize()

    provider2 = SparseEmbeddingProvider()
    await provider2._initialize()

    # Should reuse the same model instance
    assert provider1.model is provider2.model
```

### Integration Test: Hybrid Search

#### File: `tests/test_hybrid_search_qdrant.py`

```python
import pytest
import os
from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
from nano_graphrag._utils import EmbeddingFunc

@pytest.mark.skipif(
    os.getenv("RUN_QDRANT_TESTS") != "1",
    reason="Qdrant integration tests require running Qdrant instance"
)
@pytest.mark.asyncio
async def test_hybrid_search_retrieval():
    """Test that hybrid search improves ID-based retrieval."""

    # Mock embedding function for dense vectors
    async def mock_embed(texts):
        return [[0.1] * 1536 for _ in texts]  # Dummy embeddings

    embedding_func = EmbeddingFunc(
        embedding_dim=1536,
        max_token_size=8192,
        func=mock_embed
    )

    config = {
        "enable_hybrid_search": True,
        "sparse_model": "prithvida/Splade_PP_en_v1",
        "qdrant_url": "http://localhost:6333"
    }

    storage = QdrantVectorStorage(
        namespace="test_hybrid",
        global_config=config,
        embedding_func=embedding_func,
        meta_fields=set()
    )

    # Insert documents
    await storage.upsert({
        "eo-14282": {
            "content": "Executive Order 14282 concerning transparency at universities",
            "entity_name": "EXECUTIVE ORDER 14282"
        },
        "eo-14190": {
            "content": "Executive Order 14190 about K-12 education",
            "entity_name": "EXECUTIVE ORDER 14190"
        }
    })

    # Query with exact ID
    results = await storage.query("EO 14282", top_k=2)

    # Should rank EO 14282 first due to sparse exact match
    assert len(results) > 0
    assert "14282" in results[0]["payload"]["content"]

    # Cleanup
    client = await storage._get_client()
    await client.delete_collection("test_hybrid")

@pytest.mark.asyncio
async def test_hybrid_config_from_env(monkeypatch):
    """Test that hybrid search can be configured entirely via environment."""
    monkeypatch.setenv("ENABLE_HYBRID_SEARCH", "true")
    monkeypatch.setenv("SPARSE_MODEL", "test/model")
    monkeypatch.setenv("HYBRID_FUSION_METHOD", "rrf")
    monkeypatch.setenv("SPARSE_INDEX_ON_DISK", "true")
    monkeypatch.setenv("SPARSE_FULL_SCAN_THRESHOLD", "5000")
    monkeypatch.setenv("HYBRID_SEARCH_TOP_K", "50")

    from nano_graphrag.config import StorageConfig
    config = StorageConfig.from_env()

    assert config.enable_hybrid_search is True
    assert config.sparse_model == "test/model"
    assert config.hybrid_fusion_method == "rrf"
    assert config.sparse_index_on_disk is True
    assert config.sparse_full_scan_threshold == 5000
    assert config.hybrid_search_top_k == 50
```

## Documentation Updates

### README.md Addition

Add section after "Storage Component" customization:

```markdown
### Hybrid Search (Qdrant Only)

nano-graphrag supports hybrid dense+sparse search for improved retrieval accuracy with Qdrant:

```python
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, StorageConfig

# Enable hybrid search for better ID and citation matching
config = GraphRAGConfig(
    storage=StorageConfig(
        vector_backend="qdrant",
        qdrant_url="http://localhost:6333",
        enable_hybrid_search=True,
        sparse_model="prithvida/Splade_PP_en_v1"
    )
)

graph = GraphRAG(config=config)
```

**Benefits of Hybrid Search:**
- Exact match retrieval for IDs, citations, and document numbers
- Combines semantic understanding (dense) with lexical matching (sparse)
- Particularly effective for structured documents (legal, medical, technical)
- Uses Reciprocal Rank Fusion (RRF) for result merging

**Configuration via Environment Variables:**
```bash
# Enable hybrid search
export ENABLE_HYBRID_SEARCH=true

# Sparse model selection (any SPLADE variant)
export SPARSE_MODEL=prithvida/Splade_PP_en_v1

# Fusion method (currently only 'rrf' supported)
export HYBRID_FUSION_METHOD=rrf

# Performance tuning
export SPARSE_INDEX_ON_DISK=false  # Use disk for large collections
export SPARSE_FULL_SCAN_THRESHOLD=10000  # Switch to full scan threshold
export SPARSE_MAX_LENGTH=256  # Max tokens for sparse encoding
export HYBRID_SEARCH_TOP_K=20  # Default results to retrieve
```

**Requirements:**
- Qdrant instance (local or cloud)
- Additional dependencies: `transformers`, `torch`
- ~20-30% additional storage for sparse indexes
```

## Definition of Done

- [ ] Sparse embedding provider implemented with environment variable support
- [ ] Qdrant storage supports dual vector types (dense + sparse)
- [ ] Hybrid query uses RRF fusion
- [ ] All configuration options available via environment variables
- [ ] Unit tests pass for sparse embeddings
- [ ] Integration test demonstrates improved ID-based retrieval
- [ ] Environment variable configuration tested
- [ ] README documents hybrid search usage and all env vars
- [ ] Docker compose includes all hybrid search environment variables

## Pull Request Should Contain

- Sparse embedding provider implementation with env var support
- Modified Qdrant storage with hybrid support
- Complete environment variable configuration
- Test coverage for sparse embeddings and hybrid retrieval
- Test coverage for environment variable configuration
- Documentation of hybrid search benefits and all configuration options
- Docker-compose with all hybrid search environment variables

## Implementation Notes

- All configuration options must be available via environment variables
- Keep changes minimal - only modify Qdrant storage, don't touch other backends
- Use SPLADE as default sparse encoder (proven, available on HuggingFace)
- Leverage Qdrant's native Query API for fusion (no custom fusion logic)
- RRF fusion is simple and effective (no weight tuning required initially)
- Sparse indices are relatively small (~2-4KB per document)
- No backward compatibility needed - this is opt-in via configuration
- Log at appropriate levels: INFO for operations, DEBUG for details