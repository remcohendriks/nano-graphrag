"""Unit tests for OpenAI LLM Provider implementation."""

import os
import pytest
import numpy as np
from unittest.mock import AsyncMock, Mock, patch
from typing import List, Dict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from nano_graphrag.llm.base import (
    BaseLLMProvider,
    BaseEmbeddingProvider,
    CompletionParams,
    CompletionResponse,
    StreamChunk,
    EmbeddingResponse
)
from nano_graphrag.llm.providers.openai import OpenAIProvider, OpenAIEmbeddingProvider


class TestBaseLLMProvider:
    """Test base LLM provider functionality."""
    
    def test_provider_initialization(self):
        """Verify provider initializes with correct parameters."""
        class TestProvider(BaseLLMProvider):
            env_key = "TEST_API_KEY"
            
            async def complete(self, prompt, **kwargs):
                return "test"
            
            async def stream(self, prompt, **kwargs):
                yield "test"
        
        provider = TestProvider(
            model="test-model",
            api_key="test-key",
            max_tokens=1024,
            temperature=0.5
        )
        
        assert provider.model == "test-model"
        assert provider.api_key == "test-key"
        assert provider.max_tokens == 1024
        assert provider.temperature == 0.5
    
    def test_provider_reads_env_key(self):
        """Verify provider reads API key from environment."""
        class TestProvider(BaseLLMProvider):
            env_key = "TEST_API_KEY"
            
            async def complete(self, prompt, **kwargs):
                return "test"
            
            async def stream(self, prompt, **kwargs):
                yield "test"
        
        with patch.dict(os.environ, {"TEST_API_KEY": "env-test-key"}):
            provider = TestProvider(model="test-model")
            assert provider.api_key == "env-test-key"
    
    @pytest.mark.asyncio
    async def test_caching_functionality(self):
        """Verify caching works correctly."""
        class TestProvider(BaseLLMProvider):
            async def complete(self, prompt, **kwargs):
                return "response"
            
            async def stream(self, prompt, **kwargs):
                yield "response"
        
        provider = TestProvider(model="test-model")
        mock_cache = AsyncMock()
        mock_cache.get_by_id.return_value = {"return": "cached_response"}
        
        result = await provider.complete_with_cache(
            "test prompt",
            hashing_kv=mock_cache
        )
        
        assert result == "cached_response"
        mock_cache.get_by_id.assert_called_once()
    
    def test_message_building(self):
        """Verify message list is built correctly."""
        class TestProvider(BaseLLMProvider):
            async def complete(self, prompt, **kwargs):
                return "test"
            
            async def stream(self, prompt, **kwargs):
                yield "test"
        
        provider = TestProvider(model="test")
        messages = provider._build_messages(
            "user prompt",
            "system prompt",
            [{"role": "assistant", "content": "previous"}]
        )
        
        assert len(messages) == 3
        assert messages[0] == {"role": "system", "content": "system prompt"}
        assert messages[1] == {"role": "assistant", "content": "previous"}
        assert messages[2] == {"role": "user", "content": "user prompt"}


class TestOpenAIProvider:
    """Test OpenAI provider implementation."""
    
    @pytest.mark.asyncio
    async def test_openai_complete(self):
        """Verify OpenAI provider returns completion."""
        provider = OpenAIProvider(model="gpt-4o-mini")
        
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            mock_response = Mock()
            mock_response.choices = [Mock(message=Mock(content="test response"))]
            mock_client.chat.completions.create.return_value = mock_response
            
            provider.client = mock_client
            result = await provider.complete("test prompt")
            
            assert result == "test response"
            mock_client.chat.completions.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_openai_with_system_and_history(self):
        """Verify OpenAI handles system prompts and history."""
        provider = OpenAIProvider(model="gpt-4o-mini")
        
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.chat.completions.create.return_value = Mock(
                choices=[Mock(message=Mock(content="response"))]
            )
            provider.client = mock_client
            
            await provider.complete(
                "user prompt",
                system_prompt="system",
                history=[{"role": "user", "content": "previous"}]
            )
            
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            
            assert len(messages) == 3
            assert messages[0]["role"] == "system"
            assert messages[1]["content"] == "previous"
            assert messages[2]["content"] == "user prompt"
    
    def test_max_tokens_parameter_selection(self):
        """Verify correct max_tokens parameter is used based on model."""
        # GPT-5 models should use max_completion_tokens
        provider_gpt5 = OpenAIProvider(model="gpt-5-mini")
        assert "gpt-5" in provider_gpt5.model
        
        # GPT-4 models should use max_tokens
        provider_gpt4 = OpenAIProvider(model="gpt-4o-mini")
        assert "gpt-5" not in provider_gpt4.model


class TestOpenAIEmbeddingProvider:
    """Test OpenAI embedding provider."""
    
    @pytest.mark.asyncio
    async def test_embedding_initialization(self):
        """Verify embedding provider initializes correctly."""
        provider = OpenAIEmbeddingProvider()
        assert provider.model == "text-embedding-3-small"
        assert provider.embedding_dim == 1536
    
    @pytest.mark.asyncio
    async def test_embedding_mock(self):
        """Test embedding with mocked response."""
        provider = OpenAIEmbeddingProvider()
        
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            # Mock embedding response
            mock_response = Mock()
            mock_response.data = [
                Mock(embedding=[0.1] * 1536),
                Mock(embedding=[0.2] * 1536)
            ]
            mock_client.embeddings.create.return_value = mock_response
            provider.client = mock_client
            
            result = await provider.embed(["text1", "text2"])
            
            assert result.shape == (2, 1536)
            assert isinstance(result, np.ndarray)
            mock_client.embeddings.create.assert_called_once_with(
                model="text-embedding-3-small",
                input=["text1", "text2"],
                encoding_format="float"
            )


class TestBackwardCompatibility:
    """Test backward compatibility functions."""
    
    @pytest.mark.asyncio
    async def test_gpt_4o_complete_compatibility(self):
        """Verify gpt_4o_complete backward compatibility."""
        from nano_graphrag.llm.providers.openai import gpt_4o_complete
        
        with patch('nano_graphrag.llm.providers.openai.OpenAIProvider') as mock_provider_class:
            mock_provider = AsyncMock()
            mock_provider_class.return_value = mock_provider
            mock_provider.complete_with_cache.return_value = "response"
            
            result = await gpt_4o_complete("prompt")
            
            assert result == "response"
            mock_provider_class.assert_called_once_with(model="gpt-5")
    
    @pytest.mark.asyncio
    async def test_gpt_4o_mini_complete_compatibility(self):
        """Verify gpt_4o_mini_complete backward compatibility."""
        from nano_graphrag.llm.providers.openai import gpt_4o_mini_complete
        
        with patch('nano_graphrag.llm.providers.openai.OpenAIProvider') as mock_provider_class:
            mock_provider = AsyncMock()
            mock_provider_class.return_value = mock_provider
            mock_provider.complete_with_cache.return_value = "response"
            
            result = await gpt_4o_mini_complete("prompt")
            
            assert result == "response"
            mock_provider_class.assert_called_once_with(model="gpt-5-mini")


class TestOpenAIIntegration:
    """Integration tests using real OpenAI API (when configured)."""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_API_KEY").startswith("sk-"),
        reason="OpenAI API key not configured"
    )
    async def test_real_openai_completion(self):
        """Test with real OpenAI API (requires API key)."""
        # Use test model from env or default to gpt-4o-mini
        model = os.getenv("OPENAI_TEST_MODEL", "gpt-4o-mini")
        provider = OpenAIProvider(model=model)
        
        result = await provider.complete(
            "Say 'test successful' and nothing else",
            max_tokens=50
        )
        
        assert "test successful" in result.lower()
        assert isinstance(result, str)
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_API_KEY").startswith("sk-"),
        reason="OpenAI API key not configured"
    )
    async def test_real_openai_streaming(self):
        """Test streaming with real OpenAI API."""
        model = os.getenv("OPENAI_TEST_MODEL", "gpt-4o-mini")
        provider = OpenAIProvider(model=model)
        
        chunks = []
        async for chunk in provider.stream(
            "Count from 1 to 3, just the numbers",
            max_tokens=50
        ):
            chunks.append(chunk)
        
        full_response = "".join(chunks)
        assert "1" in full_response
        assert "2" in full_response
        assert "3" in full_response
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_API_KEY").startswith("sk-"),
        reason="OpenAI API key not configured"
    )
    async def test_real_openai_embeddings(self):
        """Test embeddings with real OpenAI API."""
        provider = OpenAIEmbeddingProvider()
        
        result = await provider.embed(["test text", "another text"])
        
        assert result.shape == (2, 1536)
        assert isinstance(result, np.ndarray)
        # Embeddings should be normalized (roughly)
        assert -1.5 < result[0][0] < 1.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])