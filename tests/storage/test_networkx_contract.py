"""Contract-based tests for NetworkX graph storage."""

import pytest
import pytest_asyncio
from pathlib import Path
from tests.storage.base import BaseGraphStorageTestSuite, GraphStorageContract
from nano_graphrag._storage import NetworkXStorage


class TestNetworkXContract(BaseGraphStorageTestSuite):
    """NetworkX storage contract tests."""

    @pytest_asyncio.fixture
    async def storage(self, temp_storage_dir):
        """Provide NetworkX storage instance."""
        config = {
            "working_dir": str(temp_storage_dir),
            "max_graph_cluster_size": 10,
            "graph_cluster_seed": 42
        }

        # Ensure directory exists
        Path(config["working_dir"]).mkdir(parents=True, exist_ok=True)

        storage = NetworkXStorage(
            namespace="test",
            global_config=config
        )

        # Initialize
        await storage.index_start_callback()

        yield storage

        # Cleanup is automatic with temp dir

    @pytest.fixture
    def contract(self):
        """Define NetworkX capabilities."""
        return GraphStorageContract(
            supports_properties=True,
            supports_multi_graph=False,
            supports_transactions=False,  # NetworkX is in-memory
            supports_clustering=True,
            clustering_algorithms=["leiden"],
            max_nodes=None,  # Limited by memory
            max_edges=None  # Limited by memory
        )