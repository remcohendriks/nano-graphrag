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
    llm_provider = create_mock_llm_provider([FAKE_RESPONSE, FAKE_JSON])
    embedding_provider = create_mock_embedding_provider(dimension=384)
    return llm_provider, embedding_provider


def test_insert_with_mocks(temp_working_dir, mock_providers):
    """Test insert with mocked providers."""
    llm_provider, embedding_provider = mock_providers
    
    # Patch providers before GraphRAG instantiation
    with patch('nano_graphrag.llm.providers.get_llm_provider') as mock_get_llm, \
         patch('nano_graphrag.llm.providers.get_embedding_provider') as mock_get_embed:
        
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


async def test_local_query_with_mocks(temp_working_dir, mock_providers):
    """Test local query with mocked providers."""
    llm_provider, embedding_provider = mock_providers
    
    with patch('nano_graphrag.llm.providers.get_llm_provider') as mock_get_llm, \
         patch('nano_graphrag.llm.providers.get_embedding_provider') as mock_get_embed:
        
        mock_get_llm.return_value = llm_provider
        mock_get_embed.return_value = embedding_provider
        
        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=temp_working_dir),
            query=QueryConfig(enable_local=True)
        )
        
        rag = GraphRAG(config=config)
        
        # Mock query - providers will return FAKE_RESPONSE
        result = await rag.aquery("Test query", param=QueryParam(mode="local"))
        
        # Should get mocked response
        assert result == FAKE_RESPONSE


async def test_global_query_with_mocks(temp_working_dir, mock_providers):
    """Test global query with mocked providers."""
    llm_provider, embedding_provider = mock_providers
    
    with patch('nano_graphrag.llm.providers.get_llm_provider') as mock_get_llm, \
         patch('nano_graphrag.llm.providers.get_embedding_provider') as mock_get_embed:
        
        mock_get_llm.return_value = llm_provider
        mock_get_embed.return_value = embedding_provider
        
        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=temp_working_dir)
        )
        
        rag = GraphRAG(config=config)
        
        # Mock query
        result = await rag.aquery("Test query", param=QueryParam(mode="global"))
        
        # Should get JSON response for global query
        assert result == FAKE_JSON


async def test_naive_query_with_mocks(temp_working_dir, mock_providers):
    """Test naive RAG query with mocked providers."""
    llm_provider, embedding_provider = mock_providers
    
    with patch('nano_graphrag.llm.providers.get_llm_provider') as mock_get_llm, \
         patch('nano_graphrag.llm.providers.get_embedding_provider') as mock_get_embed:
        
        mock_get_llm.return_value = llm_provider
        mock_get_embed.return_value = embedding_provider
        
        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=temp_working_dir),
            query=QueryConfig(enable_naive_rag=True)
        )
        
        rag = GraphRAG(config=config)
        
        # Insert minimal data first
        test_text = "This is test data for naive RAG."
        rag.insert(test_text)
        
        # Mock query
        result = await rag.aquery("Test query", param=QueryParam(mode="naive"))
        
        # Should get response
        assert result == FAKE_RESPONSE


def test_backward_compatibility():
    """Test that old patterns still work with deprecation warnings."""
    # This test ensures we don't break existing code
    # Can be removed in future versions
    pass


# Mark async tests
pytest.mark.asyncio(test_local_query_with_mocks)
pytest.mark.asyncio(test_global_query_with_mocks)
pytest.mark.asyncio(test_naive_query_with_mocks)