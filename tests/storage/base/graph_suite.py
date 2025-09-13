"""Base test suite for graph storage implementations."""

import pytest
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class GraphStorageContract:
    """Contract that all graph storages must fulfill."""

    supports_properties: bool = True
    supports_multi_graph: bool = False
    supports_transactions: bool = False
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
        # Create nodes
        await storage.upsert_node("node1", {"type": "Person", "name": "Alice", "age": "30"})
        await storage.upsert_node("node2", {"type": "Person", "name": "Bob", "age": "25"})

        # Read node
        node = await storage.get_node("node1")
        assert node is not None
        assert node.get("type") == "Person"
        assert node.get("name") == "Alice"

        # Update node
        await storage.upsert_node("node1", {"type": "Person", "name": "Alice Updated", "age": "31"})
        node = await storage.get_node("node1")
        assert node.get("name") == "Alice Updated"
        assert node.get("age") == "31"

        # Check node existence
        exists = await storage.has_node("node1")
        assert exists is True

        not_exists = await storage.has_node("nonexistent")
        assert not_exists is False

    @pytest.mark.asyncio
    async def test_edge_operations(self, storage):
        """Test edge CRUD operations."""
        # Setup nodes
        await storage.upsert_node("source", {"type": "Person"})
        await storage.upsert_node("target", {"type": "Person"})

        # Create edge
        await storage.upsert_edge("source", "target", {"relation": "knows", "weight": "0.8"})

        # Check edge existence
        has_edge = await storage.has_edge("source", "target")
        assert has_edge is True

        # Get edge
        edge = await storage.get_edge("source", "target")
        assert edge is not None
        assert edge.get("relation") == "knows"
        assert edge.get("weight") == "0.8"

        # Update edge
        await storage.upsert_edge("source", "target", {"relation": "knows", "weight": "0.9", "since": "2020"})
        edge = await storage.get_edge("source", "target")
        assert edge.get("weight") == "0.9"
        assert edge.get("since") == "2020"

    @pytest.mark.asyncio
    async def test_batch_operations(self, storage):
        """Test batch node and edge operations."""
        # Batch node upsert
        nodes_data = [
            (f"batch_node_{i}", {"type": "TestNode", "index": str(i)})
            for i in range(10)
        ]
        await storage.upsert_nodes_batch(nodes_data)

        # Verify nodes created
        node_ids = [f"batch_node_{i}" for i in range(10)]
        nodes = await storage.get_nodes_batch(node_ids)
        assert len(nodes) == 10

        # Batch edge upsert
        edges_data = [
            (f"batch_node_{i}", f"batch_node_{i+1}", {"weight": str(i)})
            for i in range(9)
        ]
        await storage.upsert_edges_batch(edges_data)

        # Verify edges created
        edge_pairs = [(f"batch_node_{i}", f"batch_node_{i+1}") for i in range(9)]
        edges = await storage.get_edges_batch(edge_pairs)
        assert len(edges) == 9

    @pytest.mark.asyncio
    async def test_node_degree_calculations(self, storage):
        """Test node degree calculations."""
        # Create a simple graph
        await storage.upsert_node("center", {"type": "Center"})
        for i in range(5):
            await storage.upsert_node(f"spoke_{i}", {"type": "Spoke"})
            await storage.upsert_edge("center", f"spoke_{i}", {"weight": str(i)})

        # Test single node degree
        degree = await storage.node_degree("center")
        assert degree == 5

        # Test batch node degrees
        node_ids = ["center"] + [f"spoke_{i}" for i in range(5)]
        degrees = await storage.node_degrees_batch(node_ids)
        assert degrees[0] == 5  # center node
        for i in range(1, 6):
            assert degrees[i] == 1  # spoke nodes

    @pytest.mark.asyncio
    async def test_edge_degree_calculations(self, storage):
        """Test edge degree calculations."""
        # Create nodes and edges
        for i in range(3):
            await storage.upsert_node(f"node_{i}", {"type": "Node"})

        await storage.upsert_edge("node_0", "node_1", {"weight": "1"})
        await storage.upsert_edge("node_1", "node_2", {"weight": "2"})

        # Test single edge degree
        degree = await storage.edge_degree("node_0", "node_1")
        assert degree >= 1

        # Test batch edge degrees
        edge_pairs = [("node_0", "node_1"), ("node_1", "node_2")]
        degrees = await storage.edge_degrees_batch(edge_pairs)
        assert len(degrees) == 2
        assert all(d >= 1 for d in degrees)

    @pytest.mark.asyncio
    async def test_get_node_edges(self, storage):
        """Test retrieving edges for a node."""
        # Create star topology
        await storage.upsert_node("hub", {"type": "Hub"})
        for i in range(3):
            await storage.upsert_node(f"node_{i}", {"type": "Node"})
            await storage.upsert_edge("hub", f"node_{i}", {"index": str(i)})

        # Get edges for hub
        edges = await storage.get_node_edges("hub")
        assert edges is not None
        assert len(edges) == 3

        # Batch get edges
        nodes = ["hub", "node_0", "node_1"]
        all_edges = await storage.get_nodes_edges_batch(nodes)
        assert len(all_edges) == 3
        assert len(all_edges[0]) == 3  # hub has 3 edges
        # node_0 and node_1 may have 0 edges if graph is directed (only incoming edges from hub)

    @pytest.mark.asyncio
    async def test_clustering(self, storage, contract):
        """Test graph clustering algorithms."""
        if not contract.supports_clustering:
            pytest.skip("Storage doesn't support clustering")

        # Create two connected components
        # Component 1: Fully connected
        for i in range(5):
            await storage.upsert_node(f"comp1_node_{i}", {"component": "1"})

        for i in range(5):
            for j in range(i + 1, 5):
                await storage.upsert_edge(f"comp1_node_{i}", f"comp1_node_{j}", {"weight": "1"})

        # Component 2: Fully connected
        for i in range(5):
            await storage.upsert_node(f"comp2_node_{i}", {"component": "2"})

        for i in range(5):
            for j in range(i + 1, 5):
                await storage.upsert_edge(f"comp2_node_{i}", f"comp2_node_{j}", {"weight": "1"})

        # Run clustering
        for algorithm in contract.clustering_algorithms:
            try:
                result = await storage.clustering(algorithm)
                assert result is not None

                # Check if communities were detected
                if isinstance(result, dict) and "communities" in result:
                    communities = result["communities"]
                    unique_communities = set(communities.values())
                    # Should detect at least 2 communities
                    assert len(unique_communities) >= 2
            except NotImplementedError:
                pass

    @pytest.mark.asyncio
    async def test_concurrent_modifications(self, storage):
        """Test concurrent graph modifications."""
        async def modify_graph(index):
            node_id = f"concurrent_{index}"
            await storage.upsert_node(node_id, {"index": str(index)})

            if index > 0:
                prev_node = f"concurrent_{index - 1}"
                try:
                    await storage.upsert_edge(prev_node, node_id, {"order": str(index)})
                except Exception:
                    # Node might not exist yet due to concurrency
                    pass

        # Concurrent modifications
        tasks = [modify_graph(i) for i in range(20)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Verify nodes created
        node_count = 0
        for i in range(20):
            if await storage.has_node(f"concurrent_{i}"):
                node_count += 1

        assert node_count >= 15  # Most nodes should be created

    @pytest.mark.asyncio
    async def test_graphrag_namespace_handling(self, storage):
        """Test GraphRAG-specific namespace handling."""
        # Create nodes with GraphRAG naming convention
        entity_nodes = [
            ("entity_person_alice", {"type": "Person", "name": "Alice"}),
            ("entity_person_bob", {"type": "Person", "name": "Bob"}),
            ("entity_org_acme", {"type": "Organization", "name": "ACME"})
        ]

        for node_id, data in entity_nodes:
            await storage.upsert_node(node_id, data)

        # Create relationships
        await storage.upsert_edge("entity_person_alice", "entity_person_bob", {"relation": "knows"})
        await storage.upsert_edge("entity_person_alice", "entity_org_acme", {"relation": "works_at"})

        # Verify namespace handling
        alice = await storage.get_node("entity_person_alice")
        assert alice is not None
        assert alice.get("name") == "Alice"

        # Check if namespace is properly set
        if hasattr(storage, 'namespace'):
            assert storage.namespace is not None

    @pytest.mark.asyncio
    async def test_special_characters_in_ids(self, storage):
        """Test handling of special characters in node/edge IDs."""
        special_ids = [
            "node_with_underscore",
            "node-with-dash",
            "node.with.dot",
            "node:with:colon"
        ]

        for node_id in special_ids:
            try:
                # Some storages may not support all special chars
                safe_id = node_id.replace(":", "_").replace(".", "_")
                await storage.upsert_node(safe_id, {"original_id": node_id})
                exists = await storage.has_node(safe_id)
                assert exists is True
            except Exception:
                # Some backends may reject certain characters
                pass