"""Test HNSW vector storage functionality."""
import os
import shutil
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch
from dataclasses import asdict
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, StorageConfig
from nano_graphrag._utils import wrap_embedding_func_with_attrs
from nano_graphrag._storage import HNSWVectorStorage


@pytest.fixture(scope="function")
def temp_dir(tmp_path):
    """Use pytest's tmp_path for temporary directories."""
    return str(tmp_path)


@wrap_embedding_func_with_attrs(embedding_dim=384, max_token_size=8192)
async def mock_embedding(texts: list[str]) -> np.ndarray:
    return np.random.rand(len(texts), 384)


@pytest.fixture
def hnsw_storage(temp_dir):
    """Create HNSW storage with proper config."""
    # Create minimal config dict for storage
    global_config = {
        "working_dir": temp_dir,
        "embedding_func": mock_embedding,
        "embedding_batch_num": 32,
        "embedding_func_max_async": 16,
        "vector_db_storage_cls_kwargs": {
            "ef_construction": 100,
            "M": 16,
            "ef_search": 50,
            "max_elements": 1000
        }
    }
    
    # Ensure the directory exists
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    
    return HNSWVectorStorage(
        namespace="test",
        global_config=global_config,
        embedding_func=mock_embedding,
        meta_fields={"entity_name"},
    )


@pytest.mark.asyncio
async def test_upsert_and_query(hnsw_storage):
    # Build the payload the storage expects: dict[str, dict] with 'content' field
    payload = {
        'Apple':  {'content': 'A fruit that is red or green', 'entity_name': 'Apple'},
        'Banana': {'content': 'A yellow fruit that is curved', 'entity_name': 'Banana'},
        'Orange': {'content': 'An orange fruit that is round', 'entity_name': 'Orange'},
    }

    await hnsw_storage.upsert(payload)

    results = await hnsw_storage.query("A fruit", top_k=2)
    assert len(results) == 2
    assert all("entity_name" in result for result in results)
    assert all("distance" in result for result in results)


@pytest.mark.asyncio
async def test_persistence(temp_dir):
    """Test storage persistence."""
    global_config = {
        "working_dir": temp_dir,
        "embedding_func": mock_embedding,
        "embedding_batch_num": 32,
        "embedding_func_max_async": 16,
        "vector_db_storage_cls_kwargs": {
            "ef_construction": 100,
            "M": 16,
            "ef_search": 50,
            "max_elements": 1000
        }
    }
    
    initial_storage = HNSWVectorStorage(
        namespace="test_persistence",
        global_config=global_config,
        embedding_func=mock_embedding,
        meta_fields={"entity_name"},
    )

    # Use correct API: dict[str, dict] with content field
    payload = {"Apple": {"entity_name": "Apple", "content": "A fruit"}}
    await initial_storage.upsert(payload)
    await initial_storage.index_done_callback()

    # Create new storage instance
    new_storage = HNSWVectorStorage(
        namespace="test_persistence",
        global_config=global_config,
        embedding_func=mock_embedding,
        meta_fields={"entity_name"},
    )

    results = await new_storage.query("fruit", top_k=1)
    assert len(results) == 1
    assert results[0]["entity_name"] == "Apple"


@pytest.mark.asyncio
async def test_multiple_upserts(hnsw_storage):
    """Test multiple upsert operations."""
    # First upsert
    payload1 = {
        "Apple": {"entity_name": "Apple", "content": "A red fruit"}
    }
    await hnsw_storage.upsert(payload1)
    
    # Second upsert
    payload2 = {
        "Banana": {"entity_name": "Banana", "content": "A yellow fruit"}
    }
    await hnsw_storage.upsert(payload2)

    # Query should find both
    results = await hnsw_storage.query("fruit", top_k=10)
    assert len(results) == 2
    entity_names = {r["entity_name"] for r in results}
    assert "Apple" in entity_names
    assert "Banana" in entity_names


@pytest.mark.asyncio
async def test_embedding_function(hnsw_storage):
    """Test that embedding function is correctly used."""
    test_text = "test content"
    
    # Mock the embedding function to verify it's called
    with patch.object(hnsw_storage, 'embedding_func', wraps=hnsw_storage.embedding_func) as mock_embed:
        payload = {"Test": {"entity_name": "Test", "content": test_text}}
        await hnsw_storage.upsert(payload)
        
        # Verify embedding function was called (don't check specific args as batching can vary)
        mock_embed.assert_called()
        # Just verify it was called at least once
        assert mock_embed.call_count >= 1


@pytest.mark.asyncio
async def test_max_elements_limit(temp_dir):
    """Test max_elements configuration."""
    global_config = {
        "working_dir": temp_dir,
        "embedding_func": mock_embedding,
        "embedding_batch_num": 32,
        "embedding_func_max_async": 16,
        "vector_db_storage_cls_kwargs": {
            "ef_construction": 100,
            "M": 16,
            "ef_search": 50,
            "max_elements": 5  # Small limit for testing
        }
    }
    
    storage = HNSWVectorStorage(
        namespace="test_limit",
        global_config=global_config,
        embedding_func=mock_embedding,
        meta_fields={"id"},
    )
    
    # Insert up to the limit - use correct API format
    payload = {f"item_{i}": {"id": f"item_{i}", "content": f"content {i}"} for i in range(5)}
    await storage.upsert(payload)
    
    results = await storage.query("content", top_k=10)
    assert len(results) == 5


@pytest.mark.asyncio
async def test_empty_query(hnsw_storage):
    """Test querying empty storage."""
    results = await hnsw_storage.query("test", top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_upsert_empty_dict(hnsw_storage):
    """Test upserting empty dict."""
    await hnsw_storage.upsert({})
    results = await hnsw_storage.query("test", top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_metadata_fields(hnsw_storage):
    """Test that metadata fields are preserved."""
    payload = {
        "TestEntity": {
            "entity_name": "TestEntity",
            "content": "Test content",
            "extra_field": "should not be stored"
        }
    }
    
    await hnsw_storage.upsert(payload)
    results = await hnsw_storage.query("test", top_k=1)
    
    assert len(results) == 1
    assert "entity_name" in results[0]
    assert results[0]["entity_name"] == "TestEntity"
    assert "extra_field" not in results[0]  # Only meta_fields should be stored


@pytest.mark.asyncio
async def test_distance_calculation(hnsw_storage):
    """Test that distances are calculated correctly."""
    # Insert items with correct API format
    payload = {
        "A": {"entity_name": "A", "content": "first"},
        "B": {"entity_name": "B", "content": "second"}
    }
    
    await hnsw_storage.upsert(payload)
    
    results = await hnsw_storage.query("first", top_k=2)
    
    # Verify distances are included and ordered
    assert len(results) == 2
    assert all("distance" in r for r in results)
    assert results[0]["distance"] <= results[1]["distance"]  # Closest first