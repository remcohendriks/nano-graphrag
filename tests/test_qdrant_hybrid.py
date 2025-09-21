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
    with patch.dict(os.environ, {"ENABLE_HYBRID_SEARCH": "true"}):
        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])

        with patch("qdrant_client.AsyncQdrantClient") as mock_async_client:
            mock_async_client.return_value = mock_client

            from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage

            storage = QdrantVectorStorage(
                namespace="test_hybrid",
                global_config={},
                embedding_func=MockEmbeddingFunc(),
                meta_fields=set()
            )

            await storage._ensure_collection()

            # Verify collection was created with both dense and sparse
            mock_client.create_collection.assert_called_once()
            call_args = mock_client.create_collection.call_args[1]
            assert "vectors_config" in call_args
            vectors_config = call_args["vectors_config"]
            assert "dense" in vectors_config
            assert "sparse" in vectors_config


@pytest.mark.asyncio
async def test_qdrant_hybrid_upsert():
    """Test upserting with both dense and sparse vectors."""
    with patch.dict(os.environ, {"ENABLE_HYBRID_SEARCH": "true"}):
        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(collections=[MagicMock(name="test_hybrid")])

        # Mock sparse embeddings
        mock_sparse = [
            {"indices": [1, 10, 100], "values": [0.5, 0.3, 0.2]},
            {"indices": [2, 20, 200], "values": [0.6, 0.4, 0.1]}
        ]

        with patch("qdrant_client.AsyncQdrantClient") as mock_async_client:
            with patch("nano_graphrag._storage.sparse_embed.get_sparse_embeddings") as mock_get_sparse:
                mock_async_client.return_value = mock_client
                mock_get_sparse.return_value = mock_sparse

                from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage

                storage = QdrantVectorStorage(
                    namespace="test_hybrid",
                    global_config={},
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
    with patch.dict(os.environ, {"ENABLE_HYBRID_SEARCH": "true"}):
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
            with patch("nano_graphrag._storage.sparse_embed.get_sparse_embeddings") as mock_get_sparse:
                mock_async_client.return_value = mock_client
                mock_get_sparse.return_value = mock_sparse

                from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage

                storage = QdrantVectorStorage(
                    namespace="test_hybrid",
                    global_config={},
                    embedding_func=MockEmbeddingFunc(),
                    meta_fields=set()
                )

                # Execute query
                results = await storage.query("EO 14282", top_k=5)

                # Verify hybrid search was used
                mock_client.query_points.assert_called_once()
                call_args = mock_client.query_points.call_args[1]
                assert "prefetch" in call_args  # Hybrid uses prefetch
                assert len(call_args["prefetch"]) == 2  # Dense and sparse

                # Check results
                assert len(results) == 1
                assert results[0]["id"] == "doc1"
                assert "14282" in results[0]["content"]


@pytest.mark.asyncio
async def test_qdrant_hybrid_fallback_to_dense():
    """Test fallback to dense when sparse fails."""
    with patch.dict(os.environ, {"ENABLE_HYBRID_SEARCH": "true"}):
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
            with patch("nano_graphrag._storage.sparse_embed.get_sparse_embeddings") as mock_get_sparse:
                mock_async_client.return_value = mock_client
                # Simulate sparse embedding failure
                mock_get_sparse.side_effect = Exception("Sparse model failed")

                from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage

                storage = QdrantVectorStorage(
                    namespace="test_hybrid",
                    global_config={},
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
    with patch.dict(os.environ, {"ENABLE_HYBRID_SEARCH": "false"}):
        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(collections=[MagicMock(name="test_dense")])

        # Mock query response
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response

        with patch("qdrant_client.AsyncQdrantClient") as mock_async_client:
            mock_async_client.return_value = mock_client

            from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage

            storage = QdrantVectorStorage(
                namespace="test_dense",
                global_config={},
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