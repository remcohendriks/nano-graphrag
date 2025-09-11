# NGRAF-011: Qdrant Vector Storage - First-Class Integration

## Overview
Comprehensive integration of Qdrant as a production-ready vector storage backend, including factory registration, configuration management, implementation, testing framework, and documentation.

## Current State
- Working example exists in `examples/using_qdrant_as_vectorDB.py` but uses legacy patterns
- Not registered in StorageFactory (`ALLOWED_VECTOR` only has "nano" and "hnswlib")
- No configuration support in StorageConfig
- Uses UUID instead of consistent hashing
- Missing proper async support and connection management
- No integration tests or benchmarks

## Proposed Implementation

### Phase 1: Configuration and Factory Integration

#### Update `nano_graphrag/config.py`
```python
@dataclass
class StorageConfig:
    # ... existing fields ...
    
    # Qdrant configuration
    qdrant_url: Optional[str] = None  # None for embedded, URL for remote
    qdrant_api_key: Optional[str] = None
    qdrant_path: str = "./qdrant_data"  # For embedded mode
    qdrant_collection_params: dict = field(default_factory=dict)
    qdrant_timeout: float = 30.0
    qdrant_grpc_port: Optional[int] = None  # For gRPC mode
    qdrant_prefer_grpc: bool = False
    
    def validate(self) -> None:
        """Add Qdrant validation."""
        if self.vector_backend == "qdrant":
            if self.qdrant_url and self.qdrant_path == "./qdrant_data":
                logger.warning("Both qdrant_url and qdrant_path set, using remote")
```

#### Update `nano_graphrag/_storage/factory.py`
```python
class StorageFactory:
    ALLOWED_VECTOR = {"nano", "hnswlib", "qdrant"}  # Add qdrant
    
def _get_qdrant_storage():
    """Lazy loader for Qdrant storage."""
    from .vdb_qdrant import QdrantVectorStorage
    return QdrantVectorStorage

def _register_backends():
    # Add Qdrant registration
    if "qdrant" not in StorageFactory._vector_backends:
        StorageFactory.register_vector("qdrant", _get_qdrant_storage)
```

### Phase 2: Storage Implementation

#### Create `nano_graphrag/_storage/vdb_qdrant.py`
```python
from typing import Optional, List, Dict, Any, Set, Union
from dataclasses import dataclass, field
import asyncio
import logging
from pathlib import Path

from nano_graphrag.base import BaseVectorStorage
from nano_graphrag._utils import ensure_dependency, logger
import xxhash

@dataclass
class QdrantVectorStorage(BaseVectorStorage):
    """Production-ready Qdrant vector storage with async support."""
    
    _client: Optional[Any] = field(default=None, init=False)
    _async_client: Optional[Any] = field(default=None, init=False)
    _collection_initialized: bool = field(default=False, init=False)
    _use_grpc: bool = field(default=False, init=False)
    
    def __post_init__(self):
        """Initialize Qdrant client and collection."""
        ensure_dependency("qdrant_client", "qdrant-client", "Qdrant vector storage")
        
        from qdrant_client import QdrantClient, AsyncQdrantClient
        from qdrant_client.models import Distance, VectorParams, OptimizersConfig
        
        # Determine connection mode
        config = self.global_config
        
        if config.get("qdrant_url"):
            # Remote mode
            self._use_grpc = config.get("qdrant_prefer_grpc", False)
            
            kwargs = {
                "url": config["qdrant_url"],
                "api_key": config.get("qdrant_api_key"),
                "timeout": config.get("qdrant_timeout", 30),
            }
            
            if self._use_grpc and config.get("qdrant_grpc_port"):
                kwargs["grpc_port"] = config["qdrant_grpc_port"]
                kwargs["prefer_grpc"] = True
            
            self._client = QdrantClient(**kwargs)
            self._async_client = AsyncQdrantClient(**kwargs)
        else:
            # Embedded mode
            path = Path(config.get("qdrant_path", "./qdrant_data"))
            path.mkdir(parents=True, exist_ok=True)
            
            self._client = QdrantClient(path=str(path))
            self._async_client = AsyncQdrantClient(path=str(path))
        
        # Initialize collection
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Ensure collection exists with proper configuration."""
        from qdrant_client.models import Distance, VectorParams, OptimizersConfig
        
        collections = self._client.get_collections().collections
        exists = any(c.name == self.namespace for c in collections)
        
        if not exists:
            vector_params = VectorParams(
                size=self.embedding_func.embedding_dim,
                distance=Distance.COSINE
            )
            
            # Apply custom collection params if provided
            collection_params = self.global_config.get("qdrant_collection_params", {})
            
            self._client.create_collection(
                collection_name=self.namespace,
                vectors_config=vector_params,
                optimizers_config=OptimizersConfig(
                    indexing_threshold=collection_params.get("indexing_threshold", 20000)
                ),
                **collection_params
            )
        
        self._collection_initialized = True
    
    async def upsert(self, data: Dict[str, Dict]):
        """Upsert vectors with consistent ID generation and batching."""
        from qdrant_client.models import PointStruct, Batch
        
        if not data:
            return
        
        # Prepare points with consistent hashing
        points = []
        for content, metadata in data.items():
            # Use xxhash for consistent ID generation (matching HNSW)
            content_id = xxhash.xxh32_hexdigest(content)
            
            # Prepare payload
            payload = {
                "content": content,
                **{k: v for k, v in metadata.items() if k != "embedding"}
            }
            
            # Ensure required fields for GraphRAG compatibility
            if "entity_name" not in payload and "entity_name" in metadata:
                payload["entity_name"] = metadata["entity_name"]
            
            points.append(PointStruct(
                id=content_id,
                vector=metadata["embedding"],
                payload=payload
            ))
        
        # Batch upsert for performance
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            await self._async_client.upsert(
                collection_name=self.namespace,
                points=batch,
                wait=True  # Ensure consistency
            )
        
        # Call index done callback if provided
        if callback := self.global_config.get("index_done_callback"):
            callback(self)
    
    async def query(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Query vectors with proper return format for GraphRAG."""
        # Get query embedding
        query_embeddings = await self.embedding_func([query])
        query_vector = query_embeddings[0]
        
        # Search
        results = await self._async_client.search(
            collection_name=self.namespace,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
            with_vectors=False  # Don't return vectors to save bandwidth
        )
        
        # Format results for GraphRAG compatibility
        formatted_results = []
        for hit in results:
            result = {
                "content": hit.payload.get("content", ""),
                "score": hit.score,  # Qdrant returns similarity score
                "distance": 1 - hit.score,  # Convert to distance for compatibility
            }
            
            # Include all payload fields
            for key, value in hit.payload.items():
                if key not in result:
                    result[key] = value
            
            formatted_results.append(result)
        
        return formatted_results
    
    async def delete_collection(self):
        """Delete the collection."""
        await self._async_client.delete_collection(self.namespace)
        self._collection_initialized = False
    
    async def close(self):
        """Clean up connections."""
        if self._async_client:
            await self._async_client.close()
        if self._client:
            self._client.close()
```

### Phase 3: Testing Framework

#### Create `tests/storage/test_qdrant_storage.py`
```python
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import tempfile
from pathlib import Path

from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
from nano_graphrag.base import BaseVectorStorage

class TestQdrantStorage:
    """Comprehensive tests for Qdrant storage."""
    
    @pytest.fixture
    def mock_embedding_func(self):
        """Mock embedding function."""
        func = AsyncMock()
        func.embedding_dim = 128
        func.return_value = [[0.1] * 128]
        return func
    
    @pytest.fixture
    def temp_dir(self):
        """Temporary directory for embedded Qdrant."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.mark.asyncio
    async def test_embedded_initialization(self, mock_embedding_func, temp_dir):
        """Test embedded Qdrant initialization."""
        config = {
            "qdrant_path": temp_dir,
        }
        
        with patch("nano_graphrag._storage.vdb_qdrant.QdrantClient") as mock_client:
            storage = QdrantVectorStorage(
                namespace="test",
                global_config=config,
                embedding_func=mock_embedding_func
            )
            
            mock_client.assert_called_once()
            assert temp_dir in str(mock_client.call_args)
    
    @pytest.mark.asyncio
    async def test_remote_initialization(self, mock_embedding_func):
        """Test remote Qdrant initialization."""
        config = {
            "qdrant_url": "http://localhost:6333",
            "qdrant_api_key": "test-key",
            "qdrant_timeout": 60
        }
        
        with patch("nano_graphrag._storage.vdb_qdrant.QdrantClient") as mock_client:
            storage = QdrantVectorStorage(
                namespace="test",
                global_config=config,
                embedding_func=mock_embedding_func
            )
            
            assert "http://localhost:6333" in str(mock_client.call_args)
            assert "test-key" in str(mock_client.call_args)
    
    @pytest.mark.asyncio
    async def test_upsert_with_xxhash(self, mock_embedding_func, temp_dir):
        """Test upsert uses xxhash for ID generation."""
        import xxhash
        
        config = {"qdrant_path": temp_dir}
        
        with patch("nano_graphrag._storage.vdb_qdrant.AsyncQdrantClient") as mock_async:
            mock_instance = AsyncMock()
            mock_async.return_value = mock_instance
            
            storage = QdrantVectorStorage(
                namespace="test",
                global_config=config,
                embedding_func=mock_embedding_func
            )
            
            test_data = {
                "test content": {
                    "embedding": [0.1] * 128,
                    "entity_name": "test_entity",
                    "metadata": "test"
                }
            }
            
            await storage.upsert(test_data)
            
            # Verify xxhash was used for ID
            expected_id = xxhash.xxh32_hexdigest("test content")
            call_args = mock_instance.upsert.call_args
            points = call_args[1]["points"]
            assert points[0].id == expected_id
    
    @pytest.mark.asyncio
    async def test_query_format_compatibility(self, mock_embedding_func, temp_dir):
        """Test query returns GraphRAG-compatible format."""
        from qdrant_client.models import ScoredPoint
        
        config = {"qdrant_path": temp_dir}
        
        with patch("nano_graphrag._storage.vdb_qdrant.AsyncQdrantClient") as mock_async:
            mock_instance = AsyncMock()
            mock_async.return_value = mock_instance
            
            # Mock search results
            mock_instance.search.return_value = [
                Mock(
                    score=0.95,
                    payload={
                        "content": "test content",
                        "entity_name": "entity1",
                        "entity_type": "person"
                    }
                )
            ]
            
            storage = QdrantVectorStorage(
                namespace="test",
                global_config=config,
                embedding_func=mock_embedding_func
            )
            
            results = await storage.query("test query", top_k=5)
            
            assert len(results) == 1
            assert results[0]["content"] == "test content"
            assert results[0]["score"] == 0.95
            assert results[0]["distance"] == 0.05  # 1 - score
            assert results[0]["entity_name"] == "entity1"
    
    @pytest.mark.asyncio
    async def test_batch_upsert(self, mock_embedding_func, temp_dir):
        """Test batch upsert for large datasets."""
        config = {"qdrant_path": temp_dir}
        
        with patch("nano_graphrag._storage.vdb_qdrant.AsyncQdrantClient") as mock_async:
            mock_instance = AsyncMock()
            mock_async.return_value = mock_instance
            
            storage = QdrantVectorStorage(
                namespace="test",
                global_config=config,
                embedding_func=mock_embedding_func
            )
            
            # Create 250 items (should trigger batching at 100)
            test_data = {
                f"content_{i}": {
                    "embedding": [0.1] * 128,
                    "metadata": f"test_{i}"
                }
                for i in range(250)
            }
            
            await storage.upsert(test_data)
            
            # Should be called 3 times (100, 100, 50)
            assert mock_instance.upsert.call_count == 3

@pytest.mark.integration
class TestQdrantIntegration:
    """Integration tests with real Qdrant instance."""
    
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration"),
        reason="Integration tests require --integration flag"
    )
    @pytest.mark.asyncio
    async def test_end_to_end_embedded(self):
        """Test end-to-end with embedded Qdrant."""
        # Implementation for real Qdrant testing
        pass
```

### Phase 4: Benchmarking

#### Create `benchmarks/storage/benchmark_qdrant.py`
```python
"""Benchmark Qdrant against other vector stores."""

import asyncio
import time
import numpy as np
from typing import Dict, List
import tempfile

async def benchmark_qdrant(num_vectors: int, dimensions: int) -> Dict[str, float]:
    """Benchmark Qdrant operations."""
    from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
    
    # Setup
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {"qdrant_path": tmpdir}
        
        # Mock embedding function
        class MockEmbed:
            embedding_dim = dimensions
            async def __call__(self, texts):
                return [np.random.rand(dimensions).tolist() for _ in texts]
        
        storage = QdrantVectorStorage(
            namespace="benchmark",
            global_config=config,
            embedding_func=MockEmbed()
        )
        
        # Prepare data
        data = {
            f"content_{i}": {
                "embedding": np.random.rand(dimensions).tolist(),
                "metadata": f"meta_{i}"
            }
            for i in range(num_vectors)
        }
        
        # Benchmark upsert
        start = time.time()
        await storage.upsert(data)
        upsert_time = time.time() - start
        
        # Benchmark query
        queries = 100
        start = time.time()
        for _ in range(queries):
            await storage.query("test", top_k=10)
        query_time = (time.time() - start) / queries
        
        await storage.close()
    
    return {
        "upsert_time": upsert_time,
        "query_time": query_time,
        "vectors": num_vectors,
        "dimensions": dimensions
    }

# Compare with HNSW and Nano
async def compare_backends():
    """Compare Qdrant with other backends."""
    results = {}
    
    for backend in ["qdrant", "hnswlib", "nano"]:
        results[backend] = await benchmark_backend(backend, 10000, 128)
    
    return results
```

### Phase 5: Documentation and Examples

#### Create `examples/qdrant_comprehensive.py`
```python
"""Comprehensive Qdrant usage examples."""

import asyncio
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, StorageConfig

async def example_embedded():
    """Example using embedded Qdrant."""
    config = GraphRAGConfig(
        storage=StorageConfig(
            vector_backend="qdrant",
            qdrant_path="./qdrant_embedded"
        )
    )
    
    rag = GraphRAG(config)
    await rag.ainsert("Paris is the capital of France.")
    result = await rag.aquery("What is the capital of France?")
    print(f"Embedded result: {result}")

async def example_remote():
    """Example using remote Qdrant."""
    config = GraphRAGConfig(
        storage=StorageConfig(
            vector_backend="qdrant",
            qdrant_url="http://localhost:6333",
            qdrant_api_key="your-api-key",
            qdrant_collection_params={
                "indexing_threshold": 50000,
                "on_disk": True
            }
        )
    )
    
    rag = GraphRAG(config)
    # ... usage

async def example_grpc():
    """Example using Qdrant with gRPC for performance."""
    config = GraphRAGConfig(
        storage=StorageConfig(
            vector_backend="qdrant",
            qdrant_url="http://localhost:6333",
            qdrant_grpc_port=6334,
            qdrant_prefer_grpc=True
        )
    )
    
    rag = GraphRAG(config)
    # ... usage

if __name__ == "__main__":
    asyncio.run(example_embedded())
```

#### Update documentation
- Add Qdrant section to README with performance comparisons
- Create `docs/storage/qdrant.md` with detailed configuration guide
- Add Docker Compose example for Qdrant deployment

## Definition of Done

- [ ] StorageFactory recognizes "qdrant" as valid vector backend
- [ ] StorageConfig has comprehensive Qdrant configuration options
- [ ] QdrantVectorStorage implementation with:
  - [ ] Embedded and remote mode support
  - [ ] Async operations throughout
  - [ ] Consistent xxhash ID generation
  - [ ] Proper GraphRAG return format
  - [ ] Batch operations for performance
  - [ ] gRPC support for high throughput
- [ ] Comprehensive test suite:
  - [ ] Unit tests with mocking
  - [ ] Integration tests (conditional)
  - [ ] Performance benchmarks
- [ ] Documentation:
  - [ ] README updated
  - [ ] Comprehensive examples
  - [ ] Configuration guide
  - [ ] Migration guide from example
- [ ] CI/CD updates to test with optional dependency

## Feature Branch
`feature/ngraf-011-qdrant-integration`

## Pull Request Requirements
- Performance comparison showing Qdrant vs HNSW vs Nano
- Test coverage > 90% for new code
- Documentation review by team
- Integration test results (if Qdrant available in CI)

## Technical Considerations
- Qdrant's gRPC mode offers 10x throughput over HTTP
- Collection optimization parameters crucial for large-scale deployment
- Consider implementing connection pooling for high-concurrency scenarios
- May need retry logic for network operations in remote mode