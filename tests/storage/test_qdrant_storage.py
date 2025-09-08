"""Tests for Qdrant vector storage."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import numpy as np

pytest_plugins = ["pytest_asyncio"]


class TestQdrantStorage:
    """Unit tests for QdrantVectorStorage."""
    
    @pytest.fixture
    def mock_embedding_func(self):
        """Mock embedding function."""
        func = AsyncMock()
        func.embedding_dim = 128
        func.return_value = [[0.1] * 128]
        return func
    
    @pytest.fixture
    def mock_global_config(self):
        """Mock global configuration."""
        return {
            "qdrant_url": "http://localhost:6333",
            "qdrant_api_key": None,
            "qdrant_collection_params": {},
            "working_dir": "/tmp/test"
        }
    
    @pytest.mark.asyncio
    async def test_initialization(self, mock_embedding_func, mock_global_config):
        """Test QdrantVectorStorage initialization."""
        with patch("nano_graphrag._storage.vdb_qdrant.ensure_dependency"):
            with patch("qdrant_client.AsyncQdrantClient") as mock_client:
                from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
                
                storage = QdrantVectorStorage(
                    namespace="test",
                    global_config=mock_global_config,
                    embedding_func=mock_embedding_func
                )
                
                # Check client was created with correct params
                mock_client.assert_called_once_with(
                    url="http://localhost:6333",
                    api_key=None
                )
                
                assert storage.namespace == "test"
                assert storage._collection_initialized == False
    
    @pytest.mark.asyncio
    async def test_ensure_collection_creates_if_not_exists(self, mock_embedding_func, mock_global_config):
        """Test collection creation when it doesn't exist."""
        with patch("nano_graphrag._storage.vdb_qdrant.ensure_dependency"):
            with patch("qdrant_client.AsyncQdrantClient") as mock_client_class:
                with patch("qdrant_client.models") as mock_models:
                    mock_client = AsyncMock()
                    mock_client_class.return_value = mock_client
                    
                    # Mock get_collections to return empty list
                    mock_collections = Mock()
                    mock_collections.collections = []
                    mock_client.get_collections.return_value = mock_collections
                    
                    from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
                    
                    storage = QdrantVectorStorage(
                        namespace="test_collection",
                        global_config=mock_global_config,
                        embedding_func=mock_embedding_func
                    )
                    storage._models = mock_models
                    
                    await storage._ensure_collection()
                    
                    # Check collection was created
                    mock_client.create_collection.assert_called_once()
                    call_args = mock_client.create_collection.call_args
                    assert call_args.kwargs["collection_name"] == "test_collection"
                    assert storage._collection_initialized == True
    
    @pytest.mark.asyncio
    async def test_upsert_with_content(self, mock_embedding_func, mock_global_config):
        """Test upserting data with content field."""
        with patch("nano_graphrag._storage.vdb_qdrant.AsyncQdrantClient") as mock_client_class:
            with patch("nano_graphrag._storage.vdb_qdrant.ensure_dependency"):
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                # Mock collection exists
                mock_collections = Mock()
                mock_collections.collections = [Mock(name="test")]
                mock_client.get_collections.return_value = mock_collections
                
                with patch("nano_graphrag._storage.vdb_qdrant.models") as mock_models:
                    mock_point_struct = Mock()
                    mock_models.PointStruct = mock_point_struct
                    
                    from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
                    
                    storage = QdrantVectorStorage(
                        namespace="test",
                        global_config=mock_global_config,
                        embedding_func=mock_embedding_func
                    )
                    storage._models = mock_models
                    
                    # Test data
                    test_data = {
                        "test_content_1": {
                            "content": "This is test content",
                            "metadata": "test_meta"
                        }
                    }
                    
                    await storage.upsert(test_data)
                    
                    # Check upsert was called
                    mock_client.upsert.assert_called_once()
                    
                    # Check PointStruct was created
                    mock_point_struct.assert_called_once()
                    point_args = mock_point_struct.call_args
                    
                    # Check ID is a hash-based integer
                    assert isinstance(point_args.kwargs["id"], int)
                    
                    # Check payload contains content
                    assert point_args.kwargs["payload"]["content"] == "This is test content"
                    assert point_args.kwargs["payload"]["metadata"] == "test_meta"
    
    @pytest.mark.asyncio
    async def test_query_returns_formatted_results(self, mock_embedding_func, mock_global_config):
        """Test query returns properly formatted results."""
        with patch("nano_graphrag._storage.vdb_qdrant.AsyncQdrantClient") as mock_client_class:
            with patch("nano_graphrag._storage.vdb_qdrant.ensure_dependency"):
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                # Mock collection exists
                mock_collections = Mock()
                mock_collections.collections = [Mock(name="test")]
                mock_client.get_collections.return_value = mock_collections
                
                # Mock search results
                mock_hit = Mock()
                mock_hit.score = 0.95
                mock_hit.payload = {
                    "content": "Result content",
                    "entity_name": "test_entity",
                    "custom_field": "custom_value"
                }
                mock_client.search.return_value = [mock_hit]
                
                from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
                
                storage = QdrantVectorStorage(
                    namespace="test",
                    global_config=mock_global_config,
                    embedding_func=mock_embedding_func
                )
                
                results = await storage.query("test query", top_k=5)
                
                # Check search was called
                mock_client.search.assert_called_once()
                search_args = mock_client.search.call_args
                assert search_args.kwargs["collection_name"] == "test"
                assert search_args.kwargs["limit"] == 5
                
                # Check result format
                assert len(results) == 1
                assert results[0]["content"] == "Result content"
                assert results[0]["score"] == 0.95
                assert results[0]["entity_name"] == "test_entity"
                assert results[0]["custom_field"] == "custom_value"
    
    @pytest.mark.asyncio
    async def test_empty_upsert(self, mock_embedding_func, mock_global_config):
        """Test handling of empty data in upsert."""
        with patch("nano_graphrag._storage.vdb_qdrant.AsyncQdrantClient") as mock_client_class:
            with patch("nano_graphrag._storage.vdb_qdrant.ensure_dependency"):
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
                
                storage = QdrantVectorStorage(
                    namespace="test",
                    global_config=mock_global_config,
                    embedding_func=mock_embedding_func
                )
                
                # Upsert empty data
                await storage.upsert({})
                
                # Should not call client.upsert
                mock_client.upsert.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_context_manager(self, mock_embedding_func, mock_global_config):
        """Test async context manager functionality."""
        with patch("nano_graphrag._storage.vdb_qdrant.AsyncQdrantClient") as mock_client_class:
            with patch("nano_graphrag._storage.vdb_qdrant.ensure_dependency"):
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
                
                async with QdrantVectorStorage(
                    namespace="test",
                    global_config=mock_global_config,
                    embedding_func=mock_embedding_func
                ) as storage:
                    assert storage is not None
                
                # Check client.close was called on exit
                mock_client.close.assert_called_once()


@pytest.mark.integration
class TestQdrantIntegration:
    """Integration tests with real Qdrant instance."""
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Integration tests require running Qdrant instance")
    async def test_end_to_end_with_docker_qdrant(self):
        """Test end-to-end with Docker Qdrant instance."""
        try:
            from qdrant_client import AsyncQdrantClient
            from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
        except ImportError:
            pytest.skip("qdrant-client not installed")
        
        # Check if Qdrant is running
        client = AsyncQdrantClient(url="http://localhost:6333")
        try:
            await client.get_collections()
        except Exception:
            pytest.skip("Qdrant not running at localhost:6333")
        finally:
            await client.close()
        
        # Create mock embedding function
        async def mock_embed(texts):
            return [np.random.rand(128).tolist() for _ in texts]
        
        mock_embed.embedding_dim = 128
        
        # Test with real Qdrant
        config = {
            "qdrant_url": "http://localhost:6333",
            "working_dir": "/tmp/test"
        }
        
        storage = QdrantVectorStorage(
            namespace="test_integration",
            global_config=config,
            embedding_func=mock_embed
        )
        
        # Test upsert
        test_data = {
            f"doc_{i}": {
                "content": f"Document number {i}",
                "index": i
            }
            for i in range(10)
        }
        
        await storage.upsert(test_data)
        
        # Test query
        results = await storage.query("Document number 5", top_k=3)
        
        assert len(results) > 0
        assert "content" in results[0]
        assert "score" in results[0]
        
        # Cleanup
        client = AsyncQdrantClient(url="http://localhost:6333")
        await client.delete_collection("test_integration")
        await client.close()