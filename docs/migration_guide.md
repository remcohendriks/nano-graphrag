# Migration Guide: Legacy LLM Functions

## Overview

The function-based LLM interface in nano-graphrag is deprecated in favor of the provider-based interface. This guide helps you migrate from the old patterns to the new, more maintainable approach.

## Deprecation Timeline

- **v0.0.8.2** (current): Deprecation warnings added
- **v0.2.0**: Legacy functions will be removed
- **Migration period**: 3-6 months

## Migration Examples

### OpenAI Functions

#### Old way (deprecated)
```python
from nano_graphrag._llm import gpt_4o_complete, gpt_4o_mini_complete, openai_embedding

# Using legacy functions
response = await gpt_4o_complete(
    prompt="Hello",
    system_prompt="You are helpful"
)

response_mini = await gpt_4o_mini_complete(
    prompt="Hello",
    system_prompt="You are helpful"
)

embeddings = await openai_embedding(["text1", "text2"])
```

#### New way (recommended)
```python
from nano_graphrag.llm.providers import OpenAIProvider, OpenAIEmbeddingProvider

# Create provider instances
llm = OpenAIProvider(model="gpt-5")
llm_mini = OpenAIProvider(model="gpt-5-mini")
embedder = OpenAIEmbeddingProvider()

# Use provider methods
response = await llm.complete(
    prompt="Hello",
    system_prompt="You are helpful"
)

response_mini = await llm_mini.complete(
    prompt="Hello",
    system_prompt="You are helpful"
)

embedding_response = await embedder.embed(["text1", "text2"])
embeddings = embedding_response["embeddings"]
```

### Azure OpenAI Functions

#### Old way (deprecated)
```python
from nano_graphrag._llm import azure_gpt_4o_complete, azure_openai_embedding

response = await azure_gpt_4o_complete(
    prompt="Hello",
    system_prompt="You are helpful"
)

embeddings = await azure_openai_embedding(["text1", "text2"])
```

#### New way (recommended)
```python
from nano_graphrag.llm.providers import AzureOpenAIProvider, AzureOpenAIEmbeddingProvider

# Create provider instances
llm = AzureOpenAIProvider(model="gpt-5")
embedder = AzureOpenAIEmbeddingProvider()

# Use provider methods
response = await llm.complete(
    prompt="Hello",
    system_prompt="You are helpful"
)

embedding_response = await embedder.embed(["text1", "text2"])
embeddings = embedding_response["embeddings"]
```

### Amazon Bedrock Functions

#### Old way (deprecated)
```python
from nano_graphrag._llm import create_amazon_bedrock_complete_function, amazon_bedrock_embedding

# Create custom function
claude_complete = create_amazon_bedrock_complete_function(
    "us.anthropic.claude-3-sonnet-20240229-v1:0"
)

response = await claude_complete(
    prompt="Hello",
    system_prompt="You are helpful"
)

embeddings = await amazon_bedrock_embedding(["text1", "text2"])
```

#### New way (recommended)
```python
from nano_graphrag.llm.providers import BedrockProvider, BedrockEmbeddingProvider

# Create provider instances
llm = BedrockProvider(model="us.anthropic.claude-3-sonnet-20240229-v1:0")
embedder = BedrockEmbeddingProvider()

# Use provider methods
response = await llm.complete(
    prompt="Hello",
    system_prompt="You are helpful"
)

embedding_response = await embedder.embed(["text1", "text2"])
embeddings = embedding_response["embeddings"]
```

### Global Client Instances

#### Old way (deprecated)
```python
from nano_graphrag._llm import get_openai_async_client_instance

client = get_openai_async_client_instance()
# Direct client usage
```

#### New way (recommended)
```python
from nano_graphrag.llm.providers import OpenAIProvider

provider = OpenAIProvider(model="gpt-5")
# Provider handles client internally
```

## Benefits of the New Approach

1. **Type Safety**: Provider classes offer better type hints and IDE support
2. **Consistent Error Handling**: Unified error handling across all providers
3. **Better Configuration Management**: Cleaner API for provider configuration
4. **Connection Pooling**: Automatic connection management and reuse
5. **Retry Logic**: Built-in retry mechanisms with exponential backoff
6. **Easier Testing**: Mock providers can be easily created for testing
7. **Extensibility**: Easy to add new providers without modifying core code

## Common Migration Patterns

### Using with GraphRAG Configuration

```python
# Old way
from nano_graphrag import GraphRAG
from nano_graphrag._llm import gpt_4o_complete

rag = GraphRAG(
    best_model_func=gpt_4o_complete,
    # ...
)

# New way
from nano_graphrag import GraphRAG
from nano_graphrag.llm.providers import OpenAIProvider

provider = OpenAIProvider(model="gpt-5")
rag = GraphRAG(
    best_model_func=provider.complete_with_cache,
    # ...
)
```

### Custom Provider Configuration

```python
# New way allows for better configuration
from nano_graphrag.llm.providers import OpenAIProvider

provider = OpenAIProvider(
    model="gpt-5",
    api_key="your-api-key",  # Optional, uses env var by default
    base_url="https://your-proxy.com",  # Optional custom endpoint
    request_timeout=60.0,  # Custom timeout
)
```

## Suppressing Deprecation Warnings

If you need to temporarily suppress deprecation warnings during migration:

```python
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    # Your legacy code here
    from nano_graphrag._llm import gpt_4o_complete
```

## Getting Help

If you encounter issues during migration:

1. Check the provider documentation in `nano_graphrag/llm/providers/`
2. Review the provider base classes in `nano_graphrag/llm/base.py`
3. Look at examples in the `examples/` directory
4. Report issues at: https://github.com/anthropics/claude-code/issues

## Summary

The migration from function-based to provider-based LLM interface is straightforward:

1. Replace function imports with provider imports
2. Create provider instances with your desired configuration
3. Use provider methods instead of standalone functions
4. Update any direct client usage to use providers

The new provider-based approach offers better maintainability, type safety, and extensibility while maintaining backward compatibility during the migration period.