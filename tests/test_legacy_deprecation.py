"""Tests for legacy function deprecation warnings."""

import pytest
import warnings
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from nano_graphrag._llm import (
    get_openai_async_client_instance,
    get_azure_openai_async_client_instance,
    get_amazon_bedrock_async_client_instance,
)


class TestGlobalClientDeprecation:
    """Test deprecation warnings for global client functions."""
    
    def test_openai_client_deprecated(self):
        """Test that get_openai_async_client_instance shows deprecation warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # Mock the AsyncOpenAI client to avoid needing API key
            with patch('openai.AsyncOpenAI') as mock_client:
                mock_client.return_value = MagicMock()
                get_openai_async_client_instance()
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()
            assert "v0.2.0" in str(w[0].message)
            assert "OpenAIProvider" in str(w[0].message)
    
    def test_azure_client_deprecated(self):
        """Test that get_azure_openai_async_client_instance shows deprecation warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # Mock the AsyncAzureOpenAI client
            with patch('openai.AsyncAzureOpenAI') as mock_client:
                mock_client.return_value = MagicMock()
                get_azure_openai_async_client_instance()
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()
            assert "v0.2.0" in str(w[0].message)
            assert "AzureOpenAIProvider" in str(w[0].message)
    
    def test_bedrock_client_deprecated(self):
        """Test that get_amazon_bedrock_async_client_instance shows deprecation warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # Mock aioboto3
            with patch('aioboto3.Session') as mock_session:
                mock_session.return_value = MagicMock()
                get_amazon_bedrock_async_client_instance()
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()
            assert "v0.2.0" in str(w[0].message)
            assert "BedrockProvider" in str(w[0].message)
    
    def test_warning_shown_once_per_session(self):
        """Test that deprecation warning is shown only once per session."""
        # Clear the warning tracking set first
        from nano_graphrag._utils import _deprecation_warnings_shown
        _deprecation_warnings_shown.clear()
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            with patch('openai.AsyncOpenAI') as mock_client:
                mock_client.return_value = MagicMock()
                
                # First call should show warning
                get_openai_async_client_instance()
                assert len(w) == 1
                
                # Second call should not show warning
                get_openai_async_client_instance()
                assert len(w) == 1  # Still only one warning


class TestLegacyFunctionDeprecation:
    """Test deprecation warnings for legacy LLM functions."""
    
    @pytest.mark.asyncio
    async def test_gpt_4o_complete_deprecated(self):
        """Test that gpt_4o_complete shows deprecation warning."""
        # Clear warning tracking
        from nano_graphrag._utils import _deprecation_warnings_shown
        _deprecation_warnings_shown.clear()
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # Mock the provider to avoid API calls
            with patch('nano_graphrag.llm.providers.openai.OpenAIProvider') as mock_provider:
                mock_instance = MagicMock()
                mock_instance.complete_with_cache = AsyncMock(return_value="test response")
                mock_provider.return_value = mock_instance
                
                from nano_graphrag.llm.providers.openai import gpt_4o_complete
                await gpt_4o_complete("test prompt")
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "gpt_4o_complete" in str(w[0].message)
            assert "deprecated" in str(w[0].message).lower()
            assert "v0.2.0" in str(w[0].message)
            assert "OpenAIProvider" in str(w[0].message)
    
    @pytest.mark.asyncio
    async def test_openai_embedding_deprecated(self):
        """Test that openai_embedding shows deprecation warning."""
        # Clear warning tracking
        from nano_graphrag._utils import _deprecation_warnings_shown
        _deprecation_warnings_shown.clear()
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # Mock the provider
            with patch('nano_graphrag.llm.providers.openai.OpenAIEmbeddingProvider') as mock_provider:
                mock_instance = MagicMock()
                mock_instance.embed = AsyncMock(return_value={"embeddings": [[0.1, 0.2]]})
                mock_provider.return_value = mock_instance
                
                from nano_graphrag.llm.providers.openai import openai_embedding
                await openai_embedding(["test text"])
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "openai_embedding" in str(w[0].message)
            assert "deprecated" in str(w[0].message).lower()
            assert "OpenAIEmbeddingProvider" in str(w[0].message)
    
    @pytest.mark.asyncio
    async def test_azure_functions_deprecated(self):
        """Test that Azure functions show deprecation warnings."""
        # Clear warning tracking
        from nano_graphrag._utils import _deprecation_warnings_shown
        _deprecation_warnings_shown.clear()
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # Mock Azure provider
            with patch('nano_graphrag.llm.providers.azure.AzureOpenAIProvider') as mock_provider:
                mock_instance = MagicMock()
                mock_instance.complete_with_cache = AsyncMock(return_value="test response")
                mock_provider.return_value = mock_instance
                
                from nano_graphrag.llm.providers.azure import azure_gpt_4o_complete
                await azure_gpt_4o_complete("test prompt")
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "azure_gpt_4o_complete" in str(w[0].message)
            assert "AzureOpenAIProvider" in str(w[0].message)
    
    def test_bedrock_factory_deprecated(self):
        """Test that create_amazon_bedrock_complete_function shows deprecation warning."""
        # Clear warning tracking
        from nano_graphrag._utils import _deprecation_warnings_shown
        _deprecation_warnings_shown.clear()
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            from nano_graphrag.llm.providers.bedrock import create_amazon_bedrock_complete_function
            
            # Creating the function should show the warning
            func = create_amazon_bedrock_complete_function("test-model")
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "create_amazon_bedrock_complete_function" in str(w[0].message)
            assert "BedrockProvider" in str(w[0].message)


class TestBackwardCompatibility:
    """Test that deprecated functions still work correctly."""
    
    @pytest.mark.asyncio
    async def test_legacy_functions_still_work(self):
        """Test that legacy functions continue to work despite deprecation."""
        with warnings.catch_warnings():
            # Suppress warnings for this test
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            
            # Mock the provider
            with patch('nano_graphrag.llm.providers.openai.OpenAIProvider') as mock_provider:
                mock_instance = MagicMock()
                mock_instance.complete_with_cache = AsyncMock(return_value="mocked response")
                mock_provider.return_value = mock_instance
                
                from nano_graphrag.llm.providers.openai import gpt_4o_complete
                result = await gpt_4o_complete("test prompt")
                
                assert result == "mocked response"
                mock_instance.complete_with_cache.assert_called_once()
    
    def test_imports_still_work(self):
        """Test that all legacy imports still work."""
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            
            # These imports should all work without errors
            from nano_graphrag._llm import (
                gpt_4o_complete,
                gpt_4o_mini_complete,
                openai_embedding,
                azure_gpt_4o_complete,
                azure_gpt_4o_mini_complete,
                azure_openai_embedding,
                create_amazon_bedrock_complete_function,
                amazon_bedrock_embedding,
            )
            
            # Verify they are callable
            assert callable(gpt_4o_complete)
            assert callable(openai_embedding)
            assert callable(azure_gpt_4o_complete)
            assert callable(create_amazon_bedrock_complete_function)