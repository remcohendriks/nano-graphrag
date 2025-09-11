# NGRAF-013: Unified Storage Testing Framework

## Overview
Create a comprehensive testing framework that ensures all storage backends (vector, graph, KV) conform to their interfaces, provides performance benchmarking, enables compatibility testing between backends, and validates examples automatically.

## Current State
- Storage tests are scattered across different files with inconsistent patterns
- No standard way to validate new storage implementations
- No performance benchmarking framework
- No automated compatibility testing between backends
- Examples in `examples/` directory not validated in CI
- Each storage has its own test style and coverage levels
- No way to test storage migrations or data portability

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

### Phase 2: Performance Benchmarking Framework

#### Create `tests/storage/base/performance.py`
```python
"""Performance benchmarking for storage backends."""

import time
import asyncio
import numpy as np
from typing import Dict, Any, List
from dataclasses import dataclass
import pytest
import matplotlib.pyplot as plt
from pathlib import Path

@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""
    
    operation: str
    backend: str
    dataset_size: int
    duration: float
    operations_per_second: float
    memory_usage_mb: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "backend": self.backend,
            "dataset_size": self.dataset_size,
            "duration": self.duration,
            "ops_per_sec": self.operations_per_second,
            "memory_mb": self.memory_usage_mb
        }

class StoragePerformanceTestSuite:
    """Performance benchmarking suite for storage backends."""
    
    DATASET_SIZES = [100, 1000, 10000, 100000]
    
    @pytest.fixture
    def benchmark_dir(self, tmp_path):
        """Directory for benchmark results."""
        benchmark_path = tmp_path / "benchmarks"
        benchmark_path.mkdir()
        return benchmark_path
    
    async def benchmark_vector_storage(
        self,
        storage,
        dataset_size: int,
        dimension: int = 128
    ) -> Dict[str, BenchmarkResult]:
        """Benchmark vector storage operations."""
        results = {}
        backend_name = type(storage).__name__
        
        # Generate test data
        data = {}
        for i in range(dataset_size):
            data[f"content_{i}"] = {
                "embedding": np.random.rand(dimension).tolist(),
                "metadata": {"index": i}
            }
        
        # Benchmark upsert
        start = time.time()
        await storage.upsert(data)
        upsert_duration = time.time() - start
        
        results["upsert"] = BenchmarkResult(
            operation="upsert",
            backend=backend_name,
            dataset_size=dataset_size,
            duration=upsert_duration,
            operations_per_second=dataset_size / upsert_duration,
            memory_usage_mb=self._get_memory_usage()
        )
        
        # Benchmark queries
        query_times = []
        for _ in range(100):
            start = time.time()
            await storage.query(f"content_{np.random.randint(dataset_size)}", top_k=10)
            query_times.append(time.time() - start)
        
        avg_query_time = np.mean(query_times)
        results["query"] = BenchmarkResult(
            operation="query",
            backend=backend_name,
            dataset_size=dataset_size,
            duration=avg_query_time,
            operations_per_second=1 / avg_query_time,
            memory_usage_mb=self._get_memory_usage()
        )
        
        return results
    
    async def benchmark_graph_storage(
        self,
        storage,
        num_nodes: int,
        edge_factor: int = 3
    ) -> Dict[str, BenchmarkResult]:
        """Benchmark graph storage operations."""
        results = {}
        backend_name = type(storage).__name__
        num_edges = num_nodes * edge_factor
        
        # Benchmark node insertion
        start = time.time()
        for i in range(num_nodes):
            await storage.upsert_node(f"node_{i}", {"index": i})
        node_duration = time.time() - start
        
        results["node_insert"] = BenchmarkResult(
            operation="node_insert",
            backend=backend_name,
            dataset_size=num_nodes,
            duration=node_duration,
            operations_per_second=num_nodes / node_duration,
            memory_usage_mb=self._get_memory_usage()
        )
        
        # Benchmark edge insertion
        start = time.time()
        for i in range(num_edges):
            source = f"node_{np.random.randint(num_nodes)}"
            target = f"node_{np.random.randint(num_nodes)}"
            await storage.upsert_edge(source, target, {"weight": np.random.rand()})
        edge_duration = time.time() - start
        
        results["edge_insert"] = BenchmarkResult(
            operation="edge_insert",
            backend=backend_name,
            dataset_size=num_edges,
            duration=edge_duration,
            operations_per_second=num_edges / edge_duration,
            memory_usage_mb=self._get_memory_usage()
        )
        
        # Benchmark clustering
        if hasattr(storage, 'clustering'):
            start = time.time()
            await storage.clustering("leiden")
            clustering_duration = time.time() - start
            
            results["clustering"] = BenchmarkResult(
                operation="clustering",
                backend=backend_name,
                dataset_size=num_nodes,
                duration=clustering_duration,
                operations_per_second=1 / clustering_duration,
                memory_usage_mb=self._get_memory_usage()
            )
        
        return results
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
    
    def plot_results(
        self,
        results: List[BenchmarkResult],
        output_dir: Path
    ):
        """Generate performance comparison plots."""
        # Group by operation
        operations = {}
        for result in results:
            if result.operation not in operations:
                operations[result.operation] = []
            operations[result.operation].append(result)
        
        # Create plots
        for operation, op_results in operations.items():
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
            
            # Group by backend
            backends = {}
            for r in op_results:
                if r.backend not in backends:
                    backends[r.backend] = {"sizes": [], "times": [], "ops": []}
                backends[r.backend]["sizes"].append(r.dataset_size)
                backends[r.backend]["times"].append(r.duration)
                backends[r.backend]["ops"].append(r.operations_per_second)
            
            # Plot duration
            for backend, data in backends.items():
                ax1.plot(data["sizes"], data["times"], marker='o', label=backend)
            ax1.set_xlabel("Dataset Size")
            ax1.set_ylabel("Duration (seconds)")
            ax1.set_title(f"{operation} - Duration")
            ax1.set_xscale('log')
            ax1.set_yscale('log')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # Plot throughput
            for backend, data in backends.items():
                ax2.plot(data["sizes"], data["ops"], marker='o', label=backend)
            ax2.set_xlabel("Dataset Size")
            ax2.set_ylabel("Operations/Second")
            ax2.set_title(f"{operation} - Throughput")
            ax2.set_xscale('log')
            ax2.set_yscale('log')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.savefig(output_dir / f"benchmark_{operation}.png")
            plt.close()
    
    def generate_report(
        self,
        results: List[BenchmarkResult],
        output_file: Path
    ):
        """Generate markdown benchmark report."""
        with open(output_file, 'w') as f:
            f.write("# Storage Backend Performance Report\n\n")
            
            # Group by operation
            operations = {}
            for result in results:
                if result.operation not in operations:
                    operations[result.operation] = []
                operations[result.operation].append(result)
            
            for operation, op_results in operations.items():
                f.write(f"## {operation}\n\n")
                f.write("| Backend | Dataset Size | Duration (s) | Ops/sec | Memory (MB) |\n")
                f.write("|---------|--------------|--------------|---------|-------------|\n")
                
                for r in sorted(op_results, key=lambda x: (x.backend, x.dataset_size)):
                    f.write(f"| {r.backend} | {r.dataset_size:,} | "
                           f"{r.duration:.3f} | {r.operations_per_second:.1f} | "
                           f"{r.memory_usage_mb:.1f} |\n")
                
                f.write("\n")
```

### Phase 3: Compatibility Testing

#### Create `tests/storage/base/compatibility.py`
```python
"""Compatibility testing between storage backends."""

import pytest
import json
from typing import Any, Dict, List
import tempfile
from pathlib import Path

class StorageCompatibilityTestSuite:
    """Test data portability between storage backends."""
    
    @pytest.fixture
    def test_dataset(self) -> Dict[str, Any]:
        """Standard test dataset for compatibility testing."""
        return {
            "vectors": {
                "vec1": {"embedding": [0.1] * 128, "metadata": {"type": "A"}},
                "vec2": {"embedding": [0.2] * 128, "metadata": {"type": "B"}},
                "vec3": {"embedding": [0.3] * 128, "metadata": {"type": "A"}}
            },
            "nodes": {
                "node1": {"type": "Person", "name": "Alice"},
                "node2": {"type": "Person", "name": "Bob"},
                "node3": {"type": "Organization", "name": "ACME"}
            },
            "edges": [
                ("node1", "node2", {"relation": "knows"}),
                ("node1", "node3", {"relation": "works_at"}),
                ("node2", "node3", {"relation": "works_at"})
            ],
            "kv_data": {
                "key1": {"value": "data1"},
                "key2": {"value": "data2"},
                "key3": {"value": "data3"}
            }
        }
    
    async def test_vector_storage_migration(
        self,
        source_storage,
        target_storage,
        test_dataset
    ):
        """Test migrating data between vector storage backends."""
        # Insert into source
        await source_storage.upsert(test_dataset["vectors"])
        
        # Export from source
        all_data = {}
        for content in test_dataset["vectors"].keys():
            results = await source_storage.query(content, top_k=1)
            if results:
                all_data[content] = {
                    "embedding": test_dataset["vectors"][content]["embedding"],
                    **results[0]
                }
        
        # Import to target
        await target_storage.upsert(all_data)
        
        # Verify in target
        for content in test_dataset["vectors"].keys():
            results = await target_storage.query(content, top_k=1)
            assert len(results) > 0
            assert results[0].get("metadata", {}).get("type") == \
                   test_dataset["vectors"][content]["metadata"]["type"]
    
    async def test_graph_storage_migration(
        self,
        source_storage,
        target_storage,
        test_dataset
    ):
        """Test migrating graph data between backends."""
        # Insert into source
        for node_id, node_data in test_dataset["nodes"].items():
            await source_storage.upsert_node(node_id, node_data)
        
        for source, target, edge_data in test_dataset["edges"]:
            await source_storage.upsert_edge(source, target, edge_data)
        
        # Export from source
        nodes = await source_storage.get_nodes()
        edges = await source_storage.get_edges()
        
        # Import to target
        for node_id, node_data in nodes:
            await target_storage.upsert_node(node_id, node_data)
        
        for source, target, edge_data in edges:
            await target_storage.upsert_edge(source, target, edge_data)
        
        # Verify in target
        target_nodes = await target_storage.get_nodes()
        target_edges = await target_storage.get_edges()
        
        assert len(target_nodes) == len(nodes)
        assert len(target_edges) == len(edges)
    
    def test_serialization_compatibility(self, test_dataset):
        """Test that all backends can serialize/deserialize consistently."""
        # Create common serialization format
        serialized = {
            "version": "1.0",
            "vectors": test_dataset["vectors"],
            "graph": {
                "nodes": test_dataset["nodes"],
                "edges": test_dataset["edges"]
            },
            "kv": test_dataset["kv_data"]
        }
        
        # Ensure JSON serializable
        json_str = json.dumps(serialized)
        deserialized = json.loads(json_str)
        
        assert deserialized == serialized
```

### Phase 4: Example Validation Framework

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

### Phase 5: CI/CD Integration

#### Create `.github/workflows/storage-tests.yml`
```yaml
name: Storage Backend Tests

on:
  push:
    paths:
      - 'nano_graphrag/_storage/**'
      - 'tests/storage/**'
  pull_request:
    paths:
      - 'nano_graphrag/_storage/**'
      - 'tests/storage/**'

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        storage: [nano, hnswlib, qdrant, neo4j]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install base dependencies
      run: |
        pip install -e .[test]
    
    - name: Install storage-specific deps
      run: |
        if [ "${{ matrix.storage }}" = "qdrant" ]; then
          pip install qdrant-client
        elif [ "${{ matrix.storage }}" = "neo4j" ]; then
          pip install neo4j
        elif [ "${{ matrix.storage }}" = "hnswlib" ]; then
          pip install hnswlib
        fi
    
    - name: Run storage tests
      run: |
        pytest tests/storage/test_${{ matrix.storage }}_storage.py -v
  
  compatibility-tests:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install all storage backends
      run: |
        pip install -e .[all]
    
    - name: Run compatibility tests
      run: |
        pytest tests/storage/test_compatibility.py -v
  
  performance-benchmarks:
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install -e .[all,benchmark]
    
    - name: Run benchmarks
      run: |
        pytest tests/storage/benchmarks/ --benchmark-only
    
    - name: Upload results
      uses: actions/upload-artifact@v3
      with:
        name: benchmark-results
        path: benchmark_results/
  
  example-validation:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install -e .
    
    - name: Validate examples
      run: |
        pytest tests/examples/test_examples.py -v
```

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
- [ ] Performance benchmarking framework:
  - [ ] Automated benchmarks for all operations
  - [ ] Comparison plots and reports
  - [ ] Memory profiling
  - [ ] Scalability tests (100 to 1M items)
- [ ] Compatibility testing:
  - [ ] Data migration tests between backends
  - [ ] Serialization format validation
  - [ ] Cross-backend query consistency
- [ ] Example validation:
  - [ ] All examples tested for imports
  - [ ] Integration tests for runnable examples
  - [ ] Deprecation pattern detection
- [ ] CI/CD integration:
  - [ ] Matrix testing for all backends
  - [ ] Conditional backend installation
  - [ ] Performance regression detection
  - [ ] Example validation in CI
- [ ] Documentation:
  - [ ] Testing guide for new backends
  - [ ] Performance tuning guide
  - [ ] Compatibility matrix
- [ ] All existing storage implementations updated:
  - [ ] Inherit from base test suites
  - [ ] Pass all contract tests
  - [ ] Performance baselines established

## Feature Branch
`feature/ngraf-013-storage-testing-framework`

## Pull Request Requirements
- All storage backends pass base test suite
- Performance benchmarks for all backends
- CI passes with all optional dependencies
- Documentation for adding new storage backends
- Example showing how to implement custom storage

## Technical Considerations
- Use pytest fixtures for maximum reusability
- Keep test suites backend-agnostic
- Support skipping tests for missing dependencies
- Ensure tests work in CI environment
- Consider test parallelization for speed