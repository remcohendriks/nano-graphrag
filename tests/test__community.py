"""Test community operations."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from nano_graphrag._community import (
    _pack_single_community_by_sub_communities,
    _community_report_json_to_str,
    summarize_community
)
from nano_graphrag._utils import TokenizerWrapper


@pytest.fixture
def tokenizer():
    """Create tokenizer fixture."""
    return TokenizerWrapper(tokenizer_type="tiktoken", model_name="gpt-4o")


@pytest.fixture
def mock_graph_storage():
    """Create mock graph storage."""
    storage = AsyncMock()
    storage.get_node = AsyncMock()
    storage.get_node_edges = AsyncMock()
    return storage


class TestCommunity:
    def test_pack_single_community_by_sub_communities(self, tokenizer):
        """Test packing community with sub-communities."""
        community = {
            "sub_communities": ["sub1", "sub2", "sub3"],
            "title": "Test Community"
        }
        
        already_reports = {
            "sub1": {
                "report_string": "Report 1",
                "report_json": {"rating": 5},
                "occurrence": 10,
                "nodes": ["node1", "node2"],
                "edges": [["node1", "node2"]]
            },
            "sub2": {
                "report_string": "Report 2",
                "report_json": {"rating": 3},
                "occurrence": 5,
                "nodes": ["node3"],
                "edges": []
            }
            # sub3 not in already_reports - should be filtered
        }
        
        result = _pack_single_community_by_sub_communities(
            community, 1000, already_reports, tokenizer
        )
        
        describe, token_count, nodes, edges = result
        
        # Check CSV format (uses comma+tab delimiter)
        assert '"id",\t"report",\t"rating",\t"importance"' in describe
        assert "Report 1" in describe
        assert "Report 2" in describe
        
        # Check collected nodes and edges
        assert "node1" in nodes
        assert "node2" in nodes
        assert "node3" in nodes
        assert ("node1", "node2") in edges
        
    def test_community_report_json_to_str(self):
        """Test converting community report JSON to string."""
        # Full report
        report = {
            "title": "Test Report",
            "summary": "This is a summary",
            "findings": [
                {
                    "summary": "Finding 1",
                    "explanation": "Explanation 1"
                },
                {
                    "summary": "Finding 2",
                    "explanation": "Explanation 2"
                }
            ]
        }
        
        result = _community_report_json_to_str(report)
        
        assert "# Test Report" in result
        assert "This is a summary" in result
        assert "## Finding 1" in result
        assert "Explanation 1" in result
        assert "## Finding 2" in result
        assert "Explanation 2" in result
        
        # Report with string findings
        report = {
            "title": "Simple Report",
            "summary": "Summary",
            "findings": ["Finding 1", "Finding 2"]
        }
        
        result = _community_report_json_to_str(report)
        assert "## Finding 1" in result
        assert "## Finding 2" in result
        
        # Report with missing fields
        report = {}
        result = _community_report_json_to_str(report)
        assert "# Report" in result  # Default title
        
    @pytest.mark.asyncio
    async def test_summarize_community(self, mock_graph_storage):
        """Test community summarization."""
        node_ids = ["node1", "node2", "node3"]
        
        # Mock node data
        mock_graph_storage.get_node.side_effect = [
            {"id": "node1", "name": "Node 1", "description": "Desc 1"},
            {"id": "node2", "name": "Node 2", "description": "Desc 2"},
            {"id": "node3", "name": "Node 3", "description": "Desc 3"}
        ]
        
        # Mock edges
        mock_graph_storage.get_node_edges.side_effect = [
            [{"source": "node1", "target": "node2", "relation": "CONNECTS"}],
            [{"source": "node2", "target": "node3", "relation": "LINKS"}],
            []
        ]
        
        # Mock LLM
        mock_llm = AsyncMock(return_value='{"summary": "Test summary", "entities": ["node1", "node2"], "relationships": 2}')
        
        # Mock JSON converter
        def mock_json_convert(response):
            import json
            return json.loads(response)
        
        result = await summarize_community(
            node_ids,
            mock_graph_storage,
            mock_llm,
            max_tokens=1000,
            to_json_func=mock_json_convert
        )
        
        assert result["summary"] == "Test summary"
        assert result["entities"] == ["node1", "node2"]
        assert result["relationships"] == 2
        
        # Verify mock calls
        assert mock_graph_storage.get_node.call_count == 3
        assert mock_graph_storage.get_node_edges.call_count == 3
        mock_llm.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_summarize_community_with_invalid_json(self, mock_graph_storage):
        """Test community summarization with invalid JSON response."""
        node_ids = ["node1"]
        
        mock_graph_storage.get_node.return_value = {
            "id": "node1", "name": "Node 1", "description": "Desc 1"
        }
        mock_graph_storage.get_node_edges.return_value = []
        
        # Mock LLM with invalid JSON
        mock_llm = AsyncMock(return_value="This is not JSON")
        
        result = await summarize_community(
            node_ids,
            mock_graph_storage,
            mock_llm,
            max_tokens=100
        )
        
        # Should fallback to text summary
        assert "summary" in result
        assert result["summary"] == "This is not JSON"[:100]
        assert result["entities"] == ["Node 1"]
        assert result["relationships"] == 0
        
    @pytest.mark.asyncio
    async def test_summarize_empty_community(self, mock_graph_storage):
        """Test summarizing empty community."""
        node_ids = []
        mock_llm = AsyncMock(return_value='{"summary": "Empty"}')
        
        result = await summarize_community(
            node_ids,
            mock_graph_storage,
            mock_llm
        )
        
        # Should handle empty community gracefully
        assert "summary" in result
        
    @pytest.mark.asyncio
    async def test_summarize_community_with_missing_nodes(self, mock_graph_storage):
        """Test summarization when some nodes are missing."""
        node_ids = ["node1", "missing_node"]
        
        mock_graph_storage.get_node.side_effect = [
            {"id": "node1", "name": "Node 1", "description": "Desc 1"},
            None  # Missing node
        ]
        mock_graph_storage.get_node_edges.return_value = []
        
        mock_llm = AsyncMock(return_value='{"summary": "Partial"}')
        
        result = await summarize_community(
            node_ids,
            mock_graph_storage,
            mock_llm
        )
        
        # Should skip missing nodes
        assert "summary" in result