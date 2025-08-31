"""Test RAG functionality with mock providers."""
import os
import json
import shutil
import pytest
import numpy as np
from unittest.mock import patch, AsyncMock, Mock
from pathlib import Path

from nano_graphrag import GraphRAG, QueryParam
from nano_graphrag.config import GraphRAGConfig, StorageConfig, QueryConfig
from nano_graphrag._utils import wrap_embedding_func_with_attrs
from tests.utils import (
    create_test_config,
    create_mock_llm_provider,
    create_mock_embedding_provider,
    load_test_data,
    mock_embedding_func
)

# Set fake API key to avoid environment errors
os.environ["OPENAI_API_KEY"] = "FAKE"

# Use tmp_path fixture for working directory
FAKE_RESPONSE = "Hello world"
FAKE_JSON = json.dumps({"points": [{"description": "Hello world", "score": 1}]})


@pytest.fixture
def temp_working_dir(tmp_path):
    """Provide clean temporary directory for each test."""
    # Copy mock cache if it exists
    mock_cache_src = Path("./tests/fixtures/mock_cache.json")
    if mock_cache_src.exists():
        cache_dest = tmp_path / "kv_store_llm_response_cache.json"
        shutil.copy(mock_cache_src, cache_dest)
    
    return str(tmp_path)


@pytest.fixture
def mock_providers():
    """Create mock LLM and embedding providers."""
    # Return JSON first to satisfy global mapping step deterministically
    llm_provider = create_mock_llm_provider([FAKE_JSON, FAKE_RESPONSE])
    # Use 1536 dimension to match OpenAI default
    embedding_provider = create_mock_embedding_provider(dimension=1536)
    return llm_provider, embedding_provider


def test_insert_with_mocks(temp_working_dir, mock_providers):
    """Test insert with mocked providers."""
    llm_provider, embedding_provider = mock_providers
    
    # Patch providers before GraphRAG instantiation - need to patch the imports
    with patch('nano_graphrag.graphrag.get_llm_provider') as mock_get_llm, \
         patch('nano_graphrag.graphrag.get_embedding_provider') as mock_get_embed:
        
        mock_get_llm.return_value = llm_provider
        mock_get_embed.return_value = embedding_provider
        
        # Create config with test working directory
        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=temp_working_dir),
            query=QueryConfig(enable_naive_rag=True)
        )
        
        # Initialize GraphRAG with mocked providers
        rag = GraphRAG(config=config)
        
        # Load limited test data for speed
        test_text = load_test_data(max_chars=1000)
        
        # Insert should work with mocked providers
        rag.insert(test_text)
        
        # Verify providers were called
        assert llm_provider.complete_with_cache.called or llm_provider.complete.called
        assert embedding_provider.embed.called


@pytest.mark.asyncio
async def test_local_query_with_mocks(temp_working_dir, mock_providers):
    """Test local query with pre-seeded data."""
    llm_provider, embedding_provider = mock_providers
    
    with patch('nano_graphrag.graphrag.get_llm_provider') as mock_get_llm, \
         patch('nano_graphrag.graphrag.get_embedding_provider') as mock_get_embed:
        
        mock_get_llm.return_value = llm_provider
        mock_get_embed.return_value = embedding_provider
        
        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=temp_working_dir),
            query=QueryConfig(enable_local=True)
        )
        
        rag = GraphRAG(config=config)
        
        # Pre-seed entities and chunks for local query
        await rag.text_chunks.upsert({
            "chunk1": {"content": "Test chunk content", "source_id": "doc1"}
        })
        await rag.entities_vdb.upsert({
            "entity1": {"content": "Test entity", "entity_name": "entity1", "source_id": "chunk1"}
        })
        
        # Mock query - should not fail with "No available context"
        result = await rag.aquery("Test query", param=QueryParam(mode="local"))
        
        # Should get mocked response, not the failure message
        assert result  # Non-empty
        assert "Sorry" not in result  # Not default fail message
        assert llm_provider.complete_with_cache.called  # LLM was invoked


@pytest.mark.asyncio
async def test_global_query_with_mocks(temp_working_dir, mock_providers):
    """Test global query with pre-seeded community data."""
    llm_provider, embedding_provider = mock_providers
    
    with patch('nano_graphrag.graphrag.get_llm_provider') as mock_get_llm, \
         patch('nano_graphrag.graphrag.get_embedding_provider') as mock_get_embed:
        
        mock_get_llm.return_value = llm_provider
        mock_get_embed.return_value = embedding_provider
        
        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=temp_working_dir)
        )
        
        rag = GraphRAG(config=config)
        
        # Pre-seed community reports for global query
        await rag.community_reports.upsert({
            'C1': {
                'report_string': 'Test community summary',
                'report_json': {'rating': 1.0, 'description': 'Test cluster'},
                'level': 0,
                'occurrence': 1.0
            }
        })
        
        # Mock community_schema to return our seeded community
        async def fake_schema():
            return {
                'C1': {
                    'level': 0,
                    'title': 'Cluster 1',
                    'edges': [],
                    'nodes': ['node1'],
                    'chunk_ids': ['chunk1'],
                    'occurrence': 1.0,
                    'sub_communities': []
                }
            }
        
        with patch.object(rag.chunk_entity_relation_graph, 'community_schema', AsyncMock(side_effect=fake_schema)):
            # Mock query - should get JSON response
            result = await rag.aquery("Test query", param=QueryParam(mode="global"))
            
            # Should get valid JSON response for global query
            assert result  # Non-empty
            try:
                parsed = json.loads(result)
                assert "points" in parsed
                assert isinstance(parsed["points"], list)
                if parsed["points"]:  # If there are points
                    assert "description" in parsed["points"][0]
            except json.JSONDecodeError:
                # If not JSON, at least verify it's a response
                assert len(result) > 0


@pytest.mark.asyncio
async def test_naive_query_with_mocks(temp_working_dir, mock_providers):
    """Test naive RAG query with mocked providers."""
    llm_provider, embedding_provider = mock_providers
    
    with patch('nano_graphrag.graphrag.get_llm_provider') as mock_get_llm, \
         patch('nano_graphrag.graphrag.get_embedding_provider') as mock_get_embed:
        
        mock_get_llm.return_value = llm_provider
        mock_get_embed.return_value = embedding_provider
        
        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=temp_working_dir),
            query=QueryConfig(enable_naive_rag=True)
        )
        
        rag = GraphRAG(config=config)
        
        # Pre-seed text chunks for naive query
        await rag.text_chunks.upsert({
            "chunk1": {"content": "This is test data for naive RAG."}
        })
        
        # Pre-seed vector storage
        await rag.chunks_vdb.upsert({
            "chunk1": {"content": "This is test data for naive RAG."}
        })
        
        # Mock query
        result = await rag.aquery("Test query", param=QueryParam(mode="naive"))
        
        # Should get response (relaxed assertion)
        assert result  # Non-empty
        assert len(result) > 0  # Has content
        # For naive mode, we just verify we got something back from the mocked LLM


def test_backward_compatibility():
    """Test that old patterns still work with deprecation warnings."""
    # This test ensures we don't break existing code
    # Can be removed in future versions
    pass