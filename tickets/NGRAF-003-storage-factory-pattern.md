# NGRAF-003: Implement Storage Factory Pattern

## Summary
Create a factory pattern for vector and graph storage to eliminate conditional logic and improve extensibility.

## Problem
- Storage initialization scattered with if/else conditions in GraphRAG.__post_init__
- Adding new storage backends requires modifying core GraphRAG class
- Storage parameters mixed with other configuration
- No clear interface for storage backends

## Technical Solution

```python
# nano_graphrag/storage/factory.py
from typing import Type, Dict, Any
from nano_graphrag.base import BaseVectorStorage, BaseGraphStorage

class StorageFactory:
    _vector_backends: Dict[str, Type[BaseVectorStorage]] = {}
    _graph_backends: Dict[str, Type[BaseGraphStorage]] = {}
    
    @classmethod
    def register_vector(cls, name: str, backend_class: Type[BaseVectorStorage]) -> None:
        cls._vector_backends[name] = backend_class
    
    @classmethod
    def create_vector_storage(
        cls, 
        backend: str,
        namespace: str,
        embedding_func: callable,
        **kwargs
    ) -> BaseVectorStorage:
        if backend not in cls._vector_backends:
            raise ValueError(f"Unknown vector backend: {backend}")
        return cls._vector_backends[backend](
            namespace=namespace,
            embedding_func=embedding_func,
            **kwargs
        )

# Auto-register existing backends
from nano_graphrag._storage import HNSWVectorStorage, NanoVectorDBStorage
StorageFactory.register_vector("hnswlib", HNSWVectorStorage)
StorageFactory.register_vector("nano", NanoVectorDBStorage)
```

## Code Changes

### New Files
- `nano_graphrag/storage/factory.py` - Storage factory with registration
- `nano_graphrag/storage/__init__.py` - Export factory and backends

### Modified Files
- `nano_graphrag/graphrag.py:189-211` - Replace storage initialization:
  ```python
  # Before
  self.entities_vdb = (
      self.vector_db_storage_cls(
          namespace="entities",
          global_config=asdict(self),
          embedding_func=self.embedding_func,
      )
      if self.enable_local
      else None
  )
  
  # After
  self.entities_vdb = StorageFactory.create_vector_storage(
      backend=self.config.storage.vector_backend,
      namespace="entities",
      embedding_func=self.embedding_func,
      **self.config.storage.vector_kwargs
  ) if self.config.enable_local else None
  ```

- `nano_graphrag/_storage/vdb_hnswlib.py` - Ensure consistent initialization interface
- `nano_graphrag/_storage/gdb_networkx.py` - Ensure consistent initialization interface

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