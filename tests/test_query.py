"""Test query operations."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from nano_graphrag.query import (
    _find_most_related_community_from_entities,
    _find_most_related_text_unit_from_entities,
    _find_most_related_edges_from_entities,
    _build_local_query_context,
    local_query,
    global_query,
    naive_query
)
from nano_graphrag.base import QueryParam
from nano_graphrag._utils import TokenizerWrapper


@pytest.fixture
def tokenizer():
    """Create tokenizer fixture."""
    return TokenizerWrapper(tokenizer_type="tiktoken", model_name="gpt-4o")


@pytest.fixture
def query_param():
    """Create query parameters."""
    return QueryParam(
        top_k=10,
        level=0,
        response_type="multiple paragraphs",
        local_max_token_for_community_report=3000,
        local_max_token_for_text_unit=3000,
        local_max_token_for_local_context=4000,
        local_community_single_one=False,
        global_max_token_for_community_report=3000,
        global_max_consider_community=10,
        global_min_community_rating=0,
        naive_max_token_for_text_unit=3000,
        only_need_context=False
    )


@pytest.fixture
def mock_storages():
    """Create mock storage instances."""
    return {
        "graph": AsyncMock(),
        "entities_vdb": AsyncMock(),
        "community_reports": AsyncMock(),
        "text_chunks": AsyncMock(),
        "chunks_vdb": AsyncMock()
    }


class TestQuery:
    @pytest.mark.asyncio
    async def test_find_most_related_community(self, query_param, tokenizer):
        """Test finding most related communities from entities."""
        node_datas = [
            {
                "entity_name": "node1",
                "clusters": json.dumps([
                    {"cluster": "comm1", "level": 0},
                    {"cluster": "comm2", "level": 0}
                ])
            },
            {
                "entity_name": "node2",
                "clusters": json.dumps([
                    {"cluster": "comm1", "level": 0}
                ])
            }
        ]
        
        mock_reports = AsyncMock()
        mock_reports.get_by_id.side_effect = [
            {"report_string": "Community 1 report", "report_json": {"rating": 5}},
            {"report_string": "Community 2 report", "report_json": {"rating": 3}}
        ]
        
        result = await _find_most_related_community_from_entities(
            node_datas, query_param, mock_reports, tokenizer
        )
        
        # comm1 should be first (appears twice)
        assert len(result) == 2
        assert "Community 1 report" in result[0]["report_string"]
        
    @pytest.mark.asyncio
    async def test_find_most_related_text_units(self, query_param, tokenizer, mock_storages):
        """Test finding most related text units from entities."""
        node_datas = [
            {"entity_name": "node1", "source_id": "chunk1##chunk2"},
            {"entity_name": "node2", "source_id": "chunk2##chunk3"}
        ]
        
        # Mock graph edges
        mock_storages["graph"].get_nodes_edges_batch.return_value = [
            [("node1", "node3")],
            [("node2", "node3")]
        ]
        
        # Mock one-hop nodes
        mock_storages["graph"].get_nodes_batch.return_value = [
            {"source_id": "chunk1##chunk4"}
        ]
        
        # Mock text chunks
        mock_storages["text_chunks"].get_by_id.side_effect = [
            {"content": "Chunk 1 content"},
            {"content": "Chunk 2 content"},
            {"content": "Chunk 3 content"}
        ]
        
        result = await _find_most_related_text_unit_from_entities(
            node_datas, query_param, mock_storages["text_chunks"],
            mock_storages["graph"], tokenizer
        )
        
        assert len(result) > 0
        assert all("content" in chunk for chunk in result)
        
    @pytest.mark.asyncio
    async def test_find_most_related_edges(self, query_param, tokenizer, mock_storages):
        """Test finding most related edges from entities."""
        node_datas = [
            {"entity_name": "node1"},
            {"entity_name": "node2"}
        ]
        
        # Mock edges
        mock_storages["graph"].get_nodes_edges_batch.return_value = [
            [("node1", "node3"), ("node1", "node4")],
            [("node2", "node3")]
        ]
        
        # Mock edge data
        mock_storages["graph"].get_edges_batch.return_value = [
            {"description": "Edge 1", "weight": 1.0},
            {"description": "Edge 2", "weight": 0.5},
            {"description": "Edge 3", "weight": 0.8}
        ]
        
        # Mock edge degrees
        mock_storages["graph"].edge_degrees_batch.return_value = [3, 2, 2]
        
        result = await _find_most_related_edges_from_entities(
            node_datas, query_param, mock_storages["graph"], tokenizer
        )
        
        assert len(result) == 3
        assert all("description" in edge for edge in result)
        # Should be sorted by rank and weight
        assert result[0]["rank"] >= result[-1]["rank"]
        
    @pytest.mark.asyncio
    async def test_build_local_query_context(self, query_param, tokenizer, mock_storages):
        """Test building local query context."""
        query = "test query"
        
        # Mock entity search results
        mock_storages["entities_vdb"].query.return_value = [
            {"entity_name": "entity1"},
            {"entity_name": "entity2"}
        ]
        
        # Mock node data
        mock_storages["graph"].get_nodes_batch.return_value = [
            {"entity_name": "entity1", "entity_type": "PERSON", "description": "Person 1"},
            {"entity_name": "entity2", "entity_type": "ORG", "description": "Org 1"}
        ]
        
        # Mock node degrees
        mock_storages["graph"].node_degrees_batch.return_value = [5, 3]
        
        # Mock edges
        mock_storages["graph"].get_nodes_edges_batch.return_value = [[], []]
        
        # Mock empty results for other components
        mock_storages["graph"].get_edges_batch.return_value = []
        mock_storages["graph"].edge_degrees_batch.return_value = []
        
        context = await _build_local_query_context(
            query,
            mock_storages["graph"],
            mock_storages["entities_vdb"],
            mock_storages["community_reports"],
            mock_storages["text_chunks"],
            query_param,
            tokenizer
        )
        
        assert context is not None
        assert "-----Entities-----" in context
        assert "entity1" in context
        assert "entity2" in context
        
    @pytest.mark.asyncio
    async def test_local_query(self, query_param, tokenizer, mock_storages):
        """Test local query execution."""
        query = "test query"
        
        # Mock entity search
        mock_storages["entities_vdb"].query.return_value = [
            {"entity_name": "entity1"}
        ]
        
        # Mock node data
        mock_storages["graph"].get_nodes_batch.return_value = [
            {"entity_name": "entity1", "description": "Test entity"}
        ]
        mock_storages["graph"].node_degrees_batch.return_value = [1]
        mock_storages["graph"].get_nodes_edges_batch.return_value = [[]]
        mock_storages["graph"].get_edges_batch.return_value = []
        mock_storages["graph"].edge_degrees_batch.return_value = []
        
        global_config = {
            "best_model_func": AsyncMock(return_value="Query response")
        }
        
        result = await local_query(
            query,
            mock_storages["graph"],
            mock_storages["entities_vdb"],
            mock_storages["community_reports"],
            mock_storages["text_chunks"],
            query_param,
            tokenizer,
            global_config
        )
        
        assert result == "Query response"
        global_config["best_model_func"].assert_called_once()
        
    @pytest.mark.asyncio
    async def test_global_query(self, query_param, tokenizer, mock_storages):
        """Test global query execution."""
        query = "test global query"
        
        # Mock community schema
        mock_storages["graph"].community_schema.return_value = {
            "comm1": {"level": 0, "occurrence": 10},
            "comm2": {"level": 0, "occurrence": 5}
        }
        
        # Mock community reports
        mock_storages["community_reports"].get_by_ids.return_value = [
            {
                "report_string": "Community 1",
                "report_json": {"rating": 5},
                "occurrence": 10
            },
            {
                "report_string": "Community 2",
                "report_json": {"rating": 3},
                "occurrence": 5
            }
        ]
        
        global_config = {
            "best_model_func": AsyncMock(side_effect=[
                '{"points": [{"description": "Point 1", "score": 1}]}',
                "Final response"
            ]),
            "convert_response_to_json_func": lambda x: json.loads(x)
        }
        
        result = await global_query(
            query,
            mock_storages["graph"],
            mock_storages["entities_vdb"],
            mock_storages["community_reports"],
            mock_storages["text_chunks"],
            query_param,
            tokenizer,
            global_config
        )
        
        assert result == "Final response"
        
    @pytest.mark.asyncio
    async def test_naive_query(self, query_param, tokenizer, mock_storages):
        """Test naive query execution."""
        query = "test naive query"
        
        # Mock chunk search
        mock_storages["chunks_vdb"].query.return_value = [
            {"id": "chunk1"},
            {"id": "chunk2"}
        ]
        
        # Mock chunk content
        mock_storages["text_chunks"].get_by_ids.return_value = [
            {"content": "Chunk 1 content"},
            {"content": "Chunk 2 content"}
        ]
        
        global_config = {
            "best_model_func": AsyncMock(return_value="Naive response")
        }
        
        result = await naive_query(
            query,
            mock_storages["chunks_vdb"],
            mock_storages["text_chunks"],
            query_param,
            tokenizer,
            global_config
        )
        
        assert result == "Naive response"
        global_config["best_model_func"].assert_called_once()
        
    @pytest.mark.asyncio
    async def test_query_with_only_context(self, query_param, tokenizer, mock_storages):
        """Test query with only_need_context flag."""
        query_param.only_need_context = True
        
        # Mock chunk search
        mock_storages["chunks_vdb"].query.return_value = [
            {"id": "chunk1"}
        ]
        
        mock_storages["text_chunks"].get_by_ids.return_value = [
            {"content": "Test content"}
        ]
        
        global_config = {
            "best_model_func": AsyncMock()
        }
        
        result = await naive_query(
            "test",
            mock_storages["chunks_vdb"],
            mock_storages["text_chunks"],
            query_param,
            tokenizer,
            global_config
        )
        
        # Should return context only, not call LLM
        assert "Test content" in result
        global_config["best_model_func"].assert_not_called()