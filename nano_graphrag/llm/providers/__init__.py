"""LLM Provider implementations."""

from typing import Optional, Any
from ..base import BaseLLMProvider, BaseEmbeddingProvider

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
        return OpenAIProvider(model=model)
    elif provider_type == "azure":
        return AzureOpenAIProvider(model=model)
    elif provider_type == "bedrock":
        return BedrockProvider(model=model)
    elif provider_type == "deepseek":
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
        return OpenAIEmbeddingProvider(model=model)
    elif provider_type == "azure":
        return AzureOpenAIEmbeddingProvider(model=model)
    elif provider_type == "bedrock":
        return BedrockEmbeddingProvider(model=model)
    else:
        raise ValueError(f"Unknown embedding provider type: {provider_type}")


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