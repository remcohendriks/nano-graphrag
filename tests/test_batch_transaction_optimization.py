"""Test batch transaction optimization for NGRAF-022 Phase 2.5"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from nano_graphrag.graphrag import GraphRAG
from nano_graphrag._extraction import DocumentGraphBatch
from nano_graphrag.config import GraphRAGConfig


@pytest.mark.asyncio
async def test_batch_operations_reduce_transactions():
    """Verify that batch operations create fewer transactions than individual operations."""
    # Create a mock Neo4j storage with transaction counting
    mock_storage = AsyncMock()
    mock_storage.upsert_node = AsyncMock()
    mock_storage.upsert_edge = AsyncMock()
    mock_storage.execute_document_batch = AsyncMock()
    mock_storage.get_node = AsyncMock(return_value=None)
    mock_storage.has_node = AsyncMock(return_value=False)
    mock_storage.has_edge = AsyncMock(return_value=False)

    # Create test configuration
    config = GraphRAGConfig()

    # Create GraphRAG instance
    rag = GraphRAG(config=config)

    # Create mock extraction result with multiple entities
    mock_result = MagicMock()
    mock_result.nodes = {
        "entity1": {"entity_type": "PERSON", "description": "Test person 1", "source_id": "chunk1"},
        "entity2": {"entity_type": "PERSON", "description": "Test person 2", "source_id": "chunk1"},
        "entity3": {"entity_type": "ORG", "description": "Test org", "source_id": "chunk2"},
    }
    mock_result.edges = [
        ("entity1", "entity2", {"description": "knows", "source_id": "chunk1", "weight": 1.0}),
        ("entity2", "entity3", {"description": "works at", "source_id": "chunk2", "weight": 1.0}),
    ]

    # Mock the entity extractor
    rag.entity_extractor = AsyncMock()
    rag.entity_extractor.initialize = AsyncMock()
    rag.entity_extractor.extract = AsyncMock(return_value=mock_result)

    # Test chunks
    test_chunks = {
        "chunk1": {"content": "Test content 1"},
        "chunk2": {"content": "Test content 2"},
    }

    # Mock tokenizer with proper methods
    mock_tokenizer = MagicMock()
    mock_tokenizer.encode = MagicMock(return_value=[1, 2, 3])  # Short token list
    mock_tokenizer.decode = MagicMock(return_value="decoded text")

    # Mock global config with required functions
    mock_global_config = {
        "entity_summary_to_max_tokens": 100,
        "cheap_model_func": AsyncMock(return_value="summarized"),
        "cheap_model_max_token_size": 4096,
    }

    # Call the wrapper function
    await rag._extract_entities_wrapper(
        test_chunks,
        mock_storage,
        None,  # entity_vdb
        mock_tokenizer,
        mock_global_config
    )

    # Verify batch execution was called once (not individual upserts)
    assert mock_storage.execute_document_batch.call_count == 1

    # Verify individual upserts were NOT called
    assert mock_storage.upsert_node.call_count == 0
    assert mock_storage.upsert_edge.call_count == 0

    # Verify the batch contains entities and edges
    # Note: _merge_edges_for_batch adds nodes for missing edge endpoints
    batch_arg = mock_storage.execute_document_batch.call_args[0][0]
    assert isinstance(batch_arg, DocumentGraphBatch)
    assert len(batch_arg.nodes) >= 3  # At least the original 3 entities
    assert len(batch_arg.edges) == 2  # Exactly 2 edges as specified


@pytest.mark.asyncio
async def test_neo4j_batch_size_configuration():
    """Test that Neo4j batch size configuration is properly used."""
    from nano_graphrag._storage.gdb_neo4j import Neo4jStorage

    # Mock configuration with custom batch size
    mock_config = {
        "addon_params": {
            "neo4j_url": "neo4j://localhost",
            "neo4j_auth": ("neo4j", "password"),
            "neo4j_batch_size": 500,  # Custom batch size
        }
    }

    with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.neo4j', new_callable=MagicMock):
        # Create storage instance
        storage = Neo4jStorage(
            namespace="test",
            global_config=mock_config
        )
        storage.async_driver = MagicMock()

        # Verify batch size was set from config
        assert storage.neo4j_batch_size == 500

        # Create a batch with many items
        batch = DocumentGraphBatch()
        for i in range(1000):
            batch.add_node(f"node_{i}", {"data": f"value_{i}"})

        # Test chunking uses configured batch size
        chunks = batch.chunk(max_size=storage.neo4j_batch_size)

        # Should have 2 chunks (1000 / 500)
        assert len(chunks) == 2
        assert len(chunks[0].nodes) == 500
        assert len(chunks[1].nodes) == 500


@pytest.mark.asyncio
async def test_batch_preserves_entity_relationships():
    """Ensure batching doesn't affect entity merge logic."""
    from nano_graphrag._extraction import _merge_nodes_for_batch, _merge_edges_for_batch

    # Mock storage
    mock_storage = AsyncMock()
    mock_storage.get_node = AsyncMock(return_value={
        "entity_type": "PERSON",
        "description": "Existing description",
        "source_id": "doc1"
    })
    mock_storage.get_edge = AsyncMock(return_value=None)
    mock_storage.has_node = AsyncMock(return_value=False)
    mock_storage.has_edge = AsyncMock(return_value=False)

    # Mock tokenizer
    mock_tokenizer = MagicMock()
    mock_tokenizer.encode = MagicMock(return_value=[1, 2, 3])
    mock_tokenizer.decode = MagicMock(return_value="decoded text")

    # Test merging nodes
    nodes_data = [
        {"entity_type": "PERSON", "description": "New description", "source_id": "doc2"},
        {"entity_type": "ORG", "description": "Another description", "source_id": "doc3"},
    ]

    merged_name, merged_data = await _merge_nodes_for_batch(
        "test_entity",
        nodes_data,
        mock_storage,
        {
            "entity_summary_to_max_tokens": 100,
            "cheap_model_func": AsyncMock(return_value="summarized"),
            "cheap_model_max_token_size": 4096,
        },
        mock_tokenizer
    )

    # Verify merge preserves all information
    assert merged_name == "test_entity"
    assert "ORG" in merged_data["entity_type"] or "PERSON" in merged_data["entity_type"]
    assert "doc1" in merged_data["source_id"]
    assert "doc2" in merged_data["source_id"]
    assert "doc3" in merged_data["source_id"]

    # Test merging edges
    batch = DocumentGraphBatch()
    edges_data = [
        {"description": "knows", "source_id": "doc1", "weight": 1.0},
        {"description": "works with", "source_id": "doc2", "weight": 1.0},
    ]

    await _merge_edges_for_batch(
        "entity1",
        "entity2",
        edges_data,
        mock_storage,
        {
            "entity_summary_to_max_tokens": 100,
            "cheap_model_func": AsyncMock(return_value="summarized"),
            "cheap_model_max_token_size": 4096,
        },
        mock_tokenizer,
        batch
    )

    # Verify edge was added to batch
    assert len(batch.edges) == 1
    edge = batch.edges[0]
    assert edge[0] == "entity1"
    assert edge[1] == "entity2"
    assert "doc1" in edge[2]["source_id"]
    assert "doc2" in edge[2]["source_id"]


if __name__ == "__main__":
    asyncio.run(test_batch_operations_reduce_transactions())
    asyncio.run(test_neo4j_batch_size_configuration())
    asyncio.run(test_batch_preserves_entity_relationships())
    print("All tests passed!")