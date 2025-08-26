"""Configuration management for nano-graphrag."""

import os
from dataclasses import dataclass, field
from typing import Optional, Type, Callable, Any
from pathlib import Path


@dataclass(frozen=True)
class LLMConfig:
    """LLM provider configuration."""
    provider: str = "openai"  # openai, azure, bedrock, deepseek
    model: str = "gpt-5-mini"
    max_tokens: int = 32768
    max_concurrent: int = 16
    cache_enabled: bool = True
    temperature: float = 0.0
    
    @classmethod
    def from_env(cls) -> 'LLMConfig':
        """Create config from environment variables."""
        return cls(
            provider=os.getenv("LLM_PROVIDER", "openai"),
            model=os.getenv("LLM_MODEL", "gpt-5-mini"),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "32768")),
            max_concurrent=int(os.getenv("LLM_MAX_CONCURRENT", "16")),
            cache_enabled=os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true",
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.0"))
        )
    
    def __post_init__(self):
        """Validate configuration."""
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")
        if self.max_concurrent <= 0:
            raise ValueError(f"max_concurrent must be positive, got {self.max_concurrent}")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"temperature must be between 0.0 and 2.0, got {self.temperature}")


@dataclass(frozen=True)
class EmbeddingConfig:
    """Embedding configuration."""
    provider: str = "openai"  # openai, azure, bedrock, local
    model: str = "text-embedding-3-small"
    dimension: int = 1536
    batch_size: int = 32
    max_concurrent: int = 16
    
    @classmethod
    def from_env(cls) -> 'EmbeddingConfig':
        """Create config from environment variables."""
        return cls(
            provider=os.getenv("EMBEDDING_PROVIDER", "openai"),
            model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            dimension=int(os.getenv("EMBEDDING_DIMENSION", "1536")),
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "32")),
            max_concurrent=int(os.getenv("EMBEDDING_MAX_CONCURRENT", "16"))
        )
    
    def __post_init__(self):
        """Validate configuration."""
        if self.dimension <= 0:
            raise ValueError(f"dimension must be positive, got {self.dimension}")
        if self.batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {self.batch_size}")
        if self.max_concurrent <= 0:
            raise ValueError(f"max_concurrent must be positive, got {self.max_concurrent}")


@dataclass(frozen=True)
class StorageConfig:
    """Storage backend configuration."""
    vector_backend: str = "nano"  # nano, hnswlib, milvus, qdrant
    graph_backend: str = "networkx"  # networkx, neo4j
    kv_backend: str = "json"  # json, redis
    working_dir: str = "./nano_graphrag_cache"
    
    # HNSW specific settings
    hnsw_ef_construction: int = 100
    hnsw_ef_search: int = 50
    hnsw_m: int = 16
    hnsw_max_elements: int = 1_000_000
    
    @classmethod
    def from_env(cls) -> 'StorageConfig':
        """Create config from environment variables."""
        return cls(
            vector_backend=os.getenv("STORAGE_VECTOR_BACKEND", "nano"),
            graph_backend=os.getenv("STORAGE_GRAPH_BACKEND", "networkx"),
            kv_backend=os.getenv("STORAGE_KV_BACKEND", "json"),
            working_dir=os.getenv("STORAGE_WORKING_DIR", "./nano_graphrag_cache"),
            hnsw_ef_construction=int(os.getenv("HNSW_EF_CONSTRUCTION", "100")),
            hnsw_ef_search=int(os.getenv("HNSW_EF_SEARCH", "50")),
            hnsw_m=int(os.getenv("HNSW_M", "16")),
            hnsw_max_elements=int(os.getenv("HNSW_MAX_ELEMENTS", "1000000"))
        )
    
    def __post_init__(self):
        """Validate configuration."""
        # Only allow implemented backends
        valid_vector_backends = {"nano", "hnswlib"}
        valid_graph_backends = {"networkx"}
        valid_kv_backends = {"json"}
        
        if self.vector_backend not in valid_vector_backends:
            raise ValueError(f"Unknown vector backend: {self.vector_backend}. Available: {valid_vector_backends}")
        if self.graph_backend not in valid_graph_backends:
            raise ValueError(f"Unknown graph backend: {self.graph_backend}. Available: {valid_graph_backends}")
        if self.kv_backend not in valid_kv_backends:
            raise ValueError(f"Unknown KV backend: {self.kv_backend}. Available: {valid_kv_backends}")


@dataclass(frozen=True)
class ChunkingConfig:
    """Text chunking configuration."""
    strategy: str = "token"  # token, sentence, paragraph
    size: int = 1200
    overlap: int = 100
    tokenizer: str = "tiktoken"  # tiktoken, huggingface
    tokenizer_model: str = "gpt-4o"  # for tiktoken or HF model name
    
    @classmethod
    def from_env(cls) -> 'ChunkingConfig':
        """Create config from environment variables."""
        return cls(
            strategy=os.getenv("CHUNKING_STRATEGY", "token"),
            size=int(os.getenv("CHUNKING_SIZE", "1200")),
            overlap=int(os.getenv("CHUNKING_OVERLAP", "100")),
            tokenizer=os.getenv("CHUNKING_TOKENIZER", "tiktoken"),
            tokenizer_model=os.getenv("CHUNKING_TOKENIZER_MODEL", "gpt-4o")
        )
    
    def __post_init__(self):
        """Validate configuration."""
        if self.size <= 0:
            raise ValueError(f"chunk size must be positive, got {self.size}")
        if self.overlap < 0:
            raise ValueError(f"overlap must be non-negative, got {self.overlap}")
        if self.overlap >= self.size:
            raise ValueError(f"overlap ({self.overlap}) must be less than size ({self.size})")
        if self.tokenizer not in {"tiktoken", "huggingface"}:
            raise ValueError(f"Unknown tokenizer: {self.tokenizer}")


@dataclass(frozen=True)
class EntityExtractionConfig:
    """Entity extraction configuration."""
    max_gleaning: int = 1
    summary_max_tokens: int = 500
    strategy: str = "llm"  # llm, dspy
    
    @classmethod
    def from_env(cls) -> 'EntityExtractionConfig':
        """Create config from environment variables."""
        return cls(
            max_gleaning=int(os.getenv("ENTITY_MAX_GLEANING", "1")),
            summary_max_tokens=int(os.getenv("ENTITY_SUMMARY_MAX_TOKENS", "500")),
            strategy=os.getenv("ENTITY_STRATEGY", "llm")
        )
    
    def __post_init__(self):
        """Validate configuration."""
        if self.max_gleaning < 1:
            raise ValueError(f"max_gleaning must be at least 1, got {self.max_gleaning}")
        if self.summary_max_tokens <= 0:
            raise ValueError(f"summary_max_tokens must be positive, got {self.summary_max_tokens}")


@dataclass(frozen=True)
class GraphClusteringConfig:
    """Graph clustering configuration."""
    algorithm: str = "leiden"  # leiden, louvain
    max_cluster_size: int = 10
    seed: int = 0xDEADBEEF
    
    @classmethod
    def from_env(cls) -> 'GraphClusteringConfig':
        """Create config from environment variables."""
        return cls(
            algorithm=os.getenv("GRAPH_CLUSTERING_ALGORITHM", "leiden"),
            max_cluster_size=int(os.getenv("GRAPH_MAX_CLUSTER_SIZE", "10")),
            seed=int(os.getenv("GRAPH_CLUSTERING_SEED", str(0xDEADBEEF)))
        )
    
    def __post_init__(self):
        """Validate configuration."""
        if self.algorithm not in {"leiden", "louvain"}:
            raise ValueError(f"Unknown clustering algorithm: {self.algorithm}")
        if self.max_cluster_size <= 0:
            raise ValueError(f"max_cluster_size must be positive, got {self.max_cluster_size}")


@dataclass(frozen=True)
class QueryConfig:
    """Query configuration."""
    enable_local: bool = True
    enable_global: bool = True
    enable_naive_rag: bool = False
    similarity_threshold: float = 0.2
    
    @classmethod
    def from_env(cls) -> 'QueryConfig':
        """Create config from environment variables."""
        return cls(
            enable_local=os.getenv("QUERY_ENABLE_LOCAL", "true").lower() == "true",
            enable_global=os.getenv("QUERY_ENABLE_GLOBAL", "true").lower() == "true",
            enable_naive_rag=os.getenv("QUERY_ENABLE_NAIVE_RAG", "false").lower() == "true",
            similarity_threshold=float(os.getenv("QUERY_SIMILARITY_THRESHOLD", "0.2"))
        )
    
    def __post_init__(self):
        """Validate configuration."""
        if not 0.0 <= self.similarity_threshold <= 1.0:
            raise ValueError(f"similarity_threshold must be between 0.0 and 1.0, got {self.similarity_threshold}")


@dataclass(frozen=True)
class GraphRAGConfig:
    """Main GraphRAG configuration."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    entity_extraction: EntityExtractionConfig = field(default_factory=EntityExtractionConfig)
    graph_clustering: GraphClusteringConfig = field(default_factory=GraphClusteringConfig)
    query: QueryConfig = field(default_factory=QueryConfig)
    
    @classmethod
    def from_env(cls) -> 'GraphRAGConfig':
        """Create complete config from environment variables."""
        return cls(
            llm=LLMConfig.from_env(),
            embedding=EmbeddingConfig.from_env(),
            storage=StorageConfig.from_env(),
            chunking=ChunkingConfig.from_env(),
            entity_extraction=EntityExtractionConfig.from_env(),
            graph_clustering=GraphClusteringConfig.from_env(),
            query=QueryConfig.from_env()
        )
    
    def to_dict(self) -> dict:
        """Convert config to dictionary for compatibility."""
        config_dict = {
            'working_dir': self.storage.working_dir,
            'enable_local': self.query.enable_local,
            'enable_naive_rag': self.query.enable_naive_rag,
            'chunk_token_size': self.chunking.size,
            'chunk_overlap_token_size': self.chunking.overlap,
            'tokenizer_type': self.chunking.tokenizer,
            'tiktoken_model_name': self.chunking.tokenizer_model if self.chunking.tokenizer == "tiktoken" else "gpt-4o",
            'huggingface_model_name': self.chunking.tokenizer_model if self.chunking.tokenizer == "huggingface" else "bert-base-uncased",
            'entity_extract_max_gleaning': self.entity_extraction.max_gleaning,
            'entity_summary_to_max_tokens': self.entity_extraction.summary_max_tokens,
            'graph_cluster_algorithm': self.graph_clustering.algorithm,
            'max_graph_cluster_size': self.graph_clustering.max_cluster_size,
            'graph_cluster_seed': self.graph_clustering.seed,
            'embedding_batch_num': self.embedding.batch_size,
            'embedding_func_max_async': self.embedding.max_concurrent,
            'query_better_than_threshold': self.query.similarity_threshold,
            'best_model_max_token_size': self.llm.max_tokens,
            'best_model_max_async': self.llm.max_concurrent,
            'cheap_model_max_token_size': self.llm.max_tokens,
            'cheap_model_max_async': self.llm.max_concurrent,
            'enable_llm_cache': self.llm.cache_enabled,
            # Additional fields required by legacy functions
            'node_embedding_algorithm': 'node2vec',
            'node2vec_params': {
                'dimensions': self.embedding.dimension,
                'num_walks': 10,
                'walk_length': 40,
                'window_size': 2,
                'iterations': 3,
                'random_seed': 3,
            },
            'always_create_working_dir': True,
            'addon_params': {},
        }
        
        # Add HNSW-specific parameters if using hnswlib backend
        if self.storage.vector_backend == "hnswlib":
            config_dict['vector_db_storage_cls_kwargs'] = {
                'ef_construction': self.storage.hnsw_ef_construction,
                'ef_search': self.storage.hnsw_ef_search,
                'M': self.storage.hnsw_m,
                'max_elements': self.storage.hnsw_max_elements,
            }
        
        return config_dict