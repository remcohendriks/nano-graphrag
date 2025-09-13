"""Contract-based tests for JSON KV storage."""

import pytest
import pytest_asyncio
from pathlib import Path
from tests.storage.base import BaseKVStorageTestSuite, KVStorageContract
from nano_graphrag._storage.kv_json import JsonKVStorage


class TestJsonKVContract(BaseKVStorageTestSuite):
    """JSON KV storage contract tests."""

    @pytest_asyncio.fixture
    async def storage(self, temp_storage_dir):
        """Provide JSON KV storage instance."""
        config = {
            "working_dir": str(temp_storage_dir)
        }

        # Ensure directory exists
        Path(config["working_dir"]).mkdir(parents=True, exist_ok=True)

        storage = JsonKVStorage(
            namespace="test",
            global_config=config
        )

        yield storage

        # Cleanup is automatic with temp dir

    @pytest.fixture
    def contract(self):
        """Define JSON KV capabilities."""
        return KVStorageContract(
            supports_batch_ops=True,
            supports_persistence=True,
            supports_async=True,
            supports_namespace=True,
            max_key_length=None,  # Limited by filesystem
            max_value_size=None  # Limited by memory/disk
        )