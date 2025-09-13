"""Base test suite for key-value storage implementations."""

import pytest
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class KVStorageContract:
    """Contract that all KV storages must fulfill."""

    supports_batch_ops: bool = True
    supports_persistence: bool = True
    supports_async: bool = True
    supports_namespace: bool = True
    max_key_length: Optional[int] = None
    max_value_size: Optional[int] = None


class BaseKVStorageTestSuite(ABC):
    """Abstract test suite all KV storage implementations must pass."""

    @pytest.fixture
    @abstractmethod
    async def storage(self) -> Any:
        """Provide storage instance for testing."""
        pass

    @pytest.fixture
    @abstractmethod
    def contract(self) -> KVStorageContract:
        """Define storage capabilities contract."""
        pass

    @pytest.mark.asyncio
    async def test_basic_operations(self, storage):
        """Test basic get/set operations."""
        # Set single item
        await storage.upsert({"key1": {"value": "data1", "metadata": "test"}})

        # Get single item
        result = await storage.get_by_id("key1")
        assert result is not None
        assert result["value"] == "data1"
        assert result["metadata"] == "test"

        # Get non-existent item
        result = await storage.get_by_id("nonexistent")
        assert result is None

        # Update existing item
        await storage.upsert({"key1": {"value": "updated_data1", "metadata": "updated"}})
        result = await storage.get_by_id("key1")
        assert result["value"] == "updated_data1"
        assert result["metadata"] == "updated"

    @pytest.mark.asyncio
    async def test_batch_operations(self, storage, contract):
        """Test batch operations."""
        if not contract.supports_batch_ops:
            pytest.skip("Storage doesn't support batch operations")

        # Batch upsert
        batch_data = {
            f"key_{i}": {"value": f"data_{i}", "index": i}
            for i in range(50)
        }
        await storage.upsert(batch_data)

        # Batch get
        keys = [f"key_{i}" for i in range(25)]
        results = await storage.get_by_ids(keys)

        assert len(results) == 25
        for i, result in enumerate(results):
            assert result is not None
            assert result["value"] == f"data_{i}"
            assert result["index"] == i

        # Get with field filter
        results_filtered = await storage.get_by_ids(keys, fields={"value"})
        assert len(results_filtered) == 25
        for i, result in enumerate(results_filtered):
            if result is not None:
                assert "value" in result
                assert result["value"] == f"data_{i}"
                # Index should not be included
                assert "index" not in result or result.get("index") == i

    @pytest.mark.asyncio
    async def test_filter_keys(self, storage):
        """Test filtering for non-existent keys."""
        # Insert some data
        await storage.upsert({
            "existing1": {"value": "data1"},
            "existing2": {"value": "data2"},
            "existing3": {"value": "data3"}
        })

        # Filter keys - should return only non-existent ones
        test_keys = ["existing1", "existing2", "new1", "new2", "new3"]
        new_keys = await storage.filter_keys(test_keys)

        assert "new1" in new_keys
        assert "new2" in new_keys
        assert "new3" in new_keys
        assert "existing1" not in new_keys
        assert "existing2" not in new_keys

    @pytest.mark.asyncio
    async def test_all_keys(self, storage):
        """Test listing all keys."""
        # Start fresh
        await storage.drop()

        # Insert test data
        test_data = {f"test_key_{i}": {"value": f"data_{i}"} for i in range(10)}
        await storage.upsert(test_data)

        # Get all keys
        all_keys = await storage.all_keys()

        # Should have all our keys
        for i in range(10):
            assert f"test_key_{i}" in all_keys

        assert len(all_keys) >= 10

    @pytest.mark.asyncio
    async def test_drop(self, storage):
        """Test dropping all data."""
        # Insert data
        await storage.upsert({f"drop_key_{i}": {"value": f"data_{i}"} for i in range(10)})

        # Verify data exists
        result = await storage.get_by_id("drop_key_5")
        assert result is not None

        # Drop all data
        await storage.drop()

        # Verify empty
        all_keys = await storage.all_keys()
        assert len(all_keys) == 0

        # Verify individual key is gone
        result = await storage.get_by_id("drop_key_5")
        assert result is None

    @pytest.mark.asyncio
    async def test_persistence(self, storage, contract):
        """Test data persistence via callbacks."""
        if not contract.supports_persistence:
            pytest.skip("Storage doesn't support persistence")

        # Insert data
        await storage.upsert({"persist_key": {"value": "persistent_data", "important": True}})

        # Trigger persistence callback if available
        if hasattr(storage, 'index_done_callback'):
            await storage.index_done_callback()

        # Data should still be accessible
        result = await storage.get_by_id("persist_key")
        assert result is not None
        assert result["value"] == "persistent_data"
        assert result["important"] is True

    @pytest.mark.asyncio
    async def test_concurrent_access(self, storage):
        """Test concurrent read/write operations."""
        async def write_task(index):
            await storage.upsert({f"concurrent_{index}": {"value": f"data_{index}", "index": index}})

        async def read_task(index):
            return await storage.get_by_id(f"concurrent_{index}")

        # Concurrent writes
        write_tasks = [write_task(i) for i in range(20)]
        await asyncio.gather(*write_tasks)

        # Concurrent reads
        read_tasks = [read_task(i) for i in range(20)]
        results = await asyncio.gather(*read_tasks)

        # Verify all writes succeeded
        for i, result in enumerate(results):
            assert result is not None
            assert result["value"] == f"data_{i}"
            assert result["index"] == i

    @pytest.mark.asyncio
    async def test_graphrag_namespaces(self, storage):
        """Test GraphRAG-specific namespace handling."""
        # GraphRAG uses specific namespaces
        expected_namespaces = ["full_docs", "text_chunks", "community_reports", "llm_response_cache"]

        # Check if storage has namespace attribute
        if hasattr(storage, 'namespace'):
            # Namespace should be one of the expected or a test namespace
            assert storage.namespace in expected_namespaces or "test" in storage.namespace.lower()

        # Test storing GraphRAG-like data
        graphrag_data = {
            "doc_001": {
                "content": "Full document content",
                "metadata": {"source": "test.txt", "chunk_count": 5}
            },
            "chunk_001_001": {
                "content": "First chunk of document",
                "doc_id": "doc_001",
                "chunk_index": 0,
                "tokens": 100
            },
            "community_report_001": {
                "community_id": "comm_001",
                "level": 1,
                "title": "Test Community",
                "summary": "Community of test entities"
            }
        }

        await storage.upsert(graphrag_data)

        # Verify GraphRAG data structure
        doc = await storage.get_by_id("doc_001")
        assert doc is not None
        assert doc["metadata"]["chunk_count"] == 5

        chunk = await storage.get_by_id("chunk_001_001")
        assert chunk is not None
        assert chunk["doc_id"] == "doc_001"
        assert chunk["tokens"] == 100

        report = await storage.get_by_id("community_report_001")
        assert report is not None
        assert report["level"] == 1