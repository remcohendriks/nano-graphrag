"""Test utilities for nano-graphrag tests."""
import os
import numpy as np
from unittest.mock import AsyncMock, Mock
from typing import Optional, List, Dict, Any

from nano_graphrag.config import GraphRAGConfig, StorageConfig, LLMConfig, EmbeddingConfig
from nano_graphrag.llm.base import BaseLLMProvider, BaseEmbeddingProvider
from nano_graphrag._utils import wrap_embedding_func_with_attrs


def create_test_config(**overrides) -> GraphRAGConfig:
    """Create test config with sensible defaults."""
    config_kwargs = {}
    
    # Apply storage config overrides
    if "working_dir" in overrides:
        config_kwargs["storage"] = StorageConfig(working_dir=overrides.pop("working_dir"))
    
    # Apply other config overrides
    for key, value in overrides.items():
        if key == "enable_naive_rag":
            # This goes in query config
            from nano_graphrag.config import QueryConfig
            config_kwargs["query"] = QueryConfig(enable_naive_rag=value)
        # Add more mappings as needed
    
    return GraphRAGConfig(**config_kwargs)


def create_mock_llm_provider(responses: Optional[List[str]] = None) -> Mock:
    """Create mock LLM provider with standard responses."""
    provider = Mock(spec=BaseLLMProvider)
    
    if responses is None:
        responses = ["test response"]
    
    # Create async mock for complete_with_cache
    async def mock_complete(prompt, system_prompt=None, history=None, hashing_kv=None, **kwargs):
        # Return next response or last one
        if hasattr(mock_complete, "_call_count"):
            mock_complete._call_count += 1
        else:
            mock_complete._call_count = 0
        
        idx = min(mock_complete._call_count, len(responses) - 1)
        return responses[idx]
    
    provider.complete_with_cache = AsyncMock(side_effect=mock_complete)
    provider.complete = AsyncMock(side_effect=mock_complete)
    
    return provider


def create_mock_embedding_provider(dimension: int = 1536) -> Mock:
    """Create mock embedding provider."""
    provider = Mock(spec=BaseEmbeddingProvider)
    
    async def mock_embed(texts: List[str]) -> Dict[str, Any]:
        embeddings = np.random.rand(len(texts), dimension)
        return {
            "embeddings": embeddings,
            "usage": {"total_tokens": len(texts) * 10}
        }
    
    provider.embed = AsyncMock(side_effect=mock_embed)
    provider.dimension = dimension
    
    return provider


@wrap_embedding_func_with_attrs(embedding_dim=384, max_token_size=8192)
async def mock_embedding_func(texts: List[str]) -> np.ndarray:
    """Mock embedding function for tests."""
    return np.random.rand(len(texts), 384)


def load_test_data(max_chars: int = 10000) -> str:
    """Load limited test data for fast tests."""
    test_file = os.path.join(os.path.dirname(__file__), "mock_data.txt")
    with open(test_file, encoding="utf-8-sig") as f:
        return f.read()[:max_chars]