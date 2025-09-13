# NGRAF-013: Unified Storage Testing Framework

## Overview
Create a standardized testing framework that ensures all storage backends (vector, graph, KV) conform to their interfaces through contract-based testing and validates examples automatically.

## Current State
- Storage tests are scattered across different files with inconsistent patterns
- No standard way to validate new storage implementations
- Examples in `examples/` directory not validated automatically
- Each storage has its own test style and coverage levels
- No contract-based testing to ensure interface compliance

## Proposed Implementation

### Phase 1: Abstract Test Suites

#### Create `tests/storage/base/__init__.py`
```python
"""Base test suites for all storage types."""

from .vector_suite import BaseVectorStorageTestSuite, VectorStorageContract
from .graph_suite import BaseGraphStorageTestSuite, GraphStorageContract  
from .kv_suite import BaseKVStorageTestSuite, KVStorageContract
from .compatibility import StorageCompatibilityTestSuite
from .performance import StoragePerformanceTestSuite

__all__ = [
    "BaseVectorStorageTestSuite",
    "BaseGraphStorageTestSuite", 
    "BaseKVStorageTestSuite",
    "VectorStorageContract",
    "GraphStorageContract",
    "KVStorageContract",
    "StorageCompatibilityTestSuite",
    "StoragePerformanceTestSuite"
]
```

#### Create `tests/storage/base/vector_suite.py`
```python
"""Base test suite for vector storage implementations."""

import pytest
import asyncio
import numpy as np
from abc import ABC, abstractmethod
from typing import Any, List, Dict, Optional
from dataclasses import dataclass
import time

@dataclass
class VectorStorageContract:
    """Contract that all vector storages must fulfill."""
    
    supports_metadata: bool = True
    supports_filtering: bool = True
    supports_batch_upsert: bool = True
    supports_async: bool = True
    supports_persistence: bool = True
    max_vector_dim: Optional[int] = None
    max_vectors: Optional[int] = None
    distance_metrics: List[str] = None
    
    def __post_init__(self):
        if self.distance_metrics is None:
            self.distance_metrics = ["cosine"]

class BaseVectorStorageTestSuite(ABC):
    """Abstract test suite all vector storage implementations must pass."""
    
    @pytest.fixture
    @abstractmethod
    async def storage(self) -> Any:
        """Provide storage instance for testing."""
        pass
    
    @pytest.fixture
    @abstractmethod
    def contract(self) -> VectorStorageContract:
        """Define storage capabilities contract."""
        pass
    
    @pytest.fixture
    def mock_embedding_func(self):
        """Standard mock embedding function."""
        class MockEmbedding:
            embedding_dim = 128
            
            async def __call__(self, texts: List[str]) -> List[List[float]]:
                # Deterministic embeddings based on text hash
                embeddings = []
                for text in texts:
                    np.random.seed(hash(text) % 2**32)
                    embeddings.append(np.random.rand(self.embedding_dim).tolist())
                return embeddings
        
        return MockEmbedding()
    
    # Core functionality tests
    
    @pytest.mark.asyncio
    async def test_upsert_single(self, storage, mock_embedding_func):
        """Test single vector upsert."""
        data = {
            "content1": {
                "embedding": await mock_embedding_func(["content1"])[0],
                "metadata": {"type": "test"}
            }
        }
        
        await storage.upsert(data)
        
        # Verify via query
        results = await storage.query("content1", top_k=1)
        assert len(results) > 0
        assert "content" in results[0]
    
    @pytest.mark.asyncio
    async def test_upsert_batch(self, storage, contract, mock_embedding_func):
        """Test batch vector upsert."""
        if not contract.supports_batch_upsert:
            pytest.skip("Storage doesn't support batch upsert")
        
        # Create batch data
        batch_size = 100
        data = {}
        for i in range(batch_size):
            content = f"content_{i}"
            data[content] = {
                "embedding": (await mock_embedding_func([content]))[0],
                "metadata": {"index": i, "type": "batch"}
            }
        
        start = time.time()
        await storage.upsert(data)
        duration = time.time() - start
        
        # Verify all inserted
        sample_results = await storage.query("content_50", top_k=10)
        assert len(sample_results) > 0
        
        # Performance assertion
        assert duration < 10, f"Batch insert too slow: {duration}s for {batch_size} items"
    
    @pytest.mark.asyncio
    async def test_query_accuracy(self, storage, mock_embedding_func):
        """Test query returns relevant results."""
        # Insert test data with known similarity
        test_data = {
            "apple fruit": {
                "embedding": (await mock_embedding_func(["apple fruit"]))[0],
                "metadata": {"category": "fruit"}
            },
            "banana fruit": {
                "embedding": (await mock_embedding_func(["banana fruit"]))[0],
                "metadata": {"category": "fruit"}
            },
            "car vehicle": {
                "embedding": (await mock_embedding_func(["car vehicle"]))[0],
                "metadata": {"category": "vehicle"}
            }
        }
        
        await storage.upsert(test_data)
        
        # Query for fruit
        results = await storage.query("orange fruit", top_k=2)
        
        # Fruits should rank higher
        assert len(results) >= 2
        fruit_results = [r for r in results if r.get("metadata", {}).get("category") == "fruit"]
        assert len(fruit_results) >= 1
    
    @pytest.mark.asyncio
    async def test_metadata_filtering(self, storage, contract, mock_embedding_func):
        """Test metadata filtering if supported."""
        if not contract.supports_filtering:
            pytest.skip("Storage doesn't support filtering")
        
        # Insert data with metadata
        data = {
            f"content_{i}": {
                "embedding": (await mock_embedding_func([f"content_{i}"]))[0],
                "metadata": {
                    "type": "even" if i % 2 == 0 else "odd",
                    "value": i
                }
            }
            for i in range(10)
        }
        
        await storage.upsert(data)
        
        # Query with filter
        if hasattr(storage, 'query_with_filter'):
            results = await storage.query_with_filter(
                "test",
                top_k=5,
                filter_dict={"type": "even"}
            )
            
            # All results should be even
            for result in results:
                assert result.get("metadata", {}).get("type") == "even"
    
    @pytest.mark.asyncio
    async def test_persistence(self, storage, contract, tmp_path):
        """Test data persistence across restarts."""
        if not contract.supports_persistence:
            pytest.skip("Storage doesn't support persistence")
        
        # Insert data
        test_data = {
            "persistent_content": {
                "embedding": [0.5] * 128,
                "metadata": {"persistent": True}
            }
        }
        
        await storage.upsert(test_data)
        
        # Simulate restart by creating new instance
        if hasattr(storage, 'close'):
            await storage.close()
        
        # Recreate storage with same config
        storage_class = type(storage)
        new_storage = storage_class(
            namespace=storage.namespace,
            global_config=storage.global_config,
            embedding_func=storage.embedding_func
        )
        
        # Query should still find data
        results = await new_storage.query("persistent_content", top_k=1)
        assert len(results) > 0
        assert results[0].get("metadata", {}).get("persistent") == True
    
    @pytest.mark.asyncio
    async def test_empty_query(self, storage):
        """Test querying empty storage."""
        results = await storage.query("nonexistent", top_k=10)
        assert isinstance(results, list)
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_duplicate_upsert(self, storage, mock_embedding_func):
        """Test upserting duplicate content."""
        content = "duplicate_content"
        embedding = (await mock_embedding_func([content]))[0]
        
        # First insert
        await storage.upsert({
            content: {"embedding": embedding, "version": 1}
        })
        
        # Second insert (update)
        await storage.upsert({
            content: {"embedding": embedding, "version": 2}
        })
        
        # Should have updated version
        results = await storage.query(content, top_k=1)
        assert len(results) == 1
        assert results[0].get("version") == 2
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, storage, mock_embedding_func):
        """Test concurrent upserts and queries."""
        async def upsert_task(index):
            data = {
                f"concurrent_{index}": {
                    "embedding": (await mock_embedding_func([f"concurrent_{index}"]))[0],
                    "index": index
                }
            }
            await storage.upsert(data)
        
        async def query_task():
            return await storage.query("test", top_k=5)
        
        # Run concurrent operations
        tasks = []
        for i in range(10):
            tasks.append(upsert_task(i))
            if i % 2 == 0:
                tasks.append(query_task())
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check no exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Concurrent ops failed: {exceptions}"
    
    @pytest.mark.asyncio
    async def test_graphrag_compatibility(self, storage):
        """Test GraphRAG-specific requirements."""
        # Test return format matches GraphRAG expectations
        test_data = {
            "entity_content": {
                "embedding": [0.1] * 128,
                "entity_name": "TestEntity",
                "entity_type": "Person",
                "description": "Test description"
            }
        }
        
        await storage.upsert(test_data)
        results = await storage.query("test", top_k=1)
        
        # Verify GraphRAG fields present
        assert len(results) > 0
        result = results[0]
        assert "content" in result
        assert isinstance(result.get("distance") or result.get("score"), (int, float))
```

#### Create `tests/storage/base/graph_suite.py`
```python
"""Base test suite for graph storage implementations."""

import pytest
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple, Optional
from dataclasses import dataclass

@dataclass
class GraphStorageContract:
    """Contract that all graph storages must fulfill."""
    
    supports_properties: bool = True
    supports_multi_graph: bool = False
    supports_transactions: bool = True
    supports_clustering: bool = True
    clustering_algorithms: List[str] = None
    max_nodes: Optional[int] = None
    max_edges: Optional[int] = None
    
    def __post_init__(self):
        if self.clustering_algorithms is None:
            self.clustering_algorithms = ["leiden"]

class BaseGraphStorageTestSuite(ABC):
    """Abstract test suite all graph storage implementations must pass."""
    
    @pytest.fixture
    @abstractmethod
    async def storage(self) -> Any:
        """Provide storage instance for testing."""
        pass
    
    @pytest.fixture
    @abstractmethod
    def contract(self) -> GraphStorageContract:
        """Define storage capabilities contract."""
        pass
    
    @pytest.mark.asyncio
    async def test_node_operations(self, storage):
        """Test node CRUD operations."""
        # Create
        await storage.upsert_node("node1", {"type": "Person", "name": "Alice"})
        await storage.upsert_node("node2", {"type": "Person", "name": "Bob"})
        
        # Read
        node = await storage.get_node("node1")
        assert node is not None
        assert node.get("type") == "Person"
        assert node.get("name") == "Alice"
        
        # Update
        await storage.upsert_node("node1", {"type": "Person", "name": "Alice Updated"})
        node = await storage.get_node("node1")
        assert node.get("name") == "Alice Updated"
        
        # List
        nodes = await storage.get_nodes()
        assert len(nodes) >= 2
        node_ids = [n[0] for n in nodes]
        assert "node1" in node_ids
        assert "node2" in node_ids
    
    @pytest.mark.asyncio
    async def test_edge_operations(self, storage):
        """Test edge CRUD operations."""
        # Setup nodes
        await storage.upsert_node("source", {})
        await storage.upsert_node("target", {})
        
        # Create edge
        await storage.upsert_edge("source", "target", {"relation": "knows", "weight": 0.8})
        
        # Read edges
        edges = await storage.get_edges(source_id="source")
        assert len(edges) == 1
        assert edges[0][0] == "source"
        assert edges[0][1] == "target"
        assert edges[0][2]["relation"] == "knows"
        
        # Update edge
        await storage.upsert_edge("source", "target", {"relation": "knows", "weight": 0.9})
        edges = await storage.get_edges(source_id="source")
        assert edges[0][2]["weight"] == 0.9
    
    @pytest.mark.asyncio
    async def test_clustering(self, storage, contract):
        """Test graph clustering algorithms."""
        if not contract.supports_clustering:
            pytest.skip("Storage doesn't support clustering")
        
        # Create a simple graph
        for i in range(10):
            await storage.upsert_node(f"node_{i}", {"index": i})
        
        # Create two clusters
        for i in range(5):
            for j in range(i+1, 5):
                await storage.upsert_edge(f"node_{i}", f"node_{j}", {"cluster": 0})
        
        for i in range(5, 10):
            for j in range(i+1, 10):
                await storage.upsert_edge(f"node_{i}", f"node_{j}", {"cluster": 1})
        
        # Run clustering
        for algorithm in contract.clustering_algorithms:
            result = await storage.clustering(algorithm)
            
            assert "communities" in result
            communities = result["communities"]
            
            # Should detect two main communities
            unique_communities = set(communities.values())
            assert len(unique_communities) >= 2
    
    @pytest.mark.asyncio
    async def test_transaction_support(self, storage, contract):
        """Test transaction atomicity."""
        if not contract.supports_transactions:
            pytest.skip("Storage doesn't support transactions")
        
        # Test rollback on error
        try:
            async with storage.transaction() as tx:
                await storage.upsert_node("tx_node1", {"temp": True})
                await storage.upsert_node("tx_node2", {"temp": True})
                raise Exception("Simulated error")
        except:
            pass
        
        # Nodes should not exist
        node1 = await storage.get_node("tx_node1")
        node2 = await storage.get_node("tx_node2")
        assert node1 is None
        assert node2 is None
    
    @pytest.mark.asyncio
    async def test_concurrent_modifications(self, storage):
        """Test concurrent graph modifications."""
        async def modify_graph(index):
            node_id = f"concurrent_{index}"
            await storage.upsert_node(node_id, {"index": index})
            
            if index > 0:
                await storage.upsert_edge(
                    f"concurrent_{index-1}",
                    node_id,
                    {"order": index}
                )
        
        # Concurrent modifications
        tasks = [modify_graph(i) for i in range(20)]
        await asyncio.gather(*tasks)
        
        # Verify graph integrity
        nodes = await storage.get_nodes()
        assert len(nodes) == 20
        
        edges = await storage.get_edges()
        assert len(edges) == 19  # Linear chain
```

### Phase 2: KV Storage Test Suite

#### Create `tests/storage/base/kv_suite.py`
```python
"""Base test suite for key-value storage implementations."""

import pytest
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

@dataclass
class KVStorageContract:
    """Contract that all KV storages must fulfill."""

    supports_batch_ops: bool = True
    supports_persistence: bool = True
    supports_async: bool = True
    supports_namespace: bool = True
    max_key_length: Optional[int] = None
    max_value_size: Optional[int] = None

class BaseKVStorageTestSuite(ABC):
    """Abstract test suite all KV storage implementations must pass."""

    @pytest.fixture
    @abstractmethod
    async def storage(self) -> Any:
        """Provide storage instance for testing."""
        pass

    @pytest.fixture
    @abstractmethod
    def contract(self) -> KVStorageContract:
        """Define storage capabilities contract."""
        pass

    @pytest.mark.asyncio
    async def test_basic_operations(self, storage):
        """Test basic get/set operations."""
        # Set single item
        await storage.upsert({"key1": {"value": "data1", "metadata": "test"}})

        # Get single item
        result = await storage.get_by_id("key1")
        assert result is not None
        assert result["value"] == "data1"
        assert result["metadata"] == "test"

        # Get non-existent item
        result = await storage.get_by_id("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_batch_operations(self, storage, contract):
        """Test batch operations."""
        if not contract.supports_batch_ops:
            pytest.skip("Storage doesn't support batch operations")

        # Batch upsert
        batch_data = {
            f"key_{i}": {"value": f"data_{i}", "index": i}
            for i in range(100)
        }
        await storage.upsert(batch_data)

        # Batch get
        keys = [f"key_{i}" for i in range(50)]
        results = await storage.get_by_ids(keys)

        assert len(results) == 50
        for i, result in enumerate(results):
            assert result["value"] == f"data_{i}"
            assert result["index"] == i

    @pytest.mark.asyncio
    async def test_filter_keys(self, storage):
        """Test filtering existing keys."""
        # Insert some data
        await storage.upsert({
            "existing1": {"value": "data1"},
            "existing2": {"value": "data2"},
            "existing3": {"value": "data3"}
        })

        # Filter keys
        test_keys = ["existing1", "existing2", "new1", "new2"]
        new_keys = await storage.filter_keys(test_keys)

        assert "new1" in new_keys
        assert "new2" in new_keys
        assert "existing1" not in new_keys
        assert "existing2" not in new_keys

    @pytest.mark.asyncio
    async def test_all_keys(self, storage):
        """Test listing all keys."""
        # Insert test data
        test_data = {f"key_{i}": {"value": f"data_{i}"} for i in range(10)}
        await storage.upsert(test_data)

        # Get all keys
        all_keys = await storage.all_keys()

        for i in range(10):
            assert f"key_{i}" in all_keys

    @pytest.mark.asyncio
    async def test_persistence(self, storage, contract):
        """Test data persistence."""
        if not contract.supports_persistence:
            pytest.skip("Storage doesn't support persistence")

        # Insert data
        await storage.upsert({"persist_key": {"value": "persistent_data"}})

        # Trigger persistence
        if hasattr(storage, 'index_done_callback'):
            await storage.index_done_callback()

        # Verify data exists
        result = await storage.get_by_id("persist_key")
        assert result["value"] == "persistent_data"

    @pytest.mark.asyncio
    async def test_drop(self, storage):
        """Test dropping all data."""
        # Insert data
        await storage.upsert({f"key_{i}": {"value": f"data_{i}"} for i in range(10)})

        # Drop all data
        await storage.drop()

        # Verify empty
        all_keys = await storage.all_keys()
        assert len(all_keys) == 0

    @pytest.mark.asyncio
    async def test_concurrent_access(self, storage):
        """Test concurrent read/write operations."""
        async def write_task(index):
            await storage.upsert({f"concurrent_{index}": {"value": f"data_{index}"}})

        async def read_task(index):
            return await storage.get_by_id(f"concurrent_{index}")

        # Concurrent writes
        write_tasks = [write_task(i) for i in range(20)]
        await asyncio.gather(*write_tasks)

        # Concurrent reads
        read_tasks = [read_task(i) for i in range(20)]
        results = await asyncio.gather(*read_tasks)

        # Verify all successful
        for i, result in enumerate(results):
            if result is not None:  # May be None if read before write
                assert result["value"] == f"data_{i}"

    @pytest.mark.asyncio
    async def test_graphrag_namespaces(self, storage):
        """Test GraphRAG-specific namespace handling."""
        # Test standard namespaces
        namespaces = ["full_docs", "text_chunks", "community_reports", "llm_response_cache"]

        for namespace in namespaces:
            # Verify namespace is handled correctly
            assert storage.namespace in namespaces or storage.namespace == "test"
```

### Phase 3: Example Validation Framework

#### Create `tests/examples/test_examples.py`
```python
"""Validate all examples work with current codebase."""

import pytest
import sys
import subprocess
import importlib.util
from pathlib import Path
import asyncio

class TestExamples:
    """Test all examples in the examples directory."""
    
    @pytest.fixture
    def examples_dir(self):
        """Get examples directory."""
        return Path(__file__).parent.parent.parent / "examples"
    
    def get_example_files(self, examples_dir):
        """Get all Python example files."""
        return list(examples_dir.glob("*.py"))
    
    @pytest.mark.parametrize("example_file", get_example_files(Path("examples")))
    def test_example_imports(self, example_file):
        """Test that example can be imported without errors."""
        spec = importlib.util.spec_from_file_location(
            example_file.stem,
            example_file
        )
        
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            
            # Check for required dependencies
            try:
                spec.loader.exec_module(module)
            except ImportError as e:
                if "qdrant" in str(e) or "neo4j" in str(e):
                    pytest.skip(f"Optional dependency not installed: {e}")
                else:
                    raise
    
    @pytest.mark.integration
    def test_example_execution(self, example_file, tmp_path):
        """Test that example runs without errors."""
        # Skip examples that require external services
        skip_patterns = ["neo4j", "qdrant", "milvus"]
        if any(pattern in example_file.name for pattern in skip_patterns):
            pytest.skip("Requires external service")
        
        # Run example in subprocess with timeout
        env = os.environ.copy()
        env["WORKING_DIR"] = str(tmp_path)
        
        try:
            result = subprocess.run(
                [sys.executable, str(example_file)],
                env=env,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            assert result.returncode == 0, f"Example failed: {result.stderr}"
            
        except subprocess.TimeoutExpired:
            pytest.fail(f"Example timed out: {example_file.name}")
    
    def test_example_config_usage(self, examples_dir):
        """Verify examples use GraphRAGConfig pattern."""
        for example_file in self.get_example_files(examples_dir):
            content = example_file.read_text()
            
            # Check for deprecated patterns
            deprecated_patterns = [
                "vector_db_storage_cls=",
                "graph_storage_cls=",
                "addon_params="
            ]
            
            for pattern in deprecated_patterns:
                if pattern in content:
                    pytest.fail(
                        f"Example {example_file.name} uses deprecated pattern: {pattern}"
                    )
            
            # Verify uses GraphRAGConfig
            if "GraphRAG(" in content and "GraphRAGConfig" not in content:
                pytest.fail(
                    f"Example {example_file.name} doesn't use GraphRAGConfig"
                )
```

### Phase 3: Simple Test Runner

#### Create `tests/storage/run_storage_tests.py`
```python
"""Simple test runner for storage backend validation."""

import pytest
import sys
from pathlib import Path
from typing import List, Tuple

def get_available_backends() -> List[Tuple[str, str]]:
    """Detect which storage backends are available."""
    backends = []

    # Check vector storages
    try:
        import nano_vectordb
        backends.append(("vector", "nano"))
    except ImportError:
        pass

    try:
        import hnswlib
        backends.append(("vector", "hnswlib"))
    except ImportError:
        pass

    try:
        import qdrant_client
        backends.append(("vector", "qdrant"))
    except ImportError:
        pass

    # Check graph storages
    backends.append(("graph", "networkx"))  # Always available

    try:
        import neo4j
        backends.append(("graph", "neo4j"))
    except ImportError:
        pass

    # KV storage
    backends.append(("kv", "json"))  # Always available

    return backends

def run_storage_tests():
    """Run tests for all available storage backends."""
    backends = get_available_backends()

    print(f"Found {len(backends)} storage backends:")
    for storage_type, backend in backends:
        print(f"  - {storage_type}: {backend}")

    # Run tests for each backend
    failed = []
    for storage_type, backend in backends:
        print(f"\nTesting {backend} {storage_type} storage...")

        test_file = f"tests/storage/test_{backend}_{storage_type}.py"
        if Path(test_file).exists():
            result = pytest.main(["-xvs", test_file])
            if result != 0:
                failed.append((storage_type, backend))
        else:
            print(f"  No specific tests found, running contract tests...")
            result = pytest.main([
                "-xvs",
                f"tests/storage/contracts/test_{storage_type}_contract.py",
                f"--backend={backend}"
            ])
            if result != 0:
                failed.append((storage_type, backend))

    # Summary
    print("\n" + "="*50)
    if failed:
        print("FAILED backends:")
        for storage_type, backend in failed:
            print(f"  - {backend} ({storage_type})")
        return 1
    else:
        print("All storage backends passed!")
        return 0

if __name__ == "__main__":
    sys.exit(run_storage_tests())
```

### Phase 4: Shared Test Fixtures

#### Create `tests/storage/conftest.py`
```python
"""Shared fixtures for storage testing."""

import pytest
from typing import Dict, Any
import tempfile
from pathlib import Path

@pytest.fixture
def temp_storage_dir():
    """Temporary directory for storage tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def mock_global_config(temp_storage_dir) -> Dict[str, Any]:
    """Mock global configuration for storage tests."""
    return {
        "working_dir": str(temp_storage_dir),
        "embedding_batch_num": 32,
        "max_async": 16,
        "qdrant_path": str(temp_storage_dir / "qdrant"),
        "neo4j_url": "neo4j://localhost:7687",
        "neo4j_auth": ("neo4j", "password")
    }

@pytest.fixture
def storage_backends():
    """Get all available storage backends for testing."""
    backends = {
        "vector": [],
        "graph": [],
        "kv": []
    }

    # Try to import each backend
    try:
        from nano_graphrag._storage import NanoVectorDBStorage
        backends["vector"].append(("nano", NanoVectorDBStorage))
    except ImportError:
        pass

    try:
        from nano_graphrag._storage import HNSWVectorStorage
        backends["vector"].append(("hnswlib", HNSWVectorStorage))
    except ImportError:
        pass

    try:
        from nano_graphrag._storage import QdrantVectorStorage
        backends["vector"].append(("qdrant", QdrantVectorStorage))
    except ImportError:
        pass

    try:
        from nano_graphrag._storage import NetworkXStorage
        backends["graph"].append(("networkx", NetworkXStorage))
    except ImportError:
        pass

    try:
        from nano_graphrag._storage import Neo4jStorage
        backends["graph"].append(("neo4j", Neo4jStorage))
    except ImportError:
        pass

    return backends
```

## Definition of Done

- [ ] Abstract test suites created for all storage types:
  - [ ] BaseVectorStorageTestSuite with 15+ test cases
  - [ ] BaseGraphStorageTestSuite with 10+ test cases
  - [ ] BaseKVStorageTestSuite with 8+ test cases
- [ ] Example validation:
  - [ ] All examples tested for imports
  - [ ] Integration tests for runnable examples
  - [ ] Deprecation pattern detection
- [ ] Simple test runner:
  - [ ] Detects available backends
  - [ ] Runs appropriate test suites
  - [ ] Provides clear pass/fail summary
- [ ] Documentation:
  - [ ] Testing guide for new backends
  - [ ] Contract compliance checklist
- [ ] All existing storage implementations updated:
  - [ ] Inherit from base test suites
  - [ ] Pass all contract tests

## Feature Branch
`feature/ngraf-013-storage-testing-framework`

## Pull Request Requirements
- All storage backends pass base test suite
- Examples validate successfully
- Test runner works with all available backends
- Documentation for adding new storage backends
- Example showing how to implement custom storage

## Technical Considerations
- Use pytest fixtures for maximum reusability
- Keep test suites backend-agnostic
- Support skipping tests for missing dependencies
- Focus on contract compliance over performance
- Simple execution without complex CI setup