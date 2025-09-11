"""Storage factory for centralized backend creation."""

from typing import Type, Dict, Optional, Set, Any, Callable
from nano_graphrag.base import BaseVectorStorage, BaseGraphStorage, BaseKVStorage


class StorageFactory:
    """Factory for creating storage backends with validation and registration."""
    
    _vector_backends: Dict[str, Callable[[], Type[BaseVectorStorage]]] = {}
    _graph_backends: Dict[str, Callable[[], Type[BaseGraphStorage]]] = {}
    _kv_backends: Dict[str, Callable[[], Type[BaseKVStorage]]] = {}
    
    # Maintain current restrictions from StorageConfig
    ALLOWED_VECTOR = {"nano", "hnswlib", "qdrant"}
    ALLOWED_GRAPH = {"networkx"}
    ALLOWED_KV = {"json"}
    
    @classmethod
    def register_vector(cls, name: str, backend_loader: Callable[[], Type[BaseVectorStorage]]) -> None:
        """Register a vector storage backend.
        
        Args:
            name: Backend name (must be in ALLOWED_VECTOR)
            backend_loader: Function that returns the vector storage class
            
        Raises:
            ValueError: If backend name not in allowed list
        """
        if name not in cls.ALLOWED_VECTOR:
            raise ValueError(f"Backend {name} not in allowed vector backends: {cls.ALLOWED_VECTOR}")
        cls._vector_backends[name] = backend_loader
    
    @classmethod
    def register_graph(cls, name: str, backend_loader: Callable[[], Type[BaseGraphStorage]]) -> None:
        """Register a graph storage backend.
        
        Args:
            name: Backend name (must be in ALLOWED_GRAPH)
            backend_loader: Function that returns the graph storage class
            
        Raises:
            ValueError: If backend name not in allowed list
        """
        if name not in cls.ALLOWED_GRAPH:
            raise ValueError(f"Backend {name} not in allowed graph backends: {cls.ALLOWED_GRAPH}")
        cls._graph_backends[name] = backend_loader
    
    @classmethod
    def register_kv(cls, name: str, backend_loader: Callable[[], Type[BaseKVStorage]]) -> None:
        """Register a KV storage backend.
        
        Args:
            name: Backend name (must be in ALLOWED_KV)
            backend_loader: Function that returns the KV storage class
            
        Raises:
            ValueError: If backend name not in allowed list
        """
        if name not in cls.ALLOWED_KV:
            raise ValueError(f"Backend {name} not in allowed KV backends: {cls.ALLOWED_KV}")
        cls._kv_backends[name] = backend_loader
    
    @classmethod
    def create_vector_storage(
        cls, 
        backend: str,
        namespace: str,
        global_config: dict,
        embedding_func: Any,
        meta_fields: Optional[Set[str]] = None,
        **kwargs
    ) -> BaseVectorStorage:
        """Create a vector storage instance.
        
        Args:
            backend: Backend name
            namespace: Storage namespace
            global_config: Global configuration dict
            embedding_func: Embedding function
            meta_fields: Optional metadata fields to track
            **kwargs: Additional backend-specific parameters
            
        Returns:
            Initialized vector storage instance
            
        Raises:
            ValueError: If backend not registered
        """
        if backend not in cls._vector_backends:
            # Try to register backends if not already done
            _register_backends()
            if backend not in cls._vector_backends:
                raise ValueError(f"Unknown vector backend: {backend}. Available: {list(cls._vector_backends.keys())}")
        
        # Build kwargs matching current storage contracts
        init_kwargs = {
            "namespace": namespace,
            "global_config": global_config,
            "embedding_func": embedding_func,
        }
        if meta_fields:
            init_kwargs["meta_fields"] = meta_fields
        
        # Add backend-specific kwargs (e.g., HNSW parameters)
        if backend == "hnswlib" and "vector_db_storage_cls_kwargs" in global_config:
            init_kwargs.update(global_config["vector_db_storage_cls_kwargs"])
        
        init_kwargs.update(kwargs)
        
        # Get the backend class through the loader
        backend_class = cls._vector_backends[backend]()
        return backend_class(**init_kwargs)
    
    @classmethod
    def create_graph_storage(
        cls,
        backend: str,
        namespace: str,
        global_config: dict,
        **kwargs
    ) -> BaseGraphStorage:
        """Create a graph storage instance.
        
        Args:
            backend: Backend name
            namespace: Storage namespace
            global_config: Global configuration dict
            **kwargs: Additional backend-specific parameters
            
        Returns:
            Initialized graph storage instance
            
        Raises:
            ValueError: If backend not registered
        """
        if backend not in cls._graph_backends:
            # Try to register backends if not already done
            _register_backends()
            if backend not in cls._graph_backends:
                raise ValueError(f"Unknown graph backend: {backend}. Available: {list(cls._graph_backends.keys())}")
        
        # Get the backend class through the loader
        backend_class = cls._graph_backends[backend]()
        return backend_class(
            namespace=namespace,
            global_config=global_config,
            **kwargs
        )
    
    @classmethod
    def create_kv_storage(
        cls,
        backend: str,
        namespace: str,
        global_config: dict,
        **kwargs
    ) -> BaseKVStorage:
        """Create a KV storage instance.
        
        Args:
            backend: Backend name
            namespace: Storage namespace
            global_config: Global configuration dict
            **kwargs: Additional backend-specific parameters
            
        Returns:
            Initialized KV storage instance
            
        Raises:
            ValueError: If backend not registered
        """
        if backend not in cls._kv_backends:
            # Try to register backends if not already done
            _register_backends()
            if backend not in cls._kv_backends:
                raise ValueError(f"Unknown KV backend: {backend}. Available: {list(cls._kv_backends.keys())}")
        
        # Get the backend class through the loader
        backend_class = cls._kv_backends[backend]()
        return backend_class(
            namespace=namespace,
            global_config=global_config,
            **kwargs
        )


def _get_hnswlib_storage():
    """Lazy loader for HNSW storage."""
    from .vdb_hnswlib import HNSWVectorStorage
    return HNSWVectorStorage


def _get_nano_storage():
    """Lazy loader for NanoVectorDB storage."""
    from .vdb_nanovectordb import NanoVectorDBStorage
    return NanoVectorDBStorage


def _get_networkx_storage():
    """Lazy loader for NetworkX storage."""
    from .gdb_networkx import NetworkXStorage
    return NetworkXStorage


def _get_neo4j_storage():
    """Lazy loader for Neo4j storage."""
    from .gdb_neo4j import Neo4jStorage
    return Neo4jStorage


def _get_json_storage():
    """Lazy loader for JSON KV storage."""
    from .kv_json import JsonKVStorage
    return JsonKVStorage


def _get_qdrant_storage():
    """Lazy loader for Qdrant storage."""
    from .vdb_qdrant import QdrantVectorStorage
    return QdrantVectorStorage


def _register_backends():
    """Register built-in backends with lazy loaders. Called when factory is first used."""
    # Register vector backends if not already registered
    if not StorageFactory._vector_backends:
        StorageFactory.register_vector("hnswlib", _get_hnswlib_storage)
        StorageFactory.register_vector("nano", _get_nano_storage)
        StorageFactory.register_vector("qdrant", _get_qdrant_storage)
    
    # Register graph backends if not already registered
    if not StorageFactory._graph_backends:
        StorageFactory.register_graph("networkx", _get_networkx_storage)
        # Note: Neo4j is not in ALLOWED_GRAPH by default, would need to be added
    
    # Register KV backends if not already registered
    if not StorageFactory._kv_backends:
        StorageFactory.register_kv("json", _get_json_storage)