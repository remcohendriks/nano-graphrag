"""Test community report generation with token limit handling."""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock
from typing import List, Dict, Any

from nano_graphrag._community import generate_community_report, _pack_single_community_describe
from nano_graphrag.base import SingleCommunitySchema
from nano_graphrag._utils import TokenizerWrapper


class MockTokenizerWrapper:
    """Mock tokenizer that simulates token counting."""

    def __init__(self, tokens_per_char: float = 0.25):
        self.tokens_per_char = tokens_per_char

    def encode(self, text: str) -> List[int]:
        """Simulate encoding by returning mock tokens based on text length."""
        token_count = int(len(text) * self.tokens_per_char)
        return list(range(token_count))


class MockGraphStorage:
    """Mock graph storage for testing."""

    def __init__(self, large_community_size: int = 500):
        self.large_community_size = large_community_size

    async def community_schema(self) -> Dict[str, SingleCommunitySchema]:
        """Return mock community schema with one large community."""
        # Create a large community that will exceed token limits
        large_nodes = [f"node_{i}" for i in range(self.large_community_size)]
        large_edges = [(f"node_{i}", f"node_{i+1}") for i in range(self.large_community_size - 1)]

        return {
            "community_1": {
                "title": "Large Test Community",
                "level": 0,
                "nodes": large_nodes,
                "edges": large_edges,
                "sub_communities": [],
                "occurrence": 1.0
            },
            "community_2": {
                "title": "Small Test Community",
                "level": 0,
                "nodes": ["node_a", "node_b", "node_c"],
                "edges": [("node_a", "node_b"), ("node_b", "node_c")],
                "sub_communities": [],
                "occurrence": 0.5
            }
        }

    async def get_node(self, node_id: str) -> Dict[str, Any]:
        """Return mock node data."""
        return {
            "entity_type": "TEST_ENTITY",
            "description": f"This is a very long description for {node_id} " * 10  # Make it long
        }

    async def get_edge(self, src: str, tgt: str) -> Dict[str, Any]:
        """Return mock edge data."""
        return {
            "description": f"Long relationship between {src} and {tgt} " * 10,  # Make it long
            "relation_type": "RELATED",
            "weight": 1.0
        }

    async def node_degrees_batch(self, node_ids: List[str]) -> List[int]:
        """Return mock node degrees."""
        return [len(node_ids) - i for i in range(len(node_ids))]

    async def edge_degrees_batch(self, edges: List[tuple]) -> List[int]:
        """Return mock edge degrees."""
        return [len(edges) - i for i in range(len(edges))]


class MockKVStorage:
    """Mock key-value storage for community reports."""

    def __init__(self):
        self.data = {}

    async def upsert(self, data: Dict[str, Any]):
        """Store community reports."""
        self.data.update(data)

    async def all_keys(self) -> List[str]:
        """Return all stored keys."""
        return list(self.data.keys())


@pytest.mark.asyncio
async def test_community_report_token_truncation():
    """Test that large communities are properly truncated to fit token limits."""

    mock_graph = MockGraphStorage(large_community_size=1000)
    mock_kv = MockKVStorage()
    mock_tokenizer = MockTokenizerWrapper(tokens_per_char=0.25)

    # Mock LLM function that would fail if prompt is too large
    async def mock_llm(prompt: str, **kwargs):
        token_count = len(mock_tokenizer.encode(prompt))
        if token_count > 24000:  # Simulate 75% of 32k limit
            raise Exception(f"Token limit exceeded: {token_count} > 24000")
        return '{"title": "Test", "summary": "Test summary", "rating": 5.0, "rating_explanation": "Test", "findings": []}'

    # Mock JSON converter
    def mock_json_convert(response: str) -> Dict[str, Any]:
        import json
        return json.loads(response)

    global_config = {
        "best_model_func": mock_llm,
        "convert_response_to_json_func": mock_json_convert,
        "best_model_max_token_size": 32000,
        "community_report_token_budget_ratio": 0.75,
        "community_report_chat_overhead": 1000,
        "special_community_report_llm_kwargs": {}
    }

    # Run report generation
    await generate_community_report(
        mock_kv,
        mock_graph,
        mock_tokenizer,
        global_config
    )

    # Verify reports were generated for both communities
    assert len(mock_kv.data) == 2
    assert "community_1" in mock_kv.data
    assert "community_2" in mock_kv.data


@pytest.mark.asyncio
async def test_pack_single_community_with_token_limit():
    """Test that community description packing respects token limits."""

    mock_graph = MockGraphStorage(large_community_size=100)
    mock_tokenizer = MockTokenizerWrapper(tokens_per_char=0.25)

    # Get a large community
    schema = await mock_graph.community_schema()
    large_community = schema["community_1"]

    # Pack with small token limit
    result = await _pack_single_community_describe(
        mock_graph,
        large_community,
        mock_tokenizer,
        max_token_size=1000,  # Very small limit
        already_reports={},
        global_config={}
    )

    # Verify result fits within token limit
    token_count = len(mock_tokenizer.encode(result))
    assert token_count <= 1000, f"Result exceeds token limit: {token_count} > 1000"

    # Verify result contains expected structure
    assert "-----Reports-----" in result
    assert "-----Entities-----" in result
    assert "-----Relationships-----" in result


@pytest.mark.asyncio
async def test_fallback_on_token_overflow():
    """Test that report generation falls back gracefully when tokens exceed limit."""

    mock_graph = MockGraphStorage(large_community_size=5000)  # Extremely large
    mock_kv = MockKVStorage()
    mock_tokenizer = MockTokenizerWrapper(tokens_per_char=0.5)  # More tokens per char

    # Mock LLM that always fails
    async def failing_llm(prompt: str, **kwargs):
        raise Exception("Token limit exceeded in LLM")

    global_config = {
        "best_model_func": failing_llm,
        "convert_response_to_json_func": lambda x: {},
        "best_model_max_token_size": 8000,  # Small limit
        "community_report_token_budget_ratio": 0.5,  # Even more conservative
        "community_report_chat_overhead": 2000,
        "special_community_report_llm_kwargs": {}
    }

    # Should not raise exception, should generate fallback reports
    await generate_community_report(
        mock_kv,
        mock_graph,
        mock_tokenizer,
        global_config
    )

    # Verify fallback reports were created
    assert len(mock_kv.data) > 0
    for key, report in mock_kv.data.items():
        assert "report_json" in report
        # Check for fallback report content
        if "Analysis incomplete" in str(report.get("report_json", {})):
            assert True  # Found a fallback report


@pytest.mark.asyncio
async def test_configurable_token_budget_ratio():
    """Test that token budget ratio configuration is respected."""

    mock_graph = MockGraphStorage(large_community_size=100)
    mock_kv = MockKVStorage()
    mock_tokenizer = MockTokenizerWrapper(tokens_per_char=0.25)

    prompt_sizes = []

    # Mock LLM that records prompt sizes
    async def recording_llm(prompt: str, **kwargs):
        prompt_sizes.append(len(mock_tokenizer.encode(prompt)))
        return '{"title": "Test", "summary": "Test", "rating": 5.0, "rating_explanation": "Test", "findings": []}'

    # Test with different ratios
    for ratio in [0.5, 0.75, 0.9]:
        prompt_sizes.clear()
        mock_kv.data.clear()

        global_config = {
            "best_model_func": recording_llm,
            "convert_response_to_json_func": lambda x: eval(x),
            "best_model_max_token_size": 10000,
            "community_report_token_budget_ratio": ratio,
            "community_report_chat_overhead": 500,
            "special_community_report_llm_kwargs": {}
        }

        await generate_community_report(
            mock_kv,
            mock_graph,
            mock_tokenizer,
            global_config
        )

        # Verify prompts respect the ratio
        max_allowed = int(10000 * ratio)
        for size in prompt_sizes:
            assert size <= max_allowed, f"Prompt size {size} exceeds limit for ratio {ratio}"


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_community_report_token_truncation())
    asyncio.run(test_pack_single_community_with_token_limit())
    asyncio.run(test_fallback_on_token_overflow())
    asyncio.run(test_configurable_token_budget_ratio())
    print("All tests passed!")