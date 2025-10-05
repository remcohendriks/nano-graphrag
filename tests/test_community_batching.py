"""Tests for community report generation batching and concurrency control.

Verifies:
1. Batch node/edge fetches are used (not individual get_node/get_edge calls)
2. Semaphore limits concurrent community processing
3. Configuration is properly wired
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, call
from nano_graphrag._community import _pack_single_community_describe, generate_community_report
from nano_graphrag.base import SingleCommunitySchema, CommunitySchema
from nano_graphrag._utils import TokenizerWrapper


@pytest.fixture
def mock_graph_storage():
    """Mock graph storage that tracks batch API calls."""
    storage = MagicMock()
    storage.get_nodes_batch = AsyncMock(return_value=[
        {"entity_name": "node1", "description": "desc1", "entity_type": "TYPE"},
        {"entity_name": "node2", "description": "desc2", "entity_type": "TYPE"},
    ])
    storage.get_edges_batch = AsyncMock(return_value=[
        {"description": "edge desc", "weight": 1.0, "relation_type": "RELATES"},
    ])
    storage.node_degrees_batch = AsyncMock(return_value=[5, 3])
    storage.edge_degrees_batch = AsyncMock(return_value=[2])
    return storage


@pytest.fixture
def tokenizer_wrapper():
    """Tokenizer wrapper for tests."""
    return TokenizerWrapper(tokenizer_type="tiktoken", model_name="gpt-4o")


@pytest.fixture
def sample_community():
    """Sample community for testing."""
    return {
        "nodes": ["node1", "node2"],
        "edges": [("node1", "node2")],
        "level": 0,
        "title": "Test Community",
        "occurrence": 1.0,
        "sub_communities": [],
        "chunk_ids": [],
    }


class TestBatchNodeEdgeFetches:
    """Verify that batch APIs are used instead of individual get_node/get_edge calls."""

    @pytest.mark.asyncio
    async def test_uses_get_nodes_batch(self, mock_graph_storage, tokenizer_wrapper, sample_community):
        """Verify get_nodes_batch is called instead of multiple get_node calls."""
        await _pack_single_community_describe(
            mock_graph_storage,
            sample_community,
            tokenizer_wrapper,
            max_token_size=1000,
        )

        mock_graph_storage.get_nodes_batch.assert_called_once_with(["node1", "node2"])
        assert not hasattr(mock_graph_storage, "get_node") or not mock_graph_storage.get_node.called

    @pytest.mark.asyncio
    async def test_uses_get_edges_batch(self, mock_graph_storage, tokenizer_wrapper, sample_community):
        """Verify get_edges_batch is called instead of multiple get_edge calls."""
        await _pack_single_community_describe(
            mock_graph_storage,
            sample_community,
            tokenizer_wrapper,
            max_token_size=1000,
        )

        mock_graph_storage.get_edges_batch.assert_called_once_with([("node1", "node2")])
        assert not hasattr(mock_graph_storage, "get_edge") or not mock_graph_storage.get_edge.called

    @pytest.mark.asyncio
    async def test_batch_calls_preserve_order(self, mock_graph_storage, tokenizer_wrapper):
        """Verify batch API maintains node/edge order."""
        community = {
            "nodes": ["z_node", "a_node", "m_node"],
            "edges": [("z_node", "a_node"), ("a_node", "m_node")],
            "level": 0,
            "title": "Order Test",
            "occurrence": 1.0,
            "sub_communities": [],
            "chunk_ids": [],
        }

        mock_graph_storage.get_nodes_batch = AsyncMock(return_value=[
            {"entity_name": "a_node", "description": "A", "entity_type": "TYPE"},
            {"entity_name": "m_node", "description": "M", "entity_type": "TYPE"},
            {"entity_name": "z_node", "description": "Z", "entity_type": "TYPE"},
        ])
        mock_graph_storage.node_degrees_batch = AsyncMock(return_value=[5, 3, 7])
        mock_graph_storage.edge_degrees_batch = AsyncMock(return_value=[2, 4])

        await _pack_single_community_describe(
            mock_graph_storage,
            community,
            tokenizer_wrapper,
            max_token_size=1000,
        )

        # Nodes should be sorted before batch call
        mock_graph_storage.get_nodes_batch.assert_called_once_with(["a_node", "m_node", "z_node"])


class TestSemaphoreConcurrencyControl:
    """Verify semaphore limits concurrent community processing."""

    @pytest.mark.asyncio
    async def test_semaphore_usage_in_code(self):
        """Verify semaphore is created and used in generate_community_report."""
        import inspect
        from nano_graphrag import _community

        # Read source code to verify semaphore implementation
        source = inspect.getsource(_community.generate_community_report)

        # Verify semaphore is created
        assert "asyncio.Semaphore" in source, "Semaphore not created in generate_community_report"

        # Verify semaphore uses config value
        assert "community_report_max_concurrency" in source, "Config value not used for semaphore"

        # Verify semaphore wraps community processing
        assert "async with semaphore:" in source, "Semaphore not used to wrap processing"

    @pytest.mark.asyncio
    async def test_configuration_value_present(self):
        """Verify configuration field exists with correct default."""
        from nano_graphrag.config import LLMConfig

        config = LLMConfig()
        assert hasattr(config, "community_report_max_concurrency")
        assert config.community_report_max_concurrency == 8

    @pytest.mark.asyncio
    async def test_configuration_env_var(self):
        """Verify environment variable is read correctly."""
        import os
        from nano_graphrag.config import LLMConfig

        # Set env var
        os.environ["COMMUNITY_REPORT_MAX_CONCURRENCY"] = "16"

        try:
            config = LLMConfig.from_env()
            assert config.community_report_max_concurrency == 16
        finally:
            # Clean up
            del os.environ["COMMUNITY_REPORT_MAX_CONCURRENCY"]


class TestPerformanceImpact:
    """Verify batching reduces Neo4j session calls."""

    @pytest.mark.asyncio
    async def test_single_community_uses_two_sessions(self, mock_graph_storage, tokenizer_wrapper, sample_community):
        """Verify a single community uses exactly 2 batch calls (nodes + edges)."""
        await _pack_single_community_describe(
            mock_graph_storage,
            sample_community,
            tokenizer_wrapper,
            max_token_size=1000,
        )

        # Should be exactly 1 call to get_nodes_batch and 1 to get_edges_batch
        assert mock_graph_storage.get_nodes_batch.call_count == 1
        assert mock_graph_storage.get_edges_batch.call_count == 1

    @pytest.mark.asyncio
    async def test_large_community_still_uses_two_sessions(self, mock_graph_storage, tokenizer_wrapper):
        """Verify even large communities use only 2 batch calls."""
        large_community = {
            "nodes": [f"node_{i}" for i in range(100)],
            "edges": [(f"node_{i}", f"node_{i+1}") for i in range(99)],
            "level": 0,
            "title": "Large Community",
            "occurrence": 1.0,
            "sub_communities": [],
            "chunk_ids": [],
        }

        mock_graph_storage.get_nodes_batch = AsyncMock(return_value=[
            {"entity_name": f"node_{i}", "description": f"desc_{i}", "entity_type": "TYPE"}
            for i in range(100)
        ])
        mock_graph_storage.get_edges_batch = AsyncMock(return_value=[
            {"description": f"edge_{i}", "weight": 1.0, "relation_type": "RELATES"}
            for i in range(99)
        ])
        mock_graph_storage.node_degrees_batch = AsyncMock(return_value=[i % 10 for i in range(100)])
        mock_graph_storage.edge_degrees_batch = AsyncMock(return_value=[i % 5 for i in range(99)])

        await _pack_single_community_describe(
            mock_graph_storage,
            large_community,
            tokenizer_wrapper,
            max_token_size=10000,
        )

        # Still only 2 batch calls regardless of community size
        assert mock_graph_storage.get_nodes_batch.call_count == 1
        assert mock_graph_storage.get_edges_batch.call_count == 1

        # Verify all nodes/edges were included in batch calls
        nodes_call_args = mock_graph_storage.get_nodes_batch.call_args[0][0]
        edges_call_args = mock_graph_storage.get_edges_batch.call_args[0][0]
        assert len(nodes_call_args) == 100
        assert len(edges_call_args) == 99
