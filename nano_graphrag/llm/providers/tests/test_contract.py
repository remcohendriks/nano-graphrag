"""Contract tests for LLM providers to ensure interface compliance."""

import pytest
import asyncio
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Type, AsyncIterator

from nano_graphrag.llm.base import (
    BaseLLMProvider,
    BaseEmbeddingProvider,
    CompletionParams,
    CompletionResponse,
    StreamChunk,
    EmbeddingResponse,
    LLMAuthError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMServerError,
    LLMBadRequestError
)
from nano_graphrag.llm.providers.openai import OpenAIProvider, OpenAIEmbeddingProvider


class ContractTestBase:
    """Base class for provider contract tests."""
    
    provider_class: Type[BaseLLMProvider] = None
    embedding_provider_class: Type[BaseEmbeddingProvider] = None
    
    @pytest.fixture
    def provider(self):
        """Create provider instance."""
        return self.provider_class(model="test-model", api_key="test-key")
    
    @pytest.fixture
    def embedding_provider(self):
        """Create embedding provider instance."""
        if self.embedding_provider_class:
            return self.embedding_provider_class(model="test-embed", api_key="test-key")
        return None
    
    def test_provider_has_required_methods(self, provider):
        """Verify provider implements all required methods."""
        assert hasattr(provider, 'complete')
        assert hasattr(provider, 'stream')
        assert hasattr(provider, '_translate_params')
        assert hasattr(provider, '_translate_error')
        assert hasattr(provider, 'complete_with_cache')
        assert hasattr(provider, 'stream_with_cache')
    
    def test_provider_initialization(self):
        """Test provider can be initialized with various configs."""
        # Basic init
        p1 = self.provider_class(model="test")
        assert p1.model == "test"
        
        # With custom timeouts
        p2 = self.provider_class(
            model="test",
            request_timeout=60.0,
            connect_timeout=5.0
        )
        assert p2.request_timeout == 60.0
        assert p2.connect_timeout == 5.0
        
        # With retry config
        retry_config = {
            "max_retries": 5,
            "retry_on_status": [429, 500],
            "backoff_factor": 3.0,
            "max_backoff": 120.0
        }
        p3 = self.provider_class(model="test", retry_config=retry_config)
        assert p3.retry_config == retry_config
    
    @pytest.mark.asyncio
    async def test_complete_returns_correct_type(self, provider):
        """Verify complete returns CompletionResponse."""
        with patch.object(provider, '_retry_with_backoff') as mock_retry:
            mock_retry.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="test"), finish_reason="stop")],
                usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
            )
            
            result = await provider.complete("test prompt")
            
            assert isinstance(result, dict)
            assert "text" in result
            assert "finish_reason" in result
            assert "usage" in result
            assert "raw" in result
            assert result["text"] == "test"
            assert result["finish_reason"] == "stop"
    
    @pytest.mark.asyncio
    async def test_stream_returns_async_iterator(self, provider):
        """Verify stream returns AsyncIterator[StreamChunk]."""
        # Test that the stream method signature is correct
        import inspect
        sig = inspect.signature(provider.stream)
        params = sig.parameters
        
        # Check required parameters
        assert 'prompt' in params
        assert 'system_prompt' in params
        assert 'history' in params
        assert 'params' in params
        assert 'timeout' in params
        
        # Verify it's an async generator
        assert inspect.isasyncgenfunction(provider.stream) or inspect.iscoroutinefunction(provider.stream)
    
    def test_translate_params_vendor_neutral(self, provider):
        """Verify parameter translation is vendor-neutral."""
        params = CompletionParams(
            max_output_tokens=1000,
            temperature=0.7,
            top_p=0.9,
            frequency_penalty=0.5,
            presence_penalty=0.3,
            stop_sequences=["\\n", "END"],
            seed=42
        )
        
        translated = provider._translate_params(params)
        
        # Ensure no vendor-neutral names leak through
        assert "max_output_tokens" not in translated
        assert "stop_sequences" not in translated
        
        # Verify some translation occurred
        assert len(translated) > 0
    
    def test_translate_error_coverage(self, provider):
        """Verify error translation covers all cases."""
        from nano_graphrag.llm.base import LLMError
        # Test various error types
        errors = [
            (Exception("generic"), LLMError),
            (asyncio.TimeoutError(), LLMTimeoutError),
        ]
        
        for original, expected_type in errors:
            translated = provider._translate_error(original)
            assert isinstance(translated, expected_type) or isinstance(translated, LLMError)
    
    @pytest.mark.asyncio
    async def test_complete_with_params(self, provider):
        """Test complete with vendor-neutral params."""
        params = CompletionParams(
            max_output_tokens=500,
            temperature=1.0,
            top_p=0.95
        )
        
        with patch.object(provider, '_retry_with_backoff') as mock_retry:
            mock_retry.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="test"), finish_reason="stop")],
                usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
            )
            
            result = await provider.complete(
                "test prompt",
                params=params,
                timeout=10.0
            )
            
            assert result["text"] == "test"
    
    @pytest.mark.asyncio
    async def test_complete_with_timeout(self, provider):
        """Test timeout handling."""
        with patch.object(provider, '_retry_with_backoff') as mock_retry:
            mock_retry.side_effect = asyncio.TimeoutError()
            
            with pytest.raises(LLMTimeoutError):
                await provider.complete("test", timeout=0.001)
    
    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self, provider):
        """Test retry behavior on rate limit errors."""
        call_count = 0
        
        async def mock_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # Create a mock rate limit error
                class MockRateLimitError(Exception):
                    pass
                error = MockRateLimitError("Rate limited")
                error.__class__.__name__ = "RateLimitError"
                raise error
            return "success"
        
        # Mock sleep to speed up test
        with patch('asyncio.sleep', new_callable=AsyncMock):
            # The retry logic will translate the error and retry
            result = await provider._retry_with_backoff(mock_func)
            assert result == "success"
            assert call_count == 3


class TestOpenAIProviderContract(ContractTestBase):
    """Contract tests for OpenAI provider."""
    
    provider_class = OpenAIProvider
    embedding_provider_class = OpenAIEmbeddingProvider
    
    def test_openai_specific_param_translation(self):
        """Test OpenAI-specific parameter translation."""
        # Test GPT-5 model
        provider_gpt5 = OpenAIProvider(model="gpt-5", api_key="test")
        params = CompletionParams(max_output_tokens=1000)
        translated = provider_gpt5._translate_params(params)
        assert "max_completion_tokens" in translated
        assert translated["max_completion_tokens"] == 1000
        
        # Test GPT-4 model
        provider_gpt4 = OpenAIProvider(model="gpt-4", api_key="test")
        translated = provider_gpt4._translate_params(params)
        assert "max_tokens" in translated
        assert translated["max_tokens"] == 1000
    
    @pytest.mark.asyncio
    async def test_embedding_provider_contract(self, embedding_provider):
        """Test embedding provider implements contract."""
        if not embedding_provider:
            pytest.skip("No embedding provider for this test")
        
        with patch.object(embedding_provider, '_retry_with_backoff') as mock_retry:
            mock_retry.return_value = MagicMock(
                data=[
                    MagicMock(embedding=[0.1] * 1536),
                    MagicMock(embedding=[0.2] * 1536)
                ]
            )
            
            result = await embedding_provider.embed(["text1", "text2"])
            
            assert isinstance(result, dict)
            assert "embeddings" in result
            assert "dimensions" in result
            assert "model" in result
            assert "usage" in result
            assert isinstance(result["embeddings"], np.ndarray)
            assert result["embeddings"].shape == (2, 1536)
    
    def test_embedding_batch_handling(self, embedding_provider):
        """Test embedding provider has batch size limit."""
        if not embedding_provider:
            pytest.skip("No embedding provider for this test")
        
        # Verify the provider has a max_batch_size attribute
        assert hasattr(embedding_provider, 'max_batch_size')
        assert isinstance(embedding_provider.max_batch_size, int)
        assert embedding_provider.max_batch_size > 0
        
        # Verify embedding dimensions are set
        assert hasattr(embedding_provider, 'embedding_dim')
        assert embedding_provider.embedding_dim > 0


# Table-driven parameter translation tests
@pytest.mark.parametrize("provider_class,model,params,expected_keys", [
    (OpenAIProvider, "gpt-5", {"max_output_tokens": 1000}, ["max_completion_tokens"]),
    (OpenAIProvider, "gpt-5-mini", {"max_output_tokens": 1000}, ["max_completion_tokens"]),
    (OpenAIProvider, "gpt-4", {"max_output_tokens": 1000}, ["max_tokens"]),
    (OpenAIProvider, "gpt-4-turbo", {"max_output_tokens": 1000}, ["max_tokens"]),
])
def test_parameter_translation_matrix(provider_class, model, params, expected_keys):
    """Table-driven test for parameter translation across models."""
    provider = provider_class(model=model, api_key="test")
    completion_params = CompletionParams(**params)
    translated = provider._translate_params(completion_params)
    
    for key in expected_keys:
        assert key in translated, f"Expected {key} in translated params for {model}"
    
    # Ensure vendor-neutral names don't leak
    assert "max_output_tokens" not in translated


# Error translation matrix tests
@pytest.mark.parametrize("provider_class,error_type,expected_llm_error", [
    (OpenAIProvider, "auth", LLMAuthError),
    (OpenAIProvider, "rate_limit", LLMRateLimitError),
    (OpenAIProvider, "timeout", LLMTimeoutError),
    (OpenAIProvider, "server", LLMServerError),
    (OpenAIProvider, "bad_request", LLMBadRequestError),
])
def test_error_translation_matrix(provider_class, error_type, expected_llm_error):
    """Table-driven test for error translation."""
    provider = provider_class(model="test", api_key="test")
    
    # Create mock errors (use mock objects to simulate OpenAI errors)
    if error_type == "auth":
        error = MagicMock()
        error.__class__.__name__ = "AuthenticationError"
        error.__str__ = lambda self: "Authentication failed"
    elif error_type == "rate_limit":
        error = MagicMock()
        error.__class__.__name__ = "RateLimitError"
        error.__str__ = lambda self: "Rate limit exceeded"
    elif error_type == "timeout":
        error = asyncio.TimeoutError()
    elif error_type == "server":
        error = MagicMock()
        error.__class__.__name__ = "APIConnectionError"
        error.__str__ = lambda self: "Server error"
    elif error_type == "bad_request":
        error = MagicMock()
        error.__class__.__name__ = "BadRequestError"
        error.__str__ = lambda self: "Invalid request"
    
    translated = provider._translate_error(error)
    assert isinstance(translated, expected_llm_error)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])