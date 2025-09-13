"""Contract-based tests for HNSW vector storage."""

import pytest
import pytest_asyncio
from pathlib import Path
from tests.storage.base import BaseVectorStorageTestSuite, VectorStorageContract
from tests.storage.base.fixtures import deterministic_embedding_func
from nano_graphrag._storage import HNSWVectorStorage


class TestHNSWContract(BaseVectorStorageTestSuite):
    """HNSW storage contract tests."""

    @pytest_asyncio.fixture
    async def storage(self, temp_storage_dir):
        """Provide HNSW storage instance."""
        config = {
            "working_dir": str(temp_storage_dir),
            "embedding_func": deterministic_embedding_func,
            "embedding_batch_num": 32,
            "embedding_func_max_async": 16,
            "vector_db_storage_cls_kwargs": {
                "ef_construction": 100,
                "M": 16,
                "ef_search": 50,
                "max_elements": 10000
            }
        }

        # Ensure directory exists
        Path(config["working_dir"]).mkdir(parents=True, exist_ok=True)

        storage = HNSWVectorStorage(
            namespace="test",
            global_config=config,
            embedding_func=deterministic_embedding_func,
            meta_fields={"entity_name", "entity_type", "description"}
        )

        yield storage

        # Cleanup is automatic with temp dir

    @pytest.fixture
    def contract(self):
        """Define HNSW capabilities."""
        return VectorStorageContract(
            supports_metadata=True,
            supports_filtering=False,  # HNSW doesn't support filtering
            supports_batch_upsert=True,
            supports_async=True,
            supports_persistence=True,
            max_vector_dim=None,  # Technically unlimited
            max_vectors=1000000,  # Default max_elements
            distance_metrics=["cosine", "l2", "ip"]
        )