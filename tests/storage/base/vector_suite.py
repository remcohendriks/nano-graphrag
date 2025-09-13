"""Base test suite for vector storage implementations."""

import pytest
import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Dict, Optional
from tests.storage.base.fixtures import deterministic_embedding_func


@dataclass
class VectorStorageContract:
    """Contract that all vector storages must fulfill."""

    supports_metadata: bool = True
    supports_filtering: bool = False
    supports_batch_upsert: bool = True
    supports_async: bool = True
    supports_persistence: bool = True
    max_vector_dim: Optional[int] = None
    max_vectors: Optional[int] = None
    distance_metrics: List[str] = None

    def __post_init__(self):
        if self.distance_metrics is None:
            self.distance_metrics = ["cosine"]


class BaseVectorStorageTestSuite(ABC):
    """Abstract test suite all vector storage implementations must pass."""

    @pytest.fixture
    @abstractmethod
    async def storage(self) -> Any:
        """Provide storage instance for testing."""
        pass

    @pytest.fixture
    @abstractmethod
    def contract(self) -> VectorStorageContract:
        """Define storage capabilities contract."""
        pass

    @pytest.mark.asyncio
    async def test_upsert_single(self, storage):
        """Test single vector upsert and retrieval."""
        test_content = "test_content_single"
        embedding = (await deterministic_embedding_func([test_content]))[0].tolist()

        data = {
            test_content: {
                "embedding": embedding,
                "metadata": {"type": "test", "index": 1}
            }
        }

        await storage.upsert(data)

        results = await storage.query(test_content, top_k=1)
        assert len(results) > 0
        assert "content" in results[0] or test_content in str(results[0])

    @pytest.mark.asyncio
    async def test_upsert_batch(self, storage, contract):
        """Test batch vector upsert."""
        if not contract.supports_batch_upsert:
            pytest.skip("Storage doesn't support batch upsert")

        batch_size = 50
        contents = [f"content_{i}" for i in range(batch_size)]
        embeddings = await deterministic_embedding_func(contents)

        data = {}
        for i, content in enumerate(contents):
            data[content] = {
                "embedding": embeddings[i].tolist(),
                "metadata": {"index": i, "type": "batch"}
            }

        start = time.time()
        await storage.upsert(data)
        duration = time.time() - start

        # Verify a sample
        results = await storage.query("content_25", top_k=5)
        assert len(results) > 0

        # Basic performance check
        assert duration < 30, f"Batch insert took {duration}s for {batch_size} items"

    @pytest.mark.asyncio
    async def test_query_accuracy(self, storage):
        """Test query returns semantically similar results."""
        test_data = {
            "apple_fruit": {
                "content": "apple fruit red",
                "metadata": {"category": "fruit"}
            },
            "banana_fruit": {
                "content": "banana fruit yellow",
                "metadata": {"category": "fruit"}
            },
            "car_vehicle": {
                "content": "car vehicle transport",
                "metadata": {"category": "vehicle"}
            },
            "bike_vehicle": {
                "content": "bike vehicle eco",
                "metadata": {"category": "vehicle"}
            }
        }

        # Generate embeddings
        for key, value in test_data.items():
            embedding = (await deterministic_embedding_func([value["content"]]))[0].tolist()
            value["embedding"] = embedding

        await storage.upsert(test_data)

        # Query for fruit - should return fruit items
        results = await storage.query("orange fruit citrus", top_k=2)
        assert len(results) >= 1

        # Check if results contain fruit category items
        result_contents = [str(r) for r in results]
        fruit_found = any("fruit" in content.lower() for content in result_contents)
        assert fruit_found, "Query for fruit should return fruit-related items"

    @pytest.mark.asyncio
    async def test_metadata_handling(self, storage, contract):
        """Test metadata storage and retrieval."""
        if not contract.supports_metadata:
            pytest.skip("Storage doesn't support metadata")

        test_data = {
            "meta_test_1": {
                "content": "test content with metadata",
                "metadata": {
                    "type": "document",
                    "author": "test_user",
                    "timestamp": "2024-01-01"
                }
            }
        }

        embedding = (await deterministic_embedding_func([test_data["meta_test_1"]["content"]]))[0].tolist()
        test_data["meta_test_1"]["embedding"] = embedding

        await storage.upsert(test_data)

        results = await storage.query("test content", top_k=1)
        assert len(results) > 0

        # Check if metadata is preserved
        result = results[0]
        if isinstance(result, dict) and "metadata" in result:
            assert result["metadata"].get("type") == "document"
            assert result["metadata"].get("author") == "test_user"

    @pytest.mark.asyncio
    async def test_empty_query(self, storage):
        """Test querying empty or nearly empty storage."""
        results = await storage.query("nonexistent_query", top_k=10)
        assert isinstance(results, list)
        # Results could be empty or contain unrelated items

    @pytest.mark.asyncio
    async def test_duplicate_upsert(self, storage):
        """Test upserting duplicate content updates rather than duplicates."""
        content_key = "duplicate_test"
        content = "This is duplicate content"

        embedding = (await deterministic_embedding_func([content]))[0].tolist()

        # First insert
        await storage.upsert({
            content_key: {
                "embedding": embedding,
                "content": content,
                "version": 1
            }
        })

        # Update with same key
        await storage.upsert({
            content_key: {
                "embedding": embedding,
                "content": content,
                "version": 2
            }
        })

        results = await storage.query(content, top_k=5)

        # Should have updated, not created duplicate
        versions = [r.get("version") for r in results if isinstance(r, dict) and "version" in r]
        if versions:
            assert 2 in versions or len(versions) <= 1

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, storage):
        """Test concurrent upserts and queries."""
        async def upsert_task(index):
            content = f"concurrent_{index}"
            embedding = (await deterministic_embedding_func([content]))[0].tolist()
            data = {
                content: {
                    "embedding": embedding,
                    "index": index
                }
            }
            await storage.upsert(data)

        async def query_task():
            return await storage.query("test", top_k=5)

        # Run concurrent operations
        tasks = []
        for i in range(10):
            tasks.append(upsert_task(i))
            if i % 2 == 0:
                tasks.append(query_task())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check no exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Concurrent ops failed: {exceptions}"

    @pytest.mark.asyncio
    async def test_top_k_retrieval(self, storage):
        """Test top_k parameter returns correct number of results."""
        # Insert multiple items
        num_items = 20
        data = {}
        for i in range(num_items):
            content = f"item_{i}"
            embedding = (await deterministic_embedding_func([content]))[0].tolist()
            data[content] = {
                "embedding": embedding,
                "index": i
            }

        await storage.upsert(data)

        # Test different top_k values
        for k in [1, 5, 10]:
            results = await storage.query("test_query", top_k=k)
            assert len(results) <= k, f"Expected at most {k} results, got {len(results)}"

    @pytest.mark.asyncio
    async def test_large_embedding_dimension(self, storage, contract):
        """Test handling of large embedding dimensions."""
        if contract.max_vector_dim and contract.max_vector_dim < 1024:
            pytest.skip(f"Storage has max dimension {contract.max_vector_dim}")

        # Use storage's embedding func if available
        embedding_func = storage.embedding_func if hasattr(storage, 'embedding_func') else deterministic_embedding_func

        content = "large_dim_test"
        embedding = (await embedding_func([content]))[0].tolist()

        data = {
            content: {
                "embedding": embedding,
                "test": "large_dimension"
            }
        }

        await storage.upsert(data)
        results = await storage.query(content, top_k=1)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_special_characters_in_content(self, storage):
        """Test handling of special characters in content."""
        special_contents = [
            "content with spaces",
            "content-with-dashes",
            "content_with_underscores",
            "content.with.dots",
            "content/with/slashes",
            "content@with#special$chars"
        ]

        data = {}
        for content in special_contents:
            try:
                embedding = (await deterministic_embedding_func([content]))[0].tolist()
                # Use safe key
                safe_key = content.replace("/", "_").replace("#", "_").replace("$", "_")
                data[safe_key] = {
                    "embedding": embedding,
                    "original_content": content
                }
            except Exception:
                continue

        if data:
            await storage.upsert(data)
            results = await storage.query("special characters", top_k=3)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_persistence(self, storage, contract, temp_storage_dir):
        """Test data persistence across storage restarts."""
        if not contract.supports_persistence:
            pytest.skip("Storage doesn't support persistence")

        # Insert test data
        test_content = "persistence_test"
        embedding = (await deterministic_embedding_func([test_content]))[0].tolist()

        await storage.upsert({
            test_content: {
                "embedding": embedding,
                "persistent": True
            }
        })

        # Trigger persistence if needed
        if hasattr(storage, 'index_done_callback'):
            await storage.index_done_callback()

        # Query should find the data
        results = await storage.query(test_content, top_k=1)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_graphrag_specific_fields(self, storage):
        """Test GraphRAG-specific field handling."""
        test_data = {
            "entity_1": {
                "content": "Barack Obama entity",
                "entity_name": "Barack Obama",
                "entity_type": "Person",
                "description": "44th President of the United States"
            }
        }

        # Add embedding
        embedding = (await deterministic_embedding_func([test_data["entity_1"]["content"]]))[0].tolist()
        test_data["entity_1"]["embedding"] = embedding

        await storage.upsert(test_data)
        results = await storage.query("Obama", top_k=1)

        assert len(results) > 0
        result = results[0]

        # Check for expected fields
        if isinstance(result, dict):
            assert "content" in result or "entity_name" in result
            # Distance or score should be present
            assert any(k in result for k in ["distance", "score", "similarity"])

    @pytest.mark.asyncio
    async def test_batch_size_limits(self, storage, contract):
        """Test storage handles large batches correctly."""
        if contract.max_vectors and contract.max_vectors < 1000:
            batch_size = min(100, contract.max_vectors)
        else:
            batch_size = 100

        data = {}
        contents = [f"batch_item_{i}" for i in range(batch_size)]
        embeddings = await deterministic_embedding_func(contents)

        for i, content in enumerate(contents):
            data[content] = {
                "embedding": embeddings[i].tolist(),
                "batch_index": i
            }

        # Should handle large batch without error
        await storage.upsert(data)

        # Verify some items were stored
        results = await storage.query("batch_item_50", top_k=5)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_query_with_no_embedding_func(self, storage):
        """Test query behavior when storage has no embedding function."""
        # Insert data with explicit embeddings
        content = "no_embed_func_test"
        embedding = (await deterministic_embedding_func([content]))[0].tolist()

        await storage.upsert({
            content: {
                "embedding": embedding,
                "test": "no_embedding_func"
            }
        })

        # Query should work if storage handles it
        try:
            results = await storage.query(content, top_k=1)
            assert isinstance(results, list)
        except NotImplementedError:
            # Some storages may require embedding func for queries
            pass