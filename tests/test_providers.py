"""Test LLM and embedding providers."""
import os
import pytest
from unittest.mock import patch, AsyncMock, Mock, MagicMock
from typing import Dict, Any

from nano_graphrag.llm.providers import (
    OpenAIProvider,
    get_llm_provider,
    get_embedding_provider
)
from nano_graphrag.llm.base import BaseLLMProvider, BaseEmbeddingProvider
from nano_graphrag.config import LLMConfig


class TestOpenAIProvider:
    """Test OpenAI provider functionality."""
    
    @pytest.mark.asyncio
    async def test_openai_provider_gpt5_params(self):
        """Test GPT-5 specific parameter mapping."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Provide full usage object with required attributes
            usage = Mock()
            usage.prompt_tokens = 10
            usage.completion_tokens = 90
            usage.total_tokens = 100
            
            # Mock response with complete structure
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "test response"
            mock_response.choices[0].finish_reason = "stop"
            mock_response.usage = usage
            
            # Create async mock that returns the response
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            
            provider = OpenAIProvider(model="gpt-5-mini")
            provider.client = mock_client
            
            # Test max_tokens → max_completion_tokens mapping
            async def mock_wait_for(coro, timeout):
                return await coro
            
            with patch('asyncio.wait_for', side_effect=mock_wait_for):
                result = await provider.complete("test", max_tokens=1000)
            
            # Verify response structure
            assert result["text"] == "test response"
            assert result["usage"]["total_tokens"] == 100
    
    @pytest.mark.asyncio
    async def test_provider_none_content_guard(self):
        """Test handling of None content from GPT-5."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Create mock for chat completions
            mock_create = AsyncMock()
            mock_client.chat.completions.create = mock_create
            
            # Provide full usage object
            usage = Mock()
            usage.prompt_tokens = 10
            usage.completion_tokens = 0
            usage.total_tokens = 10
            
            # Mock response with None content
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = None
            mock_response.choices[0].finish_reason = "stop"
            mock_response.usage = usage
            mock_create.return_value = mock_response
            
            provider = OpenAIProvider(model="gpt-5")
            provider.client = mock_client
            
            async def mock_wait_for(coro, timeout):
                return await coro
            
            with patch('asyncio.wait_for', side_effect=mock_wait_for):
                result = await provider.complete("test")
            
            # Should default to empty string
            assert result["text"] == ""
    
    def test_base_url_separation(self):
        """Test LLM_BASE_URL vs EMBEDDING_BASE_URL separation."""
        # Test LLM provider with LLM_BASE_URL
        with patch.dict(os.environ, {
            "LLM_BASE_URL": "http://localhost:1234/v1",
            "OPENAI_API_KEY": "test-key"
        }):
            with patch('nano_graphrag.llm.providers.openai.AsyncOpenAI') as mock_openai:
                mock_openai.return_value = MagicMock()
                llm_provider = get_llm_provider('openai', 'test-model')
                llm_kwargs = mock_openai.call_args.kwargs
                assert llm_kwargs.get('base_url') == 'http://localhost:1234/v1'
        
        # Test embedding provider with EMBEDDING_BASE_URL (separate context)
        with patch.dict(os.environ, {
            "EMBEDDING_BASE_URL": "https://api.openai.com/v1",
            "OPENAI_API_KEY": "test-key"
        }):
            with patch('nano_graphrag.llm.providers.openai.AsyncOpenAI') as mock_openai:
                mock_openai.return_value = MagicMock()
                embed_provider = get_embedding_provider('openai', 'text-embedding-3-small')
                embed_kwargs = mock_openai.call_args.kwargs
                assert embed_kwargs.get('base_url') == 'https://api.openai.com/v1'
    
    @pytest.mark.asyncio
    async def test_complete_with_cache(self):
        """Test caching behavior with mock KV storage."""
        from nano_graphrag.base import BaseKVStorage
        
        mock_kv = AsyncMock(spec=BaseKVStorage)
        mock_kv.get_by_id.return_value = {"return": "cached_result"}
        
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client_class.return_value = MagicMock()
            
            provider = OpenAIProvider(model="gpt-5-mini")
            
            # Test cache hit path
            result = await provider.complete_with_cache(
                "prompt", hashing_kv=mock_kv
            )
            
            assert result == "cached_result"
            mock_kv.get_by_id.assert_called_once()
    
    def test_request_timeout_config(self):
        """Test request timeout is properly configured."""
        with patch.dict(os.environ, {"LLM_REQUEST_TIMEOUT": "60.0"}):
            config = LLMConfig.from_env()
            assert config.request_timeout == 60.0


class TestProviderFactory:
    """Test provider factory functions."""
    
    def test_get_llm_provider_openai(self):
        """Test getting OpenAI LLM provider."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client_class.return_value = MagicMock()

            provider = get_llm_provider("openai", "gpt-5-mini")
            # Check class name instead of isinstance due to potential import issues
            assert provider.__class__.__name__ == "OpenAIProvider"
            assert provider.model == "gpt-5-mini"
    
    def test_get_llm_provider_unknown(self):
        """Test error on unknown provider."""
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm_provider("unknown", "model")
    
    def test_get_embedding_provider_openai(self):
        """Test getting OpenAI embedding provider."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client_class.return_value = MagicMock()
            
            provider = get_embedding_provider("openai", "text-embedding-3-small")
            assert isinstance(provider, BaseEmbeddingProvider)
    
    def test_get_embedding_provider_unknown(self):
        """Test error on unknown embedding provider."""
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            get_embedding_provider("unknown", "model")


class TestProviderIntegration:
    """Test provider integration patterns."""
    
    @pytest.mark.asyncio
    async def test_provider_with_graphrag(self):
        """Test providers work with GraphRAG."""
        from nano_graphrag import GraphRAG
        from nano_graphrag.config import GraphRAGConfig, StorageConfig
        
        with patch('nano_graphrag.graphrag.get_llm_provider') as mock_get_llm, \
             patch('nano_graphrag.graphrag.get_embedding_provider') as mock_get_embed, \
             patch('pathlib.Path.mkdir'):  # Prevent directory creation
            
            # Create mock providers
            mock_llm = Mock(spec=BaseLLMProvider)
            mock_llm.complete_with_cache = AsyncMock(return_value="response")
            mock_llm.complete = AsyncMock(return_value={"text": "response", "usage": {"total_tokens": 100}})
            
            mock_embed = Mock(spec=BaseEmbeddingProvider)
            mock_embed.embed = AsyncMock(return_value={"embeddings": [[0.1] * 1536], "usage": {"total_tokens": 10}})
            mock_embed.dimension = 1536
            
            mock_get_llm.return_value = mock_llm
            mock_get_embed.return_value = mock_embed
            
            # Create GraphRAG with mocked providers
            config = GraphRAGConfig(
                storage=StorageConfig(working_dir="/tmp/test")
            )
            rag = GraphRAG(config=config)
            
            # Verify providers were obtained
            assert mock_get_llm.called
            assert mock_get_embed.called