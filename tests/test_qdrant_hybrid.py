"""Integration tests for Qdrant hybrid search."""

import asyncio
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from dataclasses import dataclass
import numpy as np


@dataclass
class MockEmbeddingFunc:
    """Mock embedding function."""
    embedding_dim: int = 1536
    max_token_size: int = 8192

    async def __call__(self, texts):
        """Return mock embeddings."""
        return [np.random.rand(self.embedding_dim).tolist() for _ in texts]


@pytest.mark.asyncio
async def test_qdrant_hybrid_collection_creation():
    """Test that hybrid collection is created with both vector types."""
    from nano_graphrag.config import HybridSearchConfig

    mock_client = AsyncMock()
    mock_client.get_collections.return_value = MagicMock(collections=[])

    with patch("qdrant_client.AsyncQdrantClient") as mock_async_client:
        mock_async_client.return_value = mock_client

        from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage

        global_config = {
            "hybrid_search": HybridSearchConfig(enabled=True)
        }
        storage = QdrantVectorStorage(
            namespace="test_hybrid",
            global_config=global_config,
            embedding_func=MockEmbeddingFunc(),
            meta_fields=set()
        )

        await storage._ensure_collection()

        # Verify collection was created with both dense and sparse
        mock_client.create_collection.assert_called_once()
        call_args = mock_client.create_collection.call_args[1]
        assert "vectors_config" in call_args
        assert "sparse_vectors_config" in call_args
        vectors_config = call_args["vectors_config"]
        sparse_vectors_config = call_args["sparse_vectors_config"]
        assert "dense" in vectors_config
        assert "sparse" in sparse_vectors_config


@pytest.mark.asyncio
async def test_qdrant_hybrid_upsert():
    """Test upserting with both dense and sparse vectors."""
    from nano_graphrag.config import HybridSearchConfig
    from nano_graphrag.llm.providers.sparse import SparseEmbeddingProvider

    mock_client = AsyncMock()
    mock_client.get_collections.return_value = MagicMock(collections=[MagicMock(name="test_hybrid")])

    # Mock sparse embeddings
    mock_sparse = [
        {"indices": [1, 10, 100], "values": [0.5, 0.3, 0.2]},
        {"indices": [2, 20, 200], "values": [0.6, 0.4, 0.1]}
    ]

    with patch("qdrant_client.AsyncQdrantClient") as mock_async_client:
        with patch("nano_graphrag.llm.providers.sparse.SparseEmbeddingProvider.embed") as mock_embed:
            mock_async_client.return_value = mock_client
            mock_embed.return_value = mock_sparse

            from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage

            global_config = {
                "hybrid_search": HybridSearchConfig(enabled=True)
            }
            storage = QdrantVectorStorage(
                namespace="test_hybrid",
                global_config=global_config,
                embedding_func=MockEmbeddingFunc(),
                meta_fields=set()
            )

            # Upsert data
            data = {
                "doc1": {"content": "Executive Order 14282"},
                "doc2": {"content": "Another document"}
            }

            await storage.upsert(data)

            # Verify upsert was called
            mock_client.upsert.assert_called()
            call_args = mock_client.upsert.call_args[1]
            points = call_args["points"]

            # Check first point has both dense and sparse
            point = points[0]
            assert isinstance(point.vector, dict)
            assert "dense" in point.vector
            assert "sparse" in point.vector


@pytest.mark.asyncio
async def test_qdrant_hybrid_query():
    """Test hybrid query execution."""
    from nano_graphrag.config import HybridSearchConfig
    from nano_graphrag.llm.providers.sparse import SparseEmbeddingProvider

    mock_client = AsyncMock()
    mock_client.get_collections.return_value = MagicMock(collections=[MagicMock(name="test_hybrid")])

    # Mock query response
    mock_hit = MagicMock()
    mock_hit.payload = {"id": "doc1", "content": "Executive Order 14282"}
    mock_hit.score = 0.95
    mock_response = MagicMock()
    mock_response.points = [mock_hit]
    mock_client.query_points.return_value = mock_response

    # Mock sparse embedding
    mock_sparse = [{"indices": [14282], "values": [0.9]}]

    with patch("qdrant_client.AsyncQdrantClient") as mock_async_client:
        with patch("nano_graphrag.llm.providers.sparse.SparseEmbeddingProvider.embed") as mock_embed:
            mock_async_client.return_value = mock_client
            mock_embed.return_value = mock_sparse

            from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage

            global_config = {
                "hybrid_search": HybridSearchConfig(enabled=True)
            }
            storage = QdrantVectorStorage(
                namespace="test_hybrid",
                global_config=global_config,
                embedding_func=MockEmbeddingFunc(),
                meta_fields=set()
            )

            # Execute query
            results = await storage.query("EO 14282", top_k=5)

            # Verify hybrid search was used
            mock_client.query_points.assert_called_once()
            call_args = mock_client.query_points.call_args[1]
            assert "prefetch" in call_args  # Hybrid uses prefetch
            assert len(call_args["prefetch"]) == 3  # Name, content, and dense

            # Check results
            assert len(results) == 1
            assert results[0]["id"] == "doc1"
            assert "14282" in results[0]["content"]


@pytest.mark.asyncio
async def test_qdrant_hybrid_fallback_to_dense():
    """Test fallback to dense when sparse fails."""
    from nano_graphrag.config import HybridSearchConfig
    from nano_graphrag.llm.providers.sparse import SparseEmbeddingProvider

    mock_client = AsyncMock()
    mock_client.get_collections.return_value = MagicMock(collections=[MagicMock(name="test_hybrid")])

    # Mock query response
    mock_hit = MagicMock()
    mock_hit.payload = {"id": "doc1", "content": "Some content"}
    mock_hit.score = 0.85
    mock_response = MagicMock()
    mock_response.points = [mock_hit]
    mock_client.query_points.return_value = mock_response

    with patch("qdrant_client.AsyncQdrantClient") as mock_async_client:
        with patch("nano_graphrag.llm.providers.sparse.SparseEmbeddingProvider.embed") as mock_embed:
            mock_async_client.return_value = mock_client
            # Simulate sparse embedding failure
            mock_embed.side_effect = Exception("Sparse model failed")

            from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage

            global_config = {
                "hybrid_search": HybridSearchConfig(enabled=True)
            }
            storage = QdrantVectorStorage(
                namespace="test_hybrid",
                global_config=global_config,
                embedding_func=MockEmbeddingFunc(),
                meta_fields=set()
            )

            # Execute query - should fallback to dense
            results = await storage.query("test query", top_k=5)

            # Verify dense search was used
            mock_client.query_points.assert_called()
            call_args = mock_client.query_points.call_args[1]
            # Fallback uses named vector ("dense", embedding)
            query_arg = call_args["query"]
            assert isinstance(query_arg, tuple)
            assert query_arg[0] == "dense"

            assert len(results) == 1


@pytest.mark.asyncio
async def test_qdrant_dense_only_when_disabled():
    """Test that hybrid is not used when disabled."""
    from nano_graphrag.config import HybridSearchConfig

    mock_client = AsyncMock()
    mock_client.get_collections.return_value = MagicMock(collections=[MagicMock(name="test_dense")])

    # Mock query response
    mock_response = MagicMock()
    mock_response.points = []
    mock_client.query_points.return_value = mock_response

    with patch("qdrant_client.AsyncQdrantClient") as mock_async_client:
        mock_async_client.return_value = mock_client

        from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage

        global_config = {
            "hybrid_search": HybridSearchConfig(enabled=False)
        }
        storage = QdrantVectorStorage(
            namespace="test_dense",
            global_config=global_config,
            embedding_func=MockEmbeddingFunc(),
            meta_fields=set()
        )

        # Should not be hybrid
        assert not storage._enable_hybrid

        # Execute query
        await storage.query("test", top_k=5)

        # Verify regular dense search was used
        mock_client.query_points.assert_called_once()
        call_args = mock_client.query_points.call_args[1]
        assert "prefetch" not in call_args  # No prefetch for dense-only
        assert isinstance(call_args["query"], list)  # Direct embedding list


@pytest.mark.asyncio
async def test_qdrant_config_only_no_env():
    """Test that hybrid search works with config object only, no env vars."""
    from nano_graphrag.config import HybridSearchConfig

    # Clear all relevant environment variables
    import os
    env_vars_to_clear = [
        "ENABLE_HYBRID_SEARCH", "SPARSE_MODEL", "HYBRID_DEVICE",
        "RRF_K", "SPARSE_TOP_K_MULTIPLIER", "DENSE_TOP_K_MULTIPLIER",
        "SPARSE_TIMEOUT_MS", "SPARSE_BATCH_SIZE", "SPARSE_MAX_LENGTH"
    ]

    # Store original values
    original_env = {}
    for var in env_vars_to_clear:
        original_env[var] = os.environ.pop(var, None)

    try:
        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])

        with patch("qdrant_client.AsyncQdrantClient") as mock_async_client:
            mock_async_client.return_value = mock_client

            from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage

            # Create config purely from code, no env vars
            hybrid_config = HybridSearchConfig(
                enabled=True,
                rrf_k=42,  # Non-default value to prove it's from config
                sparse_top_k_multiplier=3.0,
                dense_top_k_multiplier=1.5
            )

            global_config = {
                "hybrid_search": hybrid_config
            }

            storage = QdrantVectorStorage(
                namespace="test_config_only",
                global_config=global_config,
                embedding_func=MockEmbeddingFunc(),
                meta_fields=set()
            )

            # Verify config was properly applied
            assert storage._enable_hybrid is True
            assert storage._hybrid_config.enabled is True
            assert storage._hybrid_config.rrf_k == 42
            assert storage._hybrid_config.sparse_top_k_multiplier == 3.0

            await storage._ensure_collection()

            # Verify hybrid collection was created
            mock_client.create_collection.assert_called_once()
            call_args = mock_client.create_collection.call_args[1]
            assert "vectors_config" in call_args
            assert "sparse_vectors_config" in call_args
            vectors_config = call_args["vectors_config"]
            sparse_vectors_config = call_args["sparse_vectors_config"]
            assert "dense" in vectors_config
            assert "sparse" in sparse_vectors_config

    finally:
        # Restore original environment variables
        for var, value in original_env.items():
            if value is not None:
                os.environ[var] = value