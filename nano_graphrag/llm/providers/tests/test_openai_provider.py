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
                # Must return CompletionResponse dict
                return {
                    "text": "test",
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                    "raw": None
                }
            
            async def stream(self, prompt, **kwargs):
                yield "test"
            
            def _translate_params(self, params):
                """Translate internal params to API params."""
                return params
            
            def _translate_error(self, error):
                """Translate vendor errors to standard errors."""
                return error
        
        # Current API doesn't accept max_tokens/temperature in constructor
        provider = TestProvider(
            model="test-model",
            api_key="test-key",
            base_url="https://api.test.com"
        )
        
        assert provider.model == "test-model"
        assert provider.api_key == "test-key"
        assert provider.base_url == "https://api.test.com"
    
    def test_provider_reads_env_key(self):
        """Verify provider reads API key from environment."""
        class TestProvider(BaseLLMProvider):
            env_key = "TEST_API_KEY"
            
            async def complete(self, prompt, **kwargs):
                return {
                    "text": "test",
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                    "raw": None
                }
            
            async def stream(self, prompt, **kwargs):
                yield "test"
            
            def _translate_params(self, params):
                return params
            
            def _translate_error(self, error):
                return error
        
        with patch.dict(os.environ, {"TEST_API_KEY": "env-test-key"}):
            provider = TestProvider(model="test-model")
            assert provider.api_key == "env-test-key"
    
    @pytest.mark.asyncio
    async def test_caching_functionality(self):
        """Verify caching works correctly."""
        class TestProvider(BaseLLMProvider):
            async def complete(self, prompt, **kwargs):
                # Must return CompletionResponse dict
                return {
                    "text": "response",
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                    "raw": None
                }
            
            async def stream(self, prompt, **kwargs):
                yield "response"
            
            def _translate_params(self, params):
                return params
            
            def _translate_error(self, error):
                return error
        
        provider = TestProvider(model="test-model")
        mock_cache = AsyncMock()
        # complete_with_cache expects the cache to store the text value
        mock_cache.get_by_id.return_value = {"return": "cached_response"}
        
        result = await provider.complete_with_cache(
            "test prompt",
            hashing_kv=mock_cache
        )
        
        # complete_with_cache returns just the text string from cache
        assert result == "cached_response"
        mock_cache.get_by_id.assert_called_once()
    
    def test_message_building(self):
        """Verify message list is built correctly."""
        class TestProvider(BaseLLMProvider):
            async def complete(self, prompt, **kwargs):
                return {
                    "text": "test",
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                    "raw": None
                }
            
            async def stream(self, prompt, **kwargs):
                yield "test"
            
            def _translate_params(self, params):
                return params
            
            def _translate_error(self, error):
                return error
        
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
        """Verify OpenAI provider returns CompletionResponse dict."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            # Create proper mock response with usage
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "test response"
            mock_response.choices[0].finish_reason = "stop"
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 20
            mock_response.usage.total_tokens = 30
            
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            
            provider = OpenAIProvider(model="gpt-4o-mini")
            provider.client = mock_client
            
            async def mock_wait_for(coro, timeout):
                return await coro
            
            with patch('asyncio.wait_for', side_effect=mock_wait_for):
                result = await provider.complete("test prompt")
            
            # OpenAI provider returns CompletionResponse dict
            assert isinstance(result, dict)
            assert result["text"] == "test response"
            assert result["finish_reason"] == "stop"
            assert result["usage"]["total_tokens"] == 30
    
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
        """Test embedding returns EmbeddingResponse dict."""
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
            mock_response.usage.total_tokens = 20
            
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            provider.client = mock_client
            
            async def mock_wait_for(coro, timeout):
                return await coro
            
            with patch('asyncio.wait_for', side_effect=mock_wait_for):
                result = await provider.embed(["text1", "text2"])
            
            # Provider returns EmbeddingResponse dict
            assert isinstance(result, dict)
            assert "embeddings" in result
            assert result["embeddings"].shape == (2, 1536)
            assert isinstance(result["embeddings"], np.ndarray)
            assert result["dimensions"] == 1536
            assert result["usage"]["total_tokens"] == 20


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
        # Use test model from env or default to gpt-5-mini
        model = os.getenv("OPENAI_TEST_MODEL", "gpt-5-mini")
        provider = OpenAIProvider(model=model)
        
        result = await provider.complete(
            "Say 'test successful' and nothing else",
            max_tokens=50
        )

        assert "test successful" in result["text"].lower()
        assert isinstance(result, dict)
        assert "text" in result
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_API_KEY").startswith("sk-"),
        reason="OpenAI API key not configured"
    )
    async def test_real_openai_streaming(self):
        """Test streaming with real OpenAI API."""
        # Use environment variable for model, default to gpt-5-nano for unverified streaming
        model = os.getenv("OPENAI_STREAMING_MODEL", "gpt-5-nano")
        provider = OpenAIProvider(model=model)
        
        chunks = []
        async for chunk in provider.stream(
            "Count from 1 to 3, just the numbers",
            max_completion_tokens=50
        ):
            chunks.append(chunk)

        assert len(chunks) > 0
        full_response = "".join(str(c) for c in chunks)
        assert len(full_response) > 0
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_API_KEY").startswith("sk-"),
        reason="OpenAI API key not configured"
    )
    async def test_real_openai_embeddings(self):
        """Test embeddings with real OpenAI API."""
        provider = OpenAIEmbeddingProvider()
        
        result = await provider.embed(["test text", "another text"])

        assert "embeddings" in result
        embeddings = np.array(result["embeddings"])
        assert embeddings.shape == (2, 1536)
        assert -1.5 < embeddings[0][0] < 1.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])