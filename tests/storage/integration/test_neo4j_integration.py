"""Integration tests for Neo4j storage backend."""

import os
import pytest
import pytest_asyncio
from tests.storage.base import BaseGraphStorageTestSuite, GraphStorageContract
from nano_graphrag._storage.gdb_neo4j import Neo4jStorage


# Skip all tests if Neo4j is not configured
pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_URL") or not os.environ.get("NEO4J_AUTH"),
    reason="Neo4j not configured (set NEO4J_URL and NEO4J_AUTH environment variables)"
)


class TestNeo4jIntegration(BaseGraphStorageTestSuite):
    """Neo4j storage integration tests."""

    @pytest_asyncio.fixture
    async def storage(self):
        """Provide Neo4j storage instance."""
        config = {
            "addon_params": {
                "neo4j_url": os.environ.get("NEO4J_URL", "neo4j://localhost:7687"),
                "neo4j_auth": (
                    os.environ.get("NEO4J_USER", "neo4j"),
                    os.environ.get("NEO4J_PASSWORD", "password")
                ),
                "neo4j_database": os.environ.get("NEO4J_DATABASE", "neo4j")
            },
            "working_dir": "./test_neo4j_integration"
        }

        storage = Neo4jStorage(namespace="test_integration", global_config=config)

        # Clean up before tests
        await storage._debug_delete_all_node_edges()
        await storage.index_start_callback()

        yield storage

        # Clean up after tests
        await storage._debug_delete_all_node_edges()
        await storage.close()

    @pytest.fixture
    def contract(self):
        """Define Neo4j capabilities."""
        return GraphStorageContract(
            supports_properties=True,
            supports_multi_graph=False,
            supports_transactions=True,
            supports_clustering=True,
            clustering_algorithms=["leiden"],
            max_nodes=None,
            max_edges=None
        )

    @pytest.mark.asyncio
    async def test_neo4j_specific_features(self, storage):
        """Test Neo4j-specific features."""
        # Test Cypher query execution
        await storage.upsert_node("test_node", {"name": "Test", "value": "123"})

        # Neo4j should handle complex properties
        complex_data = {
            "name": "Complex Node",
            "tags": "tag1,tag2,tag3",  # Neo4j doesn't support lists directly in properties
            "metadata": '{"key": "value"}',  # JSON as string
            "score": "0.95"
        }
        await storage.upsert_node("complex_node", complex_data)

        node = await storage.get_node("complex_node")
        assert node is not None
        assert node["name"] == "Complex Node"
        assert "tag1" in node["tags"]

    @pytest.mark.asyncio
    async def test_neo4j_namespace_isolation(self, storage):
        """Test that namespaces properly isolate data."""
        # Create node in test namespace
        await storage.upsert_node("shared_node", {"namespace": "test_integration"})

        # Create another storage with different namespace
        config = storage.global_config
        other_storage = Neo4jStorage(namespace="other_namespace", global_config=config)

        # Node should not be visible in other namespace
        node = await other_storage.get_node("shared_node")
        # Due to namespace isolation, it might not find the node or find a different one
        if node:
            assert node.get("namespace") != "test_integration"

        await other_storage.close()