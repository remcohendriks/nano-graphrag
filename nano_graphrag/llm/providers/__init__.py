"""LLM Provider implementations."""

import os
from typing import Optional, Any, TYPE_CHECKING
from ..base import BaseLLMProvider, BaseEmbeddingProvider

# Type checking imports (no runtime cost)
if TYPE_CHECKING:
    from .openai import (
        OpenAIProvider,
        OpenAIEmbeddingProvider,
        gpt_4o_complete,
        gpt_4o_mini_complete,
        openai_embedding,
    )
    from .deepseek import (
        DeepSeekProvider,
        deepseek_model_if_cache,
        stream_deepseek_model_if_cache,
    )
    from .azure import (
        AzureOpenAIProvider,
        AzureOpenAIEmbeddingProvider,
        azure_gpt_4o_complete,
        azure_gpt_4o_mini_complete,
        azure_openai_embedding,
    )
    from .bedrock import (
        BedrockProvider,
        BedrockEmbeddingProvider,
        create_amazon_bedrock_complete_function,
        amazon_bedrock_embedding,
    )


def get_llm_provider(
    provider_type: str, 
    model: str,
    config: Optional[Any] = None
) -> BaseLLMProvider:
    """Factory function to get LLM provider instance.
    
    Args:
        provider_type: Type of provider (openai, azure, bedrock, deepseek)
        model: Model name
        config: Optional configuration object
        
    Returns:
        LLM provider instance
    """
    if provider_type == "openai":
        from .openai import OpenAIProvider
        # Use LLM_BASE_URL if set, otherwise fall back to OPENAI_BASE_URL
        base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        request_timeout = float(os.getenv("LLM_REQUEST_TIMEOUT", "30.0")) if config else 30.0
        if config and hasattr(config, 'request_timeout'):
            request_timeout = config.request_timeout
        return OpenAIProvider(model=model, base_url=base_url, request_timeout=request_timeout)
    elif provider_type == "azure":
        from .azure import AzureOpenAIProvider
        return AzureOpenAIProvider(model=model)
    elif provider_type == "bedrock":
        from .bedrock import BedrockProvider
        return BedrockProvider(model=model)
    elif provider_type == "deepseek":
        from .deepseek import DeepSeekProvider
        return DeepSeekProvider(model=model)
    else:
        raise ValueError(f"Unknown LLM provider type: {provider_type}")


def get_embedding_provider(
    provider_type: str,
    model: str,
    config: Optional[Any] = None
) -> BaseEmbeddingProvider:
    """Factory function to get embedding provider instance.
    
    Args:
        provider_type: Type of provider (openai, azure, bedrock)
        model: Model name
        config: Optional configuration object
        
    Returns:
        Embedding provider instance
    """
    if provider_type == "openai":
        from .openai import OpenAIEmbeddingProvider
        # Use EMBEDDING_BASE_URL if set, otherwise default to OpenAI's API
        # This prevents LMStudio's base URL from affecting embeddings
        base_url = os.getenv("EMBEDDING_BASE_URL")
        # If no embedding base URL is set, use None to default to OpenAI
        # Don't fall back to OPENAI_BASE_URL as that would redirect embeddings
        return OpenAIEmbeddingProvider(model=model, base_url=base_url)
    elif provider_type == "azure":
        from .azure import AzureOpenAIEmbeddingProvider
        return AzureOpenAIEmbeddingProvider(model=model)
    elif provider_type == "bedrock":
        from .bedrock import BedrockEmbeddingProvider
        return BedrockEmbeddingProvider(model=model)
    else:
        raise ValueError(f"Unknown embedding provider type: {provider_type}")


# Lazy attribute getter for backward compatibility
def __getattr__(name):
    """Lazy import provider classes and functions for backward compatibility."""
    # OpenAI exports
    if name == "OpenAIProvider":
        from .openai import OpenAIProvider
        return OpenAIProvider
    elif name == "OpenAIEmbeddingProvider":
        from .openai import OpenAIEmbeddingProvider
        return OpenAIEmbeddingProvider
    elif name == "gpt_4o_complete":
        from .openai import gpt_4o_complete
        return gpt_4o_complete
    elif name == "gpt_4o_mini_complete":
        from .openai import gpt_4o_mini_complete
        return gpt_4o_mini_complete
    elif name == "openai_embedding":
        from .openai import openai_embedding
        return openai_embedding
    
    # DeepSeek exports
    elif name == "DeepSeekProvider":
        from .deepseek import DeepSeekProvider
        return DeepSeekProvider
    elif name == "deepseek_model_if_cache":
        from .deepseek import deepseek_model_if_cache
        return deepseek_model_if_cache
    elif name == "stream_deepseek_model_if_cache":
        from .deepseek import stream_deepseek_model_if_cache
        return stream_deepseek_model_if_cache
    
    # Azure exports
    elif name == "AzureOpenAIProvider":
        from .azure import AzureOpenAIProvider
        return AzureOpenAIProvider
    elif name == "AzureOpenAIEmbeddingProvider":
        from .azure import AzureOpenAIEmbeddingProvider
        return AzureOpenAIEmbeddingProvider
    elif name == "azure_gpt_4o_complete":
        from .azure import azure_gpt_4o_complete
        return azure_gpt_4o_complete
    elif name == "azure_gpt_4o_mini_complete":
        from .azure import azure_gpt_4o_mini_complete
        return azure_gpt_4o_mini_complete
    elif name == "azure_openai_embedding":
        from .azure import azure_openai_embedding
        return azure_openai_embedding
    
    # Bedrock exports
    elif name == "BedrockProvider":
        from .bedrock import BedrockProvider
        return BedrockProvider
    elif name == "BedrockEmbeddingProvider":
        from .bedrock import BedrockEmbeddingProvider
        return BedrockEmbeddingProvider
    elif name == "create_amazon_bedrock_complete_function":
        from .bedrock import create_amazon_bedrock_complete_function
        return create_amazon_bedrock_complete_function
    elif name == "amazon_bedrock_embedding":
        from .bedrock import amazon_bedrock_embedding
        return amazon_bedrock_embedding
    
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    # Factory functions
    "get_llm_provider",
    "get_embedding_provider",
    # Providers
    "OpenAIProvider",
    "OpenAIEmbeddingProvider",
    "DeepSeekProvider",
    "AzureOpenAIProvider",
    "AzureOpenAIEmbeddingProvider",
    "BedrockProvider",
    "BedrockEmbeddingProvider",
    # Backward compatibility functions
    "gpt_4o_complete",
    "gpt_4o_mini_complete",
    "openai_embedding",
    "deepseek_model_if_cache",
    "stream_deepseek_model_if_cache",
    "azure_gpt_4o_complete",
    "azure_gpt_4o_mini_complete",
    "azure_openai_embedding",
    "create_amazon_bedrock_complete_function",
    "amazon_bedrock_embedding",
]