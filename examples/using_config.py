"""Example of using the new configuration system."""

import asyncio
import os
from nano_graphrag import GraphRAG, QueryParam
from nano_graphrag.config import (
    GraphRAGConfig,
    LLMConfig,
    StorageConfig,
    ChunkingConfig,
    EmbeddingConfig,
)


def example_default_config():
    """Use GraphRAG with default configuration."""
    print("=== Using Default Configuration ===")
    
    # Create GraphRAG with all defaults
    rag = GraphRAG()
    
    # Insert document
    with open("./tests/mock_data.txt", encoding="utf-8-sig") as f:
        text = f.read()
    
    rag.insert(text)
    
    # Query
    result = rag.query(
        "What are the top themes in this story?",
        param=QueryParam(mode="global")
    )
    print(f"Result: {result}")


def example_custom_config():
    """Use GraphRAG with custom configuration."""
    print("\n=== Using Custom Configuration ===")
    
    # Create custom configuration
    config = GraphRAGConfig(
        llm=LLMConfig(
            provider="openai",
            model="gpt-5",
            max_tokens=4096,
            temperature=0.5
        ),
        storage=StorageConfig(
            vector_backend="hnswlib",
            graph_backend="networkx",
            working_dir="./custom_cache"
        ),
        chunking=ChunkingConfig(
            size=1500,
            overlap=150,
            tokenizer="tiktoken"
        ),
        embedding=EmbeddingConfig(
            provider="openai",
            model="text-embedding-3-large",
            dimension=3072
        )
    )
    
    # Create GraphRAG with custom config
    rag = GraphRAG(config)
    
    # Use as normal
    print(f"Working directory: {rag.working_dir}")
    print(f"LLM provider: {config.llm.provider}")
    print(f"Storage backend: {config.storage.vector_backend}")


def example_env_config():
    """Use GraphRAG with configuration from environment variables."""
    print("\n=== Using Environment Variable Configuration ===")
    
    # Set environment variables (normally these would be in your shell or .env)
    os.environ["LLM_PROVIDER"] = "deepseek"
    os.environ["LLM_MODEL"] = "deepseek-chat"
    os.environ["STORAGE_VECTOR_BACKEND"] = "nano"
    os.environ["CHUNKING_SIZE"] = "2000"
    
    # Create config from environment
    config = GraphRAGConfig.from_env()
    
    # Create GraphRAG
    rag = GraphRAG(config)
    
    print(f"LLM provider from env: {config.llm.provider}")
    print(f"LLM model from env: {config.llm.model}")
    print(f"Chunk size from env: {config.chunking.size}")


def example_deepseek_config():
    """Example using DeepSeek as LLM provider."""
    print("\n=== Using DeepSeek Configuration ===")
    
    # Make sure to set your DeepSeek API key
    # os.environ["DEEPSEEK_API_KEY"] = "your-api-key"
    
    config = GraphRAGConfig(
        llm=LLMConfig(
            provider="deepseek",
            model="deepseek-chat",
            max_tokens=32768
        ),
        # DeepSeek can use OpenAI embeddings
        embedding=EmbeddingConfig(
            provider="openai",
            model="text-embedding-3-small"
        )
    )
    
    rag = GraphRAG(config)
    print(f"Using DeepSeek model: {config.llm.model}")


def example_minimal_config():
    """Example with minimal configuration for testing."""
    print("\n=== Using Minimal Test Configuration ===")
    
    # Minimal config for fast testing
    config = GraphRAGConfig(
        llm=LLMConfig(
            max_concurrent=4,  # Reduce concurrency for testing
            cache_enabled=True  # Enable cache to speed up testing
        ),
        chunking=ChunkingConfig(
            size=500,  # Smaller chunks for testing
            overlap=50
        ),
        storage=StorageConfig(
            working_dir="./test_cache"
        )
    )
    
    rag = GraphRAG(config)
    print(f"Test cache directory: {config.storage.working_dir}")
    print(f"Chunk size for testing: {config.chunking.size}")


async def example_async_usage():
    """Example of async usage with configuration."""
    print("\n=== Async Usage Example ===")
    
    config = GraphRAGConfig(
        llm=LLMConfig(
            provider="openai",
            model="gpt-5-mini",
            max_concurrent=8
        )
    )
    
    rag = GraphRAG(config)
    
    # Async insert
    await rag.ainsert("This is a test document about AI and machine learning.")
    
    # Async query
    result = await rag.aquery(
        "What is this document about?",
        param=QueryParam(mode="naive")
    )
    print(f"Async query result: {result}")


if __name__ == "__main__":
    # Run examples
    example_default_config()
    example_custom_config()
    example_env_config()
    example_deepseek_config()
    example_minimal_config()
    
    # Run async example
    asyncio.run(example_async_usage())