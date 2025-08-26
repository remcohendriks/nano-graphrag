"""Storage factory for centralized backend creation."""

from typing import Type, Dict, Optional, Set, Any
from nano_graphrag.base import BaseVectorStorage, BaseGraphStorage, BaseKVStorage


class StorageFactory:
    """Factory for creating storage backends with validation and registration."""
    
    _vector_backends: Dict[str, Type[BaseVectorStorage]] = {}
    _graph_backends: Dict[str, Type[BaseGraphStorage]] = {}
    _kv_backends: Dict[str, Type[BaseKVStorage]] = {}
    
    # Maintain current restrictions from StorageConfig
    ALLOWED_VECTOR = {"nano", "hnswlib"}
    ALLOWED_GRAPH = {"networkx"}
    ALLOWED_KV = {"json"}
    
    @classmethod
    def register_vector(cls, name: str, backend_class: Type[BaseVectorStorage]) -> None:
        """Register a vector storage backend.
        
        Args:
            name: Backend name (must be in ALLOWED_VECTOR)
            backend_class: Vector storage class
            
        Raises:
            ValueError: If backend name not in allowed list
        """
        if name not in cls.ALLOWED_VECTOR:
            raise ValueError(f"Backend {name} not in allowed vector backends: {cls.ALLOWED_VECTOR}")
        cls._vector_backends[name] = backend_class
    
    @classmethod
    def register_graph(cls, name: str, backend_class: Type[BaseGraphStorage]) -> None:
        """Register a graph storage backend.
        
        Args:
            name: Backend name (must be in ALLOWED_GRAPH)
            backend_class: Graph storage class
            
        Raises:
            ValueError: If backend name not in allowed list
        """
        if name not in cls.ALLOWED_GRAPH:
            raise ValueError(f"Backend {name} not in allowed graph backends: {cls.ALLOWED_GRAPH}")
        cls._graph_backends[name] = backend_class
    
    @classmethod
    def register_kv(cls, name: str, backend_class: Type[BaseKVStorage]) -> None:
        """Register a KV storage backend.
        
        Args:
            name: Backend name (must be in ALLOWED_KV)
            backend_class: KV storage class
            
        Raises:
            ValueError: If backend name not in allowed list
        """
        if name not in cls.ALLOWED_KV:
            raise ValueError(f"Backend {name} not in allowed KV backends: {cls.ALLOWED_KV}")
        cls._kv_backends[name] = backend_class
    
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
        return cls._vector_backends[backend](**init_kwargs)
    
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
        
        return cls._graph_backends[backend](
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
        
        return cls._kv_backends[backend](
            namespace=namespace,
            global_config=global_config,
            **kwargs
        )


def _register_backends():
    """Register built-in backends. Called when factory is first used."""
    # Register vector backends if not already registered
    if not StorageFactory._vector_backends:
        from nano_graphrag._storage import HNSWVectorStorage, NanoVectorDBStorage
        StorageFactory.register_vector("hnswlib", HNSWVectorStorage)
        StorageFactory.register_vector("nano", NanoVectorDBStorage)
    
    # Register graph backends if not already registered
    if not StorageFactory._graph_backends:
        from nano_graphrag._storage import NetworkXStorage
        StorageFactory.register_graph("networkx", NetworkXStorage)
    
    # Register KV backends if not already registered
    if not StorageFactory._kv_backends:
        from nano_graphrag._storage import JsonKVStorage
        StorageFactory.register_kv("json", JsonKVStorage)