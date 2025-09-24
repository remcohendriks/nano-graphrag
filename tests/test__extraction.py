"""Test entity and relationship extraction with NDJSON format."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from nano_graphrag._extraction import (
    _handle_entity_relation_summary,
    extract_entities_from_chunks
)
from nano_graphrag._utils import TokenizerWrapper


@pytest.fixture
def tokenizer():
    """Create tokenizer fixture."""
    return TokenizerWrapper(tokenizer_type="tiktoken", model_name="gpt-4o")


@pytest.fixture
def mock_global_config():
    """Create mock global config."""
    return {
        "cheap_model_func": AsyncMock(return_value="Summarized description"),
        "cheap_model_max_token_size": 4000,
        "entity_summary_to_max_tokens": 200,
        "best_model_func": AsyncMock(),
        "entity_extract_max_gleaning": 1
    }


class TestExtraction:
    @pytest.mark.asyncio
    async def test_handle_entity_relation_summary(self, mock_global_config, tokenizer):
        """Test entity/relation summary generation."""
        entity_name = "TEST_ENTITY"
        short_description = "Short description"

        # Test short description (no summary needed)
        result = await _handle_entity_relation_summary(
            entity_name, short_description,
            mock_global_config, tokenizer
        )
        assert result == short_description
        mock_global_config["cheap_model_func"].assert_not_called()

        # Test long description (summary needed)
        long_description = "Very long description " * 100
        result = await _handle_entity_relation_summary(
            entity_name, long_description,
            mock_global_config, tokenizer
        )
        assert result == "Summarized description"
        mock_global_config["cheap_model_func"].assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_entities_from_chunks(self, tokenizer):
        """Test entity extraction from chunks with NDJSON format."""
        chunks = [
            {"content": "John works at Microsoft."},
            {"content": "Mary knows John."}
        ]

        # Mock LLM response with entities and relationships in NDJSON format
        mock_response = '''{"type":"entity","name":"JOHN","entity_type":"PERSON","description":"John is a person"}
{"type":"entity","name":"MICROSOFT","entity_type":"ORGANIZATION","description":"Microsoft is a company"}
{"type":"relationship","source":"JOHN","target":"MICROSOFT","description":"works at"}
{"type":"entity","name":"MARY","entity_type":"PERSON","description":"Mary is a person"}
{"type":"relationship","source":"MARY","target":"JOHN","description":"knows"}
<|COMPLETE|>'''

        mock_llm = AsyncMock(return_value=mock_response)

        result = await extract_entities_from_chunks(
            chunks, mock_llm, tokenizer,
            max_gleaning=0,  # No additional gleaning
            summary_max_tokens=500
        )

        assert "nodes" in result
        assert "edges" in result
        assert len(result["nodes"]) == 3  # John, Microsoft, Mary
        assert len(result["edges"]) >= 2  # At least the 2 unique relationships

        # Check node structure
        node_names = {n["name"] for n in result["nodes"]}
        assert "JOHN" in node_names
        assert "MICROSOFT" in node_names
        assert "MARY" in node_names

        # Check edge structure
        edge_pairs = {(e["source"], e["target"]) for e in result["edges"]}
        assert ("JOHN", "MICROSOFT") in edge_pairs
        assert ("MARY", "JOHN") in edge_pairs

    @pytest.mark.asyncio
    async def test_extract_entities_empty_response(self, tokenizer):
        """Test extraction with empty LLM response."""
        chunks = [{"content": "Test content"}]
        mock_llm = AsyncMock(return_value="")

        result = await extract_entities_from_chunks(
            chunks, mock_llm, tokenizer
        )

        assert result["nodes"] == []
        assert result["edges"] == []

    @pytest.mark.asyncio
    async def test_extract_entities_malformed_response(self, tokenizer):
        """Test extraction with malformed NDJSON response."""
        chunks = [{"content": "Test content"}]

        # Response with malformed NDJSON entries
        mock_response = '''{"type":"entity","name":"JOHN"
NOT_JSON_AT_ALL
{"type":"entity","name":"VALID","entity_type":"PERSON","description":"Valid entity"}
<|COMPLETE|>'''

        mock_llm = AsyncMock(return_value=mock_response)

        result = await extract_entities_from_chunks(
            chunks, mock_llm, tokenizer
        )

        # Should only extract the valid entity
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["name"] == "VALID"

    @pytest.mark.asyncio
    async def test_extract_with_gleaning(self, tokenizer):
        """Test extraction with gleaning iterations in NDJSON format."""
        chunks = [{"content": "Test content"}]

        # First response in NDJSON format
        first_response = '{"type":"entity","name":"ENTITY1","entity_type":"TYPE","description":"Description1"}'
        # Gleaning response in NDJSON format
        glean_response = '{"type":"entity","name":"ENTITY2","entity_type":"TYPE","description":"Description2"}'

        call_count = 0
        async def mock_llm_func(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return first_response
            else:
                return glean_response

        result = await extract_entities_from_chunks(
            chunks, mock_llm_func, tokenizer,
            max_gleaning=1  # One gleaning iteration
        )

        # Should have both entities from initial and gleaning responses
        assert len(result["nodes"]) == 2
        entity_names = {n["name"] for n in result["nodes"]}
        assert "ENTITY1" in entity_names
        assert "ENTITY2" in entity_names