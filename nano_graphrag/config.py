"""Configuration management for nano-graphrag."""

import os
from dataclasses import dataclass, field
from typing import Optional, Type, Callable, Any, List
from pathlib import Path


@dataclass(frozen=True)
class LLMConfig:
    """LLM provider configuration."""
    provider: str = "openai"  # openai, azure, bedrock, deepseek
    model: str = "gpt-5-mini"
    max_tokens: int = 32768
    max_concurrent: int = 8
    cache_enabled: bool = True
    temperature: float = 0.0
    request_timeout: float = 30.0
    
    @classmethod
    def from_env(cls) -> 'LLMConfig':
        """Create config from environment variables."""
        return cls(
            provider=os.getenv("LLM_PROVIDER", "openai"),
            model=os.getenv("LLM_MODEL", "gpt-5-mini"),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "32768")),
            max_concurrent=int(os.getenv("LLM_MAX_CONCURRENT", "8")),
            cache_enabled=os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true",
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
            request_timeout=float(os.getenv("LLM_REQUEST_TIMEOUT", "30.0"))
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
    max_concurrent: int = 8
    
    @classmethod
    def from_env(cls) -> 'EmbeddingConfig':
        """Create config from environment variables."""
        return cls(
            provider=os.getenv("EMBEDDING_PROVIDER", "openai"),
            model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            dimension=int(os.getenv("EMBEDDING_DIMENSION", "1536")),
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "32")),
            max_concurrent=int(os.getenv("EMBEDDING_MAX_CONCURRENT", "8"))
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
class Node2VecConfig:
    """Node2Vec parameters for graph embeddings."""
    enabled: bool = False  # Allow disabling for Neo4j/Qdrant
    dimensions: int = 128
    num_walks: int = 10
    walk_length: int = 40
    window_size: int = 2
    iterations: int = 3
    random_seed: int = 3


@dataclass(frozen=True)
class HybridSearchConfig:
    """Hybrid search configuration for sparse+dense retrieval.

    When using external SPLADE service, only enabled and RRF parameters are used.
    The service handles its own batching and timeouts.
    """
    enabled: bool = False
    rrf_k: int = 60  # RRF fusion parameter (Note: Qdrant currently uses fixed k=60)
    sparse_top_k_multiplier: float = 2.0  # Fetch 2x candidates for sparse
    dense_top_k_multiplier: float = 1.0   # Fetch 1x candidates for dense

    @classmethod
    def from_env(cls) -> 'HybridSearchConfig':
        """Create config from environment variables."""
        return cls(
            enabled=os.getenv("ENABLE_HYBRID_SEARCH", "false").lower() == "true",
            rrf_k=int(os.getenv("RRF_K", "60")),
            sparse_top_k_multiplier=float(os.getenv("SPARSE_TOP_K_MULTIPLIER", "2.0")),
            dense_top_k_multiplier=float(os.getenv("DENSE_TOP_K_MULTIPLIER", "1.0"))
        )

    def __post_init__(self):
        """Validate configuration."""
        if self.rrf_k <= 0:
            raise ValueError(f"rrf_k must be positive, got {self.rrf_k}")
        if self.sparse_top_k_multiplier <= 0:
            raise ValueError(f"sparse_top_k_multiplier must be positive, got {self.sparse_top_k_multiplier}")
        if self.dense_top_k_multiplier <= 0:
            raise ValueError(f"dense_top_k_multiplier must be positive, got {self.dense_top_k_multiplier}")


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
    
    # Qdrant specific settings
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    qdrant_collection_params: dict = field(default_factory=dict)
    
    # Neo4j specific settings
    neo4j_url: str = "neo4j://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "neo4j"
    
    # Neo4j production configuration
    neo4j_max_connection_pool_size: int = 50
    neo4j_connection_timeout: float = 30.0
    neo4j_encrypted: bool = False  # Default to False, will be inferred from URL
    neo4j_max_transaction_retry_time: float = 30.0
    neo4j_batch_size: int = 1000  # Batch size for bulk operations

    # Redis specific settings
    redis_url: str = "redis://localhost:6379"
    redis_password: Optional[str] = None
    redis_max_connections: int = 50
    redis_connection_timeout: float = 5.0
    redis_socket_timeout: float = 5.0
    redis_health_check_interval: int = 30

    # Node2Vec configuration (for NetworkX backend)
    node2vec: Node2VecConfig = field(default_factory=lambda: Node2VecConfig(enabled=True))

    # Hybrid search configuration
    hybrid_search: HybridSearchConfig = field(default_factory=lambda: HybridSearchConfig())

    @classmethod
    def from_env(cls) -> 'StorageConfig':
        """Create config from environment variables."""
        # Get Neo4j URL for TLS inference
        neo4j_url = os.getenv("NEO4J_URL", "neo4j://localhost:7687")
        
        # Intelligently infer encryption from URL scheme if not explicitly set
        if os.getenv("NEO4J_ENCRYPTED") is not None:
            # Explicit setting takes precedence
            neo4j_encrypted = os.getenv("NEO4J_ENCRYPTED", "false").lower() == "true"
        elif neo4j_url.startswith(('neo4j+s://', 'bolt+s://')):
            # URL uses secure scheme
            neo4j_encrypted = True
        elif neo4j_url.startswith(('neo4j://', 'bolt://')):
            # URL uses non-secure scheme
            neo4j_encrypted = False
        else:
            # Default to False for unknown schemes
            neo4j_encrypted = False
            
        return cls(
            vector_backend=os.getenv("STORAGE_VECTOR_BACKEND", "nano"),
            graph_backend=os.getenv("STORAGE_GRAPH_BACKEND", "networkx"),
            kv_backend=os.getenv("STORAGE_KV_BACKEND", "json"),
            working_dir=os.getenv("STORAGE_WORKING_DIR", "./nano_graphrag_cache"),
            hnsw_ef_construction=int(os.getenv("HNSW_EF_CONSTRUCTION", "100")),
            hnsw_ef_search=int(os.getenv("HNSW_EF_SEARCH", "50")),
            hnsw_m=int(os.getenv("HNSW_M", "16")),
            hnsw_max_elements=int(os.getenv("HNSW_MAX_ELEMENTS", "1000000")),
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY", None),
            neo4j_url=neo4j_url,
            neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "password"),
            neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
            neo4j_max_connection_pool_size=int(os.getenv("NEO4J_MAX_CONNECTION_POOL_SIZE", "50")),
            neo4j_connection_timeout=float(os.getenv("NEO4J_CONNECTION_TIMEOUT", "30.0")),
            neo4j_encrypted=neo4j_encrypted,
            neo4j_max_transaction_retry_time=float(os.getenv("NEO4J_MAX_TRANSACTION_RETRY_TIME", "30.0")),
            neo4j_batch_size=int(os.getenv("NEO4J_BATCH_SIZE", "1000")),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
            redis_password=os.getenv("REDIS_PASSWORD", None),
            redis_max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "50")),
            redis_connection_timeout=float(os.getenv("REDIS_CONNECTION_TIMEOUT", "5.0")),
            redis_socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0")),
            redis_health_check_interval=int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30")),
            hybrid_search=HybridSearchConfig.from_env()
        )
    
    def __post_init__(self):
        """Validate configuration."""
        # Only allow implemented backends
        valid_vector_backends = {"nano", "hnswlib", "qdrant"}
        valid_graph_backends = {"networkx", "neo4j"}
        valid_kv_backends = {"json", "redis"}
        
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
    max_continuation_attempts: int = 5  # Max attempts to continue truncated extraction
    summary_max_tokens: int = 500
    strategy: str = "llm"  # llm, dspy
    entity_types: List[str] = field(default_factory=lambda: [
        "PERSON", "ORGANIZATION", "LOCATION", "EVENT", "DATE",
        "TIME", "MONEY", "PERCENTAGE", "PRODUCT", "CONCEPT"
    ])
    enable_type_prefix_embeddings: bool = True

    @classmethod
    def from_env(cls) -> 'EntityExtractionConfig':
        """Create config from environment variables."""
        entity_types_str = os.getenv("ENTITY_TYPES", "")
        if entity_types_str and entity_types_str.strip():
            # Strip whitespace, uppercase, and filter out empty values
            entity_types = [t.strip().upper() for t in entity_types_str.split(",") if t.strip()]
        else:
            entity_types = None

        # Check for type prefix embeddings config
        enable_type_prefix = os.getenv("ENABLE_TYPE_PREFIX_EMBEDDINGS", "true").lower() == "true"

        return cls(
            max_gleaning=int(os.getenv("ENTITY_MAX_GLEANING", "1")),
            max_continuation_attempts=int(os.getenv("ENTITY_MAX_CONTINUATIONS", "5")),
            summary_max_tokens=int(os.getenv("ENTITY_SUMMARY_MAX_TOKENS", "500")),
            strategy=os.getenv("ENTITY_STRATEGY", "llm"),
            entity_types=entity_types or cls.__dataclass_fields__["entity_types"].default_factory(),
            enable_type_prefix_embeddings=enable_type_prefix
        )

    def __post_init__(self):
        """Validate configuration."""
        if self.max_gleaning < 0:
            raise ValueError(f"max_gleaning must be non-negative, got {self.max_gleaning}")
        if self.max_continuation_attempts < 0:
            raise ValueError(f"max_continuation_attempts must be non-negative, got {self.max_continuation_attempts}")
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
    local_max_token_for_text_unit: int = 100000
    local_template: Optional[str] = None
    global_template: Optional[str] = None

    @classmethod
    def from_env(cls) -> 'QueryConfig':
        """Create config from environment variables."""
        return cls(
            enable_local=os.getenv("QUERY_ENABLE_LOCAL", "true").lower() == "true",
            enable_global=os.getenv("QUERY_ENABLE_GLOBAL", "true").lower() == "true",
            enable_naive_rag=os.getenv("QUERY_ENABLE_NAIVE_RAG", "false").lower() == "true",
            similarity_threshold=float(os.getenv("QUERY_SIMILARITY_THRESHOLD", "0.2")),
            local_max_token_for_text_unit=int(os.getenv("QUERY_LOCAL_MAX_TOKEN_FOR_TEXT_UNIT", "100000")),
            local_template=os.getenv("QUERY_LOCAL_TEMPLATE"),
            global_template=os.getenv("QUERY_GLOBAL_TEMPLATE")
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
        """Convert config to clean dictionary for active configuration.
        
        Returns only actively used configuration parameters.
        For backward compatibility with legacy code, use to_legacy_dict().
        """
        config_dict = {
            'working_dir': self.storage.working_dir,
            'enable_local': self.query.enable_local,
            'enable_naive_rag': self.query.enable_naive_rag,
            'chunk_token_size': self.chunking.size,
            'chunk_overlap_token_size': self.chunking.overlap,
            'entity_extract_max_gleaning': self.entity_extraction.max_gleaning,
            'entity_summary_to_max_tokens': self.entity_extraction.summary_max_tokens,
            'entity_extraction': {
                'entity_types': self.entity_extraction.entity_types,
                'enable_type_prefix_embeddings': self.entity_extraction.enable_type_prefix_embeddings
            },
            'graph_cluster_algorithm': self.graph_clustering.algorithm,
            'max_graph_cluster_size': self.graph_clustering.max_cluster_size,
            'graph_cluster_seed': self.graph_clustering.seed,
            'embedding_batch_num': self.embedding.batch_size,
            'embedding_func_max_async': self.embedding.max_concurrent,
            'query_better_than_threshold': self.query.similarity_threshold,
            'best_model_max_token_size': self.llm.max_tokens,
            'best_model_max_async': self.llm.max_concurrent,
            'enable_llm_cache': self.llm.cache_enabled,
        }
        
        # Add storage-specific configuration
        if self.storage.vector_backend == "hnswlib":
            config_dict['vector_db_storage_cls_kwargs'] = {
                'ef_construction': self.storage.hnsw_ef_construction,
                'ef_search': self.storage.hnsw_ef_search,
                'M': self.storage.hnsw_m,
                'max_elements': self.storage.hnsw_max_elements,
            }
        elif self.storage.vector_backend == "qdrant":
            # Add Qdrant-specific configuration
            config_dict['qdrant_url'] = self.storage.qdrant_url
            config_dict['qdrant_api_key'] = self.storage.qdrant_api_key
            config_dict['qdrant_collection_params'] = self.storage.qdrant_collection_params
        
        # Add Redis configuration if using Redis backend
        if self.storage.kv_backend == "redis":
            config_dict['redis_url'] = self.storage.redis_url
            config_dict['redis_password'] = self.storage.redis_password
            config_dict['redis_max_connections'] = self.storage.redis_max_connections
            config_dict['redis_connection_timeout'] = self.storage.redis_connection_timeout
            config_dict['redis_socket_timeout'] = self.storage.redis_socket_timeout
            config_dict['redis_health_check_interval'] = self.storage.redis_health_check_interval

        # Add Neo4j configuration if using Neo4j backend
        if self.storage.graph_backend == "neo4j":
            config_dict['addon_params'] = {
                'neo4j_url': self.storage.neo4j_url,
                'neo4j_auth': (self.storage.neo4j_username, self.storage.neo4j_password),
                'neo4j_database': self.storage.neo4j_database,
                'neo4j_max_connection_pool_size': self.storage.neo4j_max_connection_pool_size,
                'neo4j_connection_timeout': self.storage.neo4j_connection_timeout,
                'neo4j_encrypted': self.storage.neo4j_encrypted,
                'neo4j_max_transaction_retry_time': self.storage.neo4j_max_transaction_retry_time,
                'neo4j_batch_size': self.storage.neo4j_batch_size,
            }
        
        # Add node2vec configuration if enabled and using NetworkX
        if self.storage.graph_backend == "networkx" and self.storage.node2vec.enabled:
            config_dict['node2vec_params'] = {
                'dimensions': self.storage.node2vec.dimensions,
                'num_walks': self.storage.node2vec.num_walks,
                'walk_length': self.storage.node2vec.walk_length,
                'window_size': self.storage.node2vec.window_size,
                'iterations': self.storage.node2vec.iterations,
                'random_seed': self.storage.node2vec.random_seed,
            }
        
        return config_dict
    
    def to_legacy_dict(self) -> dict:
        """Convert config to dictionary with full legacy compatibility.
        
        This method maintains backward compatibility with all legacy code.
        New code should use to_dict() instead.
        """
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
            'entity_extraction': {
                'entity_types': self.entity_extraction.entity_types,
                'enable_type_prefix_embeddings': self.entity_extraction.enable_type_prefix_embeddings
            },
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
            'hybrid_search': self.storage.hybrid_search,
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


def validate_config(config: GraphRAGConfig) -> list[str]:
    """Validate configuration and return list of warnings.
    
    Args:
        config: GraphRAG configuration to validate
        
    Returns:
        List of warning messages (empty if no issues)
    """
    warnings = []
    
    # Check for common misconfigurations
    if config.storage.vector_backend == "hnswlib" and config.storage.hnsw_ef_search > 500:
        warnings.append(f"Very high ef_search ({config.storage.hnsw_ef_search}) may impact performance")
    
    if config.llm.max_concurrent > 100:
        warnings.append(f"Very high max_concurrent ({config.llm.max_concurrent}) may hit rate limits")
    
    if config.embedding.max_concurrent > 100:
        warnings.append(f"Very high embedding max_concurrent ({config.embedding.max_concurrent}) may hit rate limits")
    
    if config.storage.hnsw_ef_construction < config.storage.hnsw_ef_search:
        warnings.append(f"ef_construction ({config.storage.hnsw_ef_construction}) should be >= ef_search ({config.storage.hnsw_ef_search})")
    
    return warnings