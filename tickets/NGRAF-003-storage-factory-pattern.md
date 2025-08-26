# NGRAF-003: Implement Storage Factory Pattern

## Summary
Create a factory pattern for vector, graph, and KV storage to centralize creation logic and reduce conditionals in GraphRAG class.

## Context
This ticket follows NGRAF-002 which implemented clean configuration management. The factory pattern will work with the existing StorageConfig and maintain the current backend restrictions.

## Post-NGRAF-002 Validity Assessment

### Initial Analysis
After NGRAF-002 implementation, there were concerns about:
- **Partial overlap**: Helper methods already provide some abstraction
- **Backend restrictions**: NGRAF-002 deliberately limited to implemented backends only
- **Over-engineering risk**: Only 2 vector, 1 graph, 1 KV backend currently

However, the factory pattern still provides value by centralizing creation logic and reducing GraphRAG class responsibilities.

### Expert Review Findings
The expert validated the factory pattern as a good next step with these key points:

1. **Constructor Contracts Must Match** ✅
   - Current storages require: `namespace`, `global_config`, and for vectors: `embedding_func`, `meta_fields`
   - Factory API must include all these parameters

2. **Config Shape Alignment Required** ✅
   - Add `vector_db_storage_cls_kwargs` to `GraphRAGConfig.to_dict()` for HNSW parameters
   - Map StorageConfig's `hnsw_*` fields to storage kwargs

3. **Maintain Backend Validation** ✅
   - Keep restrictions: vector={nano, hnswlib}, graph={networkx}, kv={json}
   - Don't broaden backends without updating validation

4. **Complete Implementation Needed** ✅
   - Include all three storage types (vector, graph, KV) for consistency
   - Ensure graph factory has same level of support as vector

5. **Lazy Registration Important** ✅
   - Avoid heavy imports at module load time
   - Use lazy registration pattern shown in solution

### Decision: Proceed with Adjusted Implementation
The factory pattern will:
- Reduce conditionals in GraphRAG class
- Centralize storage creation logic
- Maintain current backend restrictions
- Preserve all existing contracts and validation

## Problem
- Storage initialization logic scattered across helper methods (_get_vector_storage, _get_graph_storage, _get_kv_storage)
- Adding new storage backends requires modifying GraphRAG class
- Backend-specific initialization parameters handled in GraphRAG
- No centralized registry for available backends

## Technical Solution

```python
# nano_graphrag/_storage/factory.py
from typing import Type, Dict, Any, Optional, Set
from nano_graphrag.base import BaseVectorStorage, BaseGraphStorage, BaseKVStorage

class StorageFactory:
    _vector_backends: Dict[str, Type[BaseVectorStorage]] = {}
    _graph_backends: Dict[str, Type[BaseGraphStorage]] = {}
    _kv_backends: Dict[str, Type[BaseKVStorage]] = {}
    
    # Maintain current restrictions from StorageConfig
    ALLOWED_VECTOR = {"nano", "hnswlib"}
    ALLOWED_GRAPH = {"networkx"}
    ALLOWED_KV = {"json"}
    
    @classmethod
    def register_vector(cls, name: str, backend_class: Type[BaseVectorStorage]) -> None:
        if name not in cls.ALLOWED_VECTOR:
            raise ValueError(f"Backend {name} not in allowed vector backends: {cls.ALLOWED_VECTOR}")
        cls._vector_backends[name] = backend_class
    
    @classmethod
    def register_graph(cls, name: str, backend_class: Type[BaseGraphStorage]) -> None:
        if name not in cls.ALLOWED_GRAPH:
            raise ValueError(f"Backend {name} not in allowed graph backends: {cls.ALLOWED_GRAPH}")
        cls._graph_backends[name] = backend_class
    
    @classmethod
    def register_kv(cls, name: str, backend_class: Type[BaseKVStorage]) -> None:
        if name not in cls.ALLOWED_KV:
            raise ValueError(f"Backend {name} not in allowed KV backends: {cls.ALLOWED_KV}")
        cls._kv_backends[name] = backend_class
    
    @classmethod
    def create_vector_storage(
        cls, 
        backend: str,
        namespace: str,
        global_config: dict,
        embedding_func: callable,
        meta_fields: Optional[Set[str]] = None,
        **kwargs
    ) -> BaseVectorStorage:
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
        if backend not in cls._kv_backends:
            raise ValueError(f"Unknown KV backend: {backend}. Available: {list(cls._kv_backends.keys())}")
        
        return cls._kv_backends[backend](
            namespace=namespace,
            global_config=global_config,
            **kwargs
        )

# Lazy registration to avoid heavy imports at module load
def _register_backends():
    """Register built-in backends. Called when factory is first used."""
    if not StorageFactory._vector_backends:
        from nano_graphrag._storage import HNSWVectorStorage, NanoVectorDBStorage
        StorageFactory.register_vector("hnswlib", HNSWVectorStorage)
        StorageFactory.register_vector("nano", NanoVectorDBStorage)
    
    if not StorageFactory._graph_backends:
        from nano_graphrag._storage import NetworkXStorage
        StorageFactory.register_graph("networkx", NetworkXStorage)
    
    if not StorageFactory._kv_backends:
        from nano_graphrag._storage import JsonKVStorage
        StorageFactory.register_kv("json", JsonKVStorage)
```

## Code Changes

### New Files
- `nano_graphrag/_storage/factory.py` - Storage factory with registration and validation
- `nano_graphrag/_storage/__init__.py` - Export factory alongside existing backends

### Modified Files

#### `nano_graphrag/graphrag.py` - Replace helper methods with factory calls:
```python
# Before (current NGRAF-002 implementation)
def _get_vector_storage(self, namespace: str, global_config: dict, meta_fields: Optional[set] = None) -> BaseVectorStorage:
    kwargs = {
        "namespace": namespace,
        "global_config": global_config,
        "embedding_func": self.embedding_func,
    }
    if meta_fields:
        kwargs["meta_fields"] = meta_fields
        
    if self.config.storage.vector_backend == "nano":
        return NanoVectorDBStorage(**kwargs)
    elif self.config.storage.vector_backend == "hnswlib":
        from ._storage import HNSWVectorStorage
        return HNSWVectorStorage(**kwargs)
    else:
        raise ValueError(f"Unknown vector backend: {self.config.storage.vector_backend}")

# After (using factory)
from ._storage.factory import StorageFactory, _register_backends

def _init_storage(self):
    _register_backends()  # Ensure backends are registered
    global_config = self.config.to_dict()
    
    # Vector storage
    if self.config.query.enable_local:
        self.entities_vdb = StorageFactory.create_vector_storage(
            backend=self.config.storage.vector_backend,
            namespace="entities",
            global_config=global_config,
            embedding_func=self.embedding_func,
            meta_fields={"entity_name", "entity_type"}  # Fix metadata consistency
        )
    
    if self.config.query.enable_naive_rag:
        self.chunks_vdb = StorageFactory.create_vector_storage(
            backend=self.config.storage.vector_backend,
            namespace="chunks",
            global_config=global_config,
            embedding_func=self.embedding_func,
            meta_fields={"doc_id"}  # Fix metadata consistency
        )
    
    # Graph storage
    self.chunk_entity_relation_graph = StorageFactory.create_graph_storage(
        backend=self.config.storage.graph_backend,
        namespace="chunk_entity_relation",
        global_config=global_config
    )
    
    # KV storage
    self.full_docs = StorageFactory.create_kv_storage(
        backend=self.config.storage.kv_backend,
        namespace="full_docs",
        global_config=global_config
    )
    # ... repeat for other KV stores
```

#### `nano_graphrag/config.py` - Add vector_db_storage_cls_kwargs to to_dict():
```python
def to_dict(self) -> dict:
    """Convert config to dictionary for compatibility."""
    config_dict = {
        # ... existing fields ...
        'vector_db_storage_cls_kwargs': {
            'ef_construction': self.storage.hnsw_ef_construction,
            'ef_search': self.storage.hnsw_ef_search,
            'M': self.storage.hnsw_m,
            'max_elements': self.storage.hnsw_max_elements,
        } if self.storage.vector_backend == "hnswlib" else {},
        # ... rest of fields ...
    }
    return config_dict
```

## Definition of Done

### Unit Tests Required
```python
# tests/storage/test_factory.py
import pytest
from unittest.mock import Mock, MagicMock
from nano_graphrag.storage.factory import StorageFactory
from nano_graphrag.base import BaseVectorStorage

class TestStorageFactory:
    def test_register_vector_backend(self):
        """Verify backend registration works"""
        mock_backend = Mock(spec=BaseVectorStorage)
        StorageFactory.register_vector("test", mock_backend)
        assert "test" in StorageFactory._vector_backends
        assert StorageFactory._vector_backends["test"] == mock_backend
    
    def test_create_vector_storage(self):
        """Verify factory creates correct storage instance"""
        mock_backend = MagicMock(spec=BaseVectorStorage)
        StorageFactory.register_vector("mock", mock_backend)
        
        embedding_func = Mock()
        storage = StorageFactory.create_vector_storage(
            backend="mock",
            namespace="test",
            embedding_func=embedding_func,
            custom_param="value"
        )
        
        mock_backend.assert_called_once_with(
            namespace="test",
            embedding_func=embedding_func,
            custom_param="value"
        )
    
    def test_unknown_backend_raises(self):
        """Verify unknown backend raises ValueError"""
        with pytest.raises(ValueError, match="Unknown vector backend: invalid"):
            StorageFactory.create_vector_storage(
                backend="invalid",
                namespace="test",
                embedding_func=Mock()
            )
    
    def test_hnsw_backend_initialization(self):
        """Verify HNSW backend initializes with correct params"""
        from nano_graphrag._storage import HNSWVectorStorage
        
        storage = StorageFactory.create_vector_storage(
            backend="hnswlib",
            namespace="test",
            embedding_func=Mock(),
            max_elements=5000,
            ef_search=100
        )
        
        assert isinstance(storage, HNSWVectorStorage)
        assert storage.max_elements == 5000
        assert storage.ef_search == 100
    
    def test_backend_discovery(self):
        """Verify all backends are auto-registered"""
        assert "hnswlib" in StorageFactory._vector_backends
        assert "nano" in StorageFactory._vector_backends
        assert "networkx" in StorageFactory._graph_backends
```

### Additional Test Coverage
- Test graph backend registration and creation
- Test KV storage factory methods
- Test concurrent backend creation
- Test backend cleanup/disposal

## Feature Branch
`feature/ngraf-003-storage-factory`

## Pull Request Must Include
- Factory pattern for both vector and graph storage
- Auto-registration of existing backends
- Consistent initialization interface across backends
- Type hints for all factory methods
- All tests passing with >90% coverage