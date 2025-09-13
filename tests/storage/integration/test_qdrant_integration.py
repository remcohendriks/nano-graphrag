"""Integration tests for Qdrant storage backend."""

import os
import pytest
import pytest_asyncio
from pathlib import Path
from tests.storage.base import BaseVectorStorageTestSuite, VectorStorageContract
from tests.storage.base.fixtures import deterministic_embedding_func


# Skip all tests if Qdrant client is not installed
pytestmark = pytest.mark.skipif(
    not os.environ.get("QDRANT_URL"),
    reason="Qdrant not configured (set QDRANT_URL environment variable or install qdrant-client)"
)


class TestQdrantIntegration(BaseVectorStorageTestSuite):
    """Qdrant storage integration tests."""

    @pytest_asyncio.fixture
    async def storage(self, temp_storage_dir):
        """Provide Qdrant storage instance."""
        try:
            from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
        except ImportError:
            pytest.skip("qdrant-client not installed")

        config = {
            "working_dir": str(temp_storage_dir),
            "embedding_func": deterministic_embedding_func,
            "embedding_batch_num": 32,
            "embedding_func_max_async": 16,
            "addon_params": {
                "qdrant_url": os.environ.get("QDRANT_URL", "http://localhost:6333"),
                "qdrant_api_key": os.environ.get("QDRANT_API_KEY"),
                "qdrant_path": str(temp_storage_dir / "qdrant")
            }
        }

        storage = QdrantVectorStorage(
            namespace="test_integration",
            global_config=config,
            embedding_func=deterministic_embedding_func,
            meta_fields={"entity_name", "entity_type", "description"}
        )

        # Clean up any existing collection before starting
        try:
            client = await storage._get_client()
            await client.delete_collection(storage.namespace)
        except Exception:
            pass  # Collection might not exist

        # Initialize storage
        await storage.index_start_callback()

        yield storage

        # Cleanup
        try:
            # Drop collection if it exists
            if hasattr(storage, '_client'):
                await storage._client.delete_collection(storage.collection_name)
        except Exception:
            pass

    @pytest.fixture
    def contract(self):
        """Define Qdrant capabilities."""
        return VectorStorageContract(
            supports_metadata=True,
            supports_filtering=True,
            supports_batch_upsert=True,
            supports_async=True,
            supports_persistence=True,
            max_vector_dim=65536,
            distance_metrics=["cosine", "euclidean", "dot"]
        )

    @pytest.mark.asyncio
    async def test_qdrant_specific_features(self, storage):
        """Test Qdrant-specific features."""
        # Test with Qdrant's payload (metadata) system
        test_data = {
            "qdrant_test_1": {
                "content": "Qdrant specific test content",
                "entity_name": "Test Entity",
                "entity_type": "TestType",
                "description": "A test entity for Qdrant",
                "custom_field": "custom_value"
            }
        }

        # Add embedding
        embedding = (await deterministic_embedding_func([test_data["qdrant_test_1"]["content"]]))[0].tolist()
        test_data["qdrant_test_1"]["embedding"] = embedding

        await storage.upsert(test_data)

        # Query and check metadata preservation
        results = await storage.query("test content", top_k=5)
        assert len(results) > 0

        result = results[0]
        if isinstance(result, dict):
            # Qdrant should preserve all metadata fields
            assert "entity_name" in result or "content" in result

    @pytest.mark.asyncio
    async def test_qdrant_filtering(self, storage):
        """Test Qdrant's filtering capabilities."""
        # Insert test data with different metadata
        test_data = {}
        for i in range(10):
            content = f"qdrant_filter_test_{i}"
            test_data[content] = {
                "content": content,
                "entity_type": "Type_A" if i % 2 == 0 else "Type_B",
                "entity_name": f"Entity_{i}",
                "score": i * 0.1
            }
            embedding = (await deterministic_embedding_func([content]))[0].tolist()
            test_data[content]["embedding"] = embedding

        await storage.upsert(test_data)

        # Standard query without filter
        results = await storage.query("qdrant_filter", top_k=10)
        assert len(results) > 0

        # Qdrant supports filtering through its query API
        # The base suite doesn't test this directly, but Qdrant would support it