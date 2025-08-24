"""
Backward compatibility layer for LLM functions.
All implementations have been moved to nano_graphrag.llm.providers
"""

# Import all backward compatibility functions from new providers
from .llm.providers import (
    # OpenAI
    gpt_4o_complete,
    gpt_4o_mini_complete,
    openai_embedding,
    # Azure
    azure_gpt_4o_complete,
    azure_gpt_4o_mini_complete,
    azure_openai_embedding,
    # Bedrock
    create_amazon_bedrock_complete_function,
    amazon_bedrock_embedding,
)

# Re-export for backward compatibility
__all__ = [
    "gpt_4o_complete",
    "gpt_4o_mini_complete",
    "openai_embedding",
    "azure_gpt_4o_complete",
    "azure_gpt_4o_mini_complete",
    "azure_openai_embedding",
    "create_amazon_bedrock_complete_function",
    "amazon_bedrock_embedding",
]

# Legacy global client instances (deprecated but kept for compatibility)
global_openai_async_client = None
global_azure_openai_async_client = None
global_amazon_bedrock_async_client = None

def get_openai_async_client_instance():
    """Deprecated: Use OpenAIProvider instead."""
    from openai import AsyncOpenAI
    global global_openai_async_client
    if global_openai_async_client is None:
        global_openai_async_client = AsyncOpenAI()
    return global_openai_async_client

def get_azure_openai_async_client_instance():
    """Deprecated: Use AzureOpenAIProvider instead."""
    from openai import AsyncAzureOpenAI
    global global_azure_openai_async_client
    if global_azure_openai_async_client is None:
        global_azure_openai_async_client = AsyncAzureOpenAI()
    return global_azure_openai_async_client

def get_amazon_bedrock_async_client_instance():
    """Deprecated: Use BedrockProvider instead."""
    import aioboto3
    global global_amazon_bedrock_async_client
    if global_amazon_bedrock_async_client is None:
        global_amazon_bedrock_async_client = aioboto3.Session()
    return global_amazon_bedrock_async_client

# Legacy function aliases for full backward compatibility
openai_complete_if_cache = gpt_4o_complete  # Alias
azure_openai_complete_if_cache = azure_gpt_4o_complete  # Alias