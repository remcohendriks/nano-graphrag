"""LLM Provider implementations."""

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

__all__ = [
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