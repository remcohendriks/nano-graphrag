"""Tests for configuration management."""

import os
import pytest
from unittest.mock import patch

from nano_graphrag.config import (
    LLMConfig,
    EmbeddingConfig,
    StorageConfig,
    ChunkingConfig,
    EntityExtractionConfig,
    GraphClusteringConfig,
    QueryConfig,
    GraphRAGConfig,
)


class TestLLMConfig:
    """Test LLM configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = LLMConfig()
        assert config.provider == "openai"
        assert config.model == "gpt-5-mini"
        assert config.max_tokens == 32768
        assert config.max_concurrent == 16
        assert config.cache_enabled is True
        assert config.temperature == 0.0
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "deepseek",
            "LLM_MODEL": "deepseek-chat",
            "LLM_MAX_TOKENS": "65536",
            "LLM_MAX_CONCURRENT": "32",
            "LLM_CACHE_ENABLED": "false",
            "LLM_TEMPERATURE": "0.7"
        }):
            config = LLMConfig.from_env()
            assert config.provider == "deepseek"
            assert config.model == "deepseek-chat"
            assert config.max_tokens == 65536
            assert config.max_concurrent == 32
            assert config.cache_enabled is False
            assert config.temperature == 0.7
    
    def test_validation(self):
        """Test validation errors."""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            LLMConfig(max_tokens=0)
        
        with pytest.raises(ValueError, match="max_concurrent must be positive"):
            LLMConfig(max_concurrent=-1)
        
        with pytest.raises(ValueError, match="temperature must be between"):
            LLMConfig(temperature=3.0)
    
    def test_immutable(self):
        """Test that config is immutable."""
        config = LLMConfig()
        with pytest.raises(AttributeError):
            config.provider = "azure"


class TestEmbeddingConfig:
    """Test embedding configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = EmbeddingConfig()
        assert config.provider == "openai"
        assert config.model == "text-embedding-3-small"
        assert config.dimension == 1536
        assert config.batch_size == 32
        assert config.max_concurrent == 16
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "EMBEDDING_PROVIDER": "azure",
            "EMBEDDING_MODEL": "text-embedding-ada-002",
            "EMBEDDING_DIMENSION": "768",
            "EMBEDDING_BATCH_SIZE": "64",
            "EMBEDDING_MAX_CONCURRENT": "8"
        }):
            config = EmbeddingConfig.from_env()
            assert config.provider == "azure"
            assert config.model == "text-embedding-ada-002"
            assert config.dimension == 768
            assert config.batch_size == 64
            assert config.max_concurrent == 8
    
    def test_validation(self):
        """Test validation errors."""
        with pytest.raises(ValueError, match="dimension must be positive"):
            EmbeddingConfig(dimension=0)
        
        with pytest.raises(ValueError, match="batch_size must be positive"):
            EmbeddingConfig(batch_size=-1)


class TestStorageConfig:
    """Test storage configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = StorageConfig()
        assert config.vector_backend == "nano"
        assert config.graph_backend == "networkx"
        assert config.kv_backend == "json"
        assert config.working_dir == "./nano_graphrag_cache"
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "STORAGE_VECTOR_BACKEND": "hnswlib",
            "STORAGE_GRAPH_BACKEND": "networkx",
            "STORAGE_KV_BACKEND": "json",
            "STORAGE_WORKING_DIR": "/tmp/test_cache"
        }):
            config = StorageConfig.from_env()
            assert config.vector_backend == "hnswlib"
            assert config.graph_backend == "networkx"
            assert config.kv_backend == "json"
            assert config.working_dir == "/tmp/test_cache"
    
    def test_validation(self):
        """Test validation errors."""
        with pytest.raises(ValueError, match="Unknown vector backend"):
            StorageConfig(vector_backend="milvus")
        
        with pytest.raises(ValueError, match="Unknown graph backend"):
            StorageConfig(graph_backend="neo4j")
        
        with pytest.raises(ValueError, match="Unknown KV backend"):
            StorageConfig(kv_backend="redis")


class TestChunkingConfig:
    """Test chunking configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = ChunkingConfig()
        assert config.strategy == "token"
        assert config.size == 1200
        assert config.overlap == 100
        assert config.tokenizer == "tiktoken"
        assert config.tokenizer_model == "gpt-4o"
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "CHUNKING_STRATEGY": "sentence",
            "CHUNKING_SIZE": "2000",
            "CHUNKING_OVERLAP": "200",
            "CHUNKING_TOKENIZER": "huggingface",
            "CHUNKING_TOKENIZER_MODEL": "bert-base-uncased"
        }):
            config = ChunkingConfig.from_env()
            assert config.strategy == "sentence"
            assert config.size == 2000
            assert config.overlap == 200
            assert config.tokenizer == "huggingface"
            assert config.tokenizer_model == "bert-base-uncased"
    
    def test_validation(self):
        """Test validation errors."""
        with pytest.raises(ValueError, match="chunk size must be positive"):
            ChunkingConfig(size=0)
        
        with pytest.raises(ValueError, match="overlap must be non-negative"):
            ChunkingConfig(overlap=-1)
        
        with pytest.raises(ValueError, match="overlap .* must be less than size"):
            ChunkingConfig(size=100, overlap=100)
        
        with pytest.raises(ValueError, match="Unknown tokenizer"):
            ChunkingConfig(tokenizer="invalid")


class TestEntityExtractionConfig:
    """Test entity extraction configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = EntityExtractionConfig()
        assert config.max_gleaning == 1
        assert config.summary_max_tokens == 500
        assert config.strategy == "llm"
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "ENTITY_MAX_GLEANING": "3",
            "ENTITY_SUMMARY_MAX_TOKENS": "1000",
            "ENTITY_STRATEGY": "dspy"
        }):
            config = EntityExtractionConfig.from_env()
            assert config.max_gleaning == 3
            assert config.summary_max_tokens == 1000
            assert config.strategy == "dspy"
    
    def test_validation(self):
        """Test validation errors."""
        with pytest.raises(ValueError, match="max_gleaning must be at least 1"):
            EntityExtractionConfig(max_gleaning=0)
        
        with pytest.raises(ValueError, match="summary_max_tokens must be positive"):
            EntityExtractionConfig(summary_max_tokens=-1)


class TestGraphClusteringConfig:
    """Test graph clustering configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = GraphClusteringConfig()
        assert config.algorithm == "leiden"
        assert config.max_cluster_size == 10
        assert config.seed == 0xDEADBEEF
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "GRAPH_CLUSTERING_ALGORITHM": "louvain",
            "GRAPH_MAX_CLUSTER_SIZE": "20",
            "GRAPH_CLUSTERING_SEED": "42"
        }):
            config = GraphClusteringConfig.from_env()
            assert config.algorithm == "louvain"
            assert config.max_cluster_size == 20
            assert config.seed == 42
    
    def test_validation(self):
        """Test validation errors."""
        with pytest.raises(ValueError, match="Unknown clustering algorithm"):
            GraphClusteringConfig(algorithm="invalid")
        
        with pytest.raises(ValueError, match="max_cluster_size must be positive"):
            GraphClusteringConfig(max_cluster_size=0)


class TestQueryConfig:
    """Test query configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = QueryConfig()
        assert config.enable_local is True
        assert config.enable_global is True
        assert config.enable_naive_rag is False
        assert config.similarity_threshold == 0.2
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "QUERY_ENABLE_LOCAL": "false",
            "QUERY_ENABLE_GLOBAL": "false",
            "QUERY_ENABLE_NAIVE_RAG": "true",
            "QUERY_SIMILARITY_THRESHOLD": "0.5"
        }):
            config = QueryConfig.from_env()
            assert config.enable_local is False
            assert config.enable_global is False
            assert config.enable_naive_rag is True
            assert config.similarity_threshold == 0.5
    
    def test_validation(self):
        """Test validation errors."""
        with pytest.raises(ValueError, match="similarity_threshold must be between"):
            QueryConfig(similarity_threshold=1.5)
        
        with pytest.raises(ValueError, match="similarity_threshold must be between"):
            QueryConfig(similarity_threshold=-0.1)


class TestGraphRAGConfig:
    """Test main GraphRAG configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = GraphRAGConfig()
        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.embedding, EmbeddingConfig)
        assert isinstance(config.storage, StorageConfig)
        assert isinstance(config.chunking, ChunkingConfig)
        assert isinstance(config.entity_extraction, EntityExtractionConfig)
        assert isinstance(config.graph_clustering, GraphClusteringConfig)
        assert isinstance(config.query, QueryConfig)
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "azure",
            "STORAGE_VECTOR_BACKEND": "hnswlib",
            "CHUNKING_SIZE": "2000",
        }):
            config = GraphRAGConfig.from_env()
            assert config.llm.provider == "azure"
            assert config.storage.vector_backend == "hnswlib"
            assert config.chunking.size == 2000
    
    def test_to_dict(self):
        """Test conversion to dictionary for compatibility."""
        config = GraphRAGConfig()
        d = config.to_dict()
        
        assert "working_dir" in d
        assert "enable_local" in d
        assert "chunk_token_size" in d
        assert d["chunk_token_size"] == config.chunking.size
        assert d["enable_local"] == config.query.enable_local
        assert d["working_dir"] == config.storage.working_dir
    
    def test_custom_config(self):
        """Test creating with custom sub-configs."""
        config = GraphRAGConfig(
            llm=LLMConfig(provider="deepseek"),
            storage=StorageConfig(vector_backend="hnswlib"),
            chunking=ChunkingConfig(size=2000)
        )
        assert config.llm.provider == "deepseek"
        assert config.storage.vector_backend == "hnswlib"
        assert config.chunking.size == 2000
    
    def test_immutable(self):
        """Test that config is immutable."""
        config = GraphRAGConfig()
        with pytest.raises(AttributeError):
            config.llm = LLMConfig(provider="azure")