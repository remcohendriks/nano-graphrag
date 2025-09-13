"""Tests for the storage factory pattern."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from nano_graphrag._storage.factory import StorageFactory, _register_backends
from nano_graphrag.base import BaseVectorStorage, BaseGraphStorage, BaseKVStorage


class TestStorageFactory:
    """Test suite for StorageFactory."""
    
    def setup_method(self):
        """Reset factory state before each test."""
        StorageFactory._vector_backends = {}
        StorageFactory._graph_backends = {}
        StorageFactory._kv_backends = {}
    
    def test_register_vector_backend(self):
        """Verify vector backend registration works."""
        mock_backend = Mock(spec=BaseVectorStorage)
        
        # Should register allowed backend
        StorageFactory.register_vector("nano", mock_backend)
        assert "nano" in StorageFactory._vector_backends
        assert StorageFactory._vector_backends["nano"] == mock_backend
    
    def test_register_vector_backend_not_allowed(self):
        """Verify registration fails for non-allowed vector backends."""
        mock_backend = Mock(spec=BaseVectorStorage)
        
        with pytest.raises(ValueError, match="Backend invalid not in allowed vector backends"):
            StorageFactory.register_vector("invalid", mock_backend)
    
    def test_register_graph_backend(self):
        """Verify graph backend registration works."""
        mock_backend = Mock(spec=BaseGraphStorage)
        
        # Should register allowed backend
        StorageFactory.register_graph("networkx", mock_backend)
        assert "networkx" in StorageFactory._graph_backends
        assert StorageFactory._graph_backends["networkx"] == mock_backend
    
    def test_register_graph_backend_not_allowed(self):
        """Verify registration fails for non-allowed graph backends."""
        mock_backend = Mock(spec=BaseGraphStorage)
        
        with pytest.raises(ValueError, match="Backend invalid not in allowed graph backends"):
            StorageFactory.register_graph("invalid", mock_backend)
    
    def test_register_kv_backend(self):
        """Verify KV backend registration works."""
        mock_backend = Mock(spec=BaseKVStorage)
        
        # Should register allowed backend
        StorageFactory.register_kv("json", mock_backend)
        assert "json" in StorageFactory._kv_backends
        assert StorageFactory._kv_backends["json"] == mock_backend
    
    def test_register_kv_backend_not_allowed(self):
        """Verify registration fails for non-allowed KV backends."""
        mock_backend = Mock(spec=BaseKVStorage)
        
        with pytest.raises(ValueError, match="Backend invalid not in allowed KV backends"):
            StorageFactory.register_kv("invalid", mock_backend)
    
    def test_create_vector_storage(self):
        """Verify factory creates correct vector storage instance."""
        mock_class = MagicMock()
        mock_instance = Mock()
        mock_class.return_value = mock_instance
        mock_loader = Mock(return_value=mock_class)
        StorageFactory.register_vector("nano", mock_loader)

        embedding_func = Mock()
        global_config = {"working_dir": "/tmp"}

        storage = StorageFactory.create_vector_storage(
            backend="nano",
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func,
            custom_param="value"
        )

        assert storage == mock_instance
        mock_loader.assert_called_once_with()
        mock_class.assert_called_once_with(
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func,
            custom_param="value"
        )
    
    def test_create_vector_storage_with_meta_fields(self):
        """Verify vector storage creation with meta_fields."""
        mock_class = MagicMock()
        mock_instance = Mock()
        mock_class.return_value = mock_instance
        mock_loader = Mock(return_value=mock_class)
        StorageFactory.register_vector("nano", mock_loader)

        embedding_func = Mock()
        global_config = {"working_dir": "/tmp"}
        meta_fields = {"entity_name", "entity_type"}

        storage = StorageFactory.create_vector_storage(
            backend="nano",
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func,
            meta_fields=meta_fields
        )

        assert storage == mock_instance
        mock_loader.assert_called_once_with()
        mock_class.assert_called_once_with(
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func,
            meta_fields=meta_fields
        )
    
    def test_create_vector_storage_hnsw_kwargs(self):
        """Verify HNSW backend receives vector_db_storage_cls_kwargs."""
        mock_class = MagicMock()
        mock_instance = Mock()
        mock_class.return_value = mock_instance
        mock_loader = Mock(return_value=mock_class)
        StorageFactory.register_vector("hnswlib", mock_loader)

        embedding_func = Mock()
        global_config = {
            "working_dir": "/tmp",
            "vector_db_storage_cls_kwargs": {
                "ef_construction": 200,
                "ef_search": 100,
                "M": 32,
                "max_elements": 2000000
            }
        }

        storage = StorageFactory.create_vector_storage(
            backend="hnswlib",
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func
        )

        assert storage == mock_instance
        mock_loader.assert_called_once_with()
        mock_class.assert_called_once_with(
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func,
            ef_construction=200,
            ef_search=100,
            M=32,
            max_elements=2000000
        )
    
    def test_create_vector_storage_unknown_backend(self):
        """Verify unknown vector backend raises ValueError."""
        with pytest.raises(ValueError, match="Unknown vector backend: invalid"):
            StorageFactory.create_vector_storage(
                backend="invalid",
                namespace="test",
                global_config={},
                embedding_func=Mock()
            )
    
    def test_create_graph_storage(self):
        """Verify factory creates correct graph storage instance."""
        mock_class = MagicMock()
        mock_instance = Mock()
        mock_class.return_value = mock_instance
        mock_loader = Mock(return_value=mock_class)
        StorageFactory.register_graph("networkx", mock_loader)

        global_config = {"working_dir": "/tmp"}

        storage = StorageFactory.create_graph_storage(
            backend="networkx",
            namespace="test",
            global_config=global_config,
            custom_param="value"
        )

        assert storage == mock_instance
        mock_loader.assert_called_once_with()
        mock_class.assert_called_once_with(
            namespace="test",
            global_config=global_config,
            custom_param="value"
        )
    
    def test_create_graph_storage_unknown_backend(self):
        """Verify unknown graph backend raises ValueError."""
        with pytest.raises(ValueError, match="Unknown graph backend: invalid"):
            StorageFactory.create_graph_storage(
                backend="invalid",
                namespace="test",
                global_config={}
            )
    
    def test_create_kv_storage(self):
        """Verify factory creates correct KV storage instance."""
        mock_class = MagicMock()
        mock_instance = Mock()
        mock_class.return_value = mock_instance
        mock_loader = Mock(return_value=mock_class)
        StorageFactory.register_kv("json", mock_loader)

        global_config = {"working_dir": "/tmp"}

        storage = StorageFactory.create_kv_storage(
            backend="json",
            namespace="test",
            global_config=global_config,
            custom_param="value"
        )

        assert storage == mock_instance
        mock_loader.assert_called_once_with()
        mock_class.assert_called_once_with(
            namespace="test",
            global_config=global_config,
            custom_param="value"
        )
    
    def test_create_kv_storage_unknown_backend(self):
        """Verify unknown KV backend raises ValueError."""
        with pytest.raises(ValueError, match="Unknown KV backend: invalid"):
            StorageFactory.create_kv_storage(
                backend="invalid",
                namespace="test",
                global_config={}
            )
    
    @patch('nano_graphrag._storage.factory.StorageFactory.register_vector')
    @patch('nano_graphrag._storage.factory.StorageFactory.register_graph')
    @patch('nano_graphrag._storage.factory.StorageFactory.register_kv')
    def test_register_backends_lazy_loading(self, mock_kv, mock_graph, mock_vector):
        """Verify lazy registration of built-in backends."""
        # First call should register backends
        _register_backends()
        
        assert mock_vector.call_count == 3  # nano, hnswlib, and qdrant
        assert mock_graph.call_count == 2   # networkx and neo4j
        assert mock_kv.call_count == 1      # json
        
        # Reset mocks
        mock_vector.reset_mock()
        mock_graph.reset_mock()
        mock_kv.reset_mock()
        
        # Set backends as already registered
        StorageFactory._vector_backends = {"nano": Mock(), "hnswlib": Mock(), "qdrant": Mock()}
        StorageFactory._graph_backends = {"networkx": Mock(), "neo4j": Mock()}
        StorageFactory._kv_backends = {"json": Mock()}
        
        # Second call should not re-register
        _register_backends()
        
        assert mock_vector.call_count == 0
        assert mock_graph.call_count == 0
        assert mock_kv.call_count == 0
    
    def test_auto_register_on_create(self):
        """Verify backends are auto-registered when creating storage."""
        # Don't manually register anything
        assert len(StorageFactory._vector_backends) == 0
        
        # Mock the imports inside _register_backends
        with patch('nano_graphrag._storage.NanoVectorDBStorage') as mock_nano:
            with patch('nano_graphrag._storage.HNSWVectorStorage') as mock_hnsw:
                # Try to create storage - should auto-register
                try:
                    StorageFactory.create_vector_storage(
                        backend="nano",
                        namespace="test",
                        global_config={"working_dir": "/tmp"},
                        embedding_func=Mock()
                    )
                except:
                    pass  # We're just testing registration, not actual creation
                
                # Should have registered backends
                assert "nano" in StorageFactory._vector_backends
                assert "hnswlib" in StorageFactory._vector_backends
                assert "qdrant" in StorageFactory._vector_backends


class TestStorageFactoryIntegration:
    """Integration tests with real storage classes."""
    
    def setup_method(self):
        """Reset factory state before each test."""
        StorageFactory._vector_backends = {}
        StorageFactory._graph_backends = {}
        StorageFactory._kv_backends = {}
    
    def test_hnsw_backend_initialization(self):
        """Verify HNSW backend initializes with correct params."""
        # This test requires the actual storage classes to be available
        try:
            from nano_graphrag._storage import HNSWVectorStorage
        except ImportError:
            pytest.skip("HNSWVectorStorage not available")
        
        # Register backends
        _register_backends()
        
        # Create mock embedding function with required attributes
        embedding_func = Mock()
        embedding_func.embedding_dim = 1536
        
        global_config = {
            "working_dir": "/tmp",
            "embedding_batch_num": 100,  # Required by HNSWVectorStorage
            "vector_db_storage_cls_kwargs": {
                "ef_construction": 200,
                "ef_search": 100,
                "M": 32,
                "max_elements": 5000
            }
        }
        
        storage = StorageFactory.create_vector_storage(
            backend="hnswlib",
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func
        )
        
        assert isinstance(storage, HNSWVectorStorage)
        assert storage.ef_construction == 200
        assert storage.ef_search == 100
        assert storage.M == 32
        assert storage.max_elements == 5000
    
    def test_nano_backend_initialization(self):
        """Verify Nano backend initializes correctly."""
        try:
            from nano_graphrag._storage import NanoVectorDBStorage
        except ImportError:
            pytest.skip("NanoVectorDBStorage not available")
        
        # Register backends
        _register_backends()
        
        embedding_func = Mock()
        embedding_func.embedding_dim = 1536  # Required by NanoVectorDBStorage
        global_config = {
            "working_dir": "/tmp",
            "embedding_batch_num": 100  # Required by NanoVectorDBStorage
        }
        
        storage = StorageFactory.create_vector_storage(
            backend="nano",
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func,
            meta_fields={"doc_id", "entity_name"}
        )
        
        assert isinstance(storage, NanoVectorDBStorage)
        assert storage.namespace == "test"
    
    def test_networkx_backend_initialization(self):
        """Verify NetworkX backend initializes correctly."""
        try:
            from nano_graphrag._storage import NetworkXStorage
        except ImportError:
            pytest.skip("NetworkXStorage not available")
        
        # Register backends
        _register_backends()
        
        global_config = {"working_dir": "/tmp"}
        
        storage = StorageFactory.create_graph_storage(
            backend="networkx",
            namespace="test_graph",
            global_config=global_config
        )
        
        assert isinstance(storage, NetworkXStorage)
        assert storage.namespace == "test_graph"
    
    def test_json_kv_backend_initialization(self):
        """Verify JSON KV backend initializes correctly."""
        try:
            from nano_graphrag._storage import JsonKVStorage
        except ImportError:
            pytest.skip("JsonKVStorage not available")
        
        # Register backends
        _register_backends()
        
        global_config = {"working_dir": "/tmp"}
        
        storage = StorageFactory.create_kv_storage(
            backend="json",
            namespace="test_kv",
            global_config=global_config
        )
        
        assert isinstance(storage, JsonKVStorage)
        assert storage.namespace == "test_kv"