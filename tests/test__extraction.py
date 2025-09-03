"""Test entity and relationship extraction."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from nano_graphrag._extraction import (
    _handle_entity_relation_summary,
    _handle_single_entity_extraction,
    _handle_single_relationship_extraction,
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
    async def test_handle_single_entity_extraction(self):
        """Test single entity extraction from attributes."""
        # Valid entity
        attributes = ['"entity"', 'PERSON_NAME', 'PERSON', 'A test person']
        chunk_key = "chunk-123"
        
        result = await _handle_single_entity_extraction(attributes, chunk_key)
        assert result is not None
        assert result["entity_name"] == "PERSON_NAME"
        assert result["entity_type"] == "PERSON"
        assert result["description"] == "A test person"
        assert result["source_id"] == "chunk-123"
        
        # Invalid entity (not enough attributes)
        attributes = ['"entity"', 'NAME']
        result = await _handle_single_entity_extraction(attributes, chunk_key)
        assert result is None
        
        # Invalid entity (wrong type)
        attributes = ['"relationship"', 'NAME', 'TYPE', 'DESC']
        result = await _handle_single_entity_extraction(attributes, chunk_key)
        assert result is None
        
    @pytest.mark.asyncio
    async def test_handle_single_relationship_extraction(self):
        """Test single relationship extraction from attributes."""
        # Valid relationship
        attributes = ['"relationship"', 'ENTITY1', 'ENTITY2', 'knows', '0.8']
        chunk_key = "chunk-123"
        
        result = await _handle_single_relationship_extraction(attributes, chunk_key)
        assert result is not None
        assert result["src_id"] == "ENTITY1"
        assert result["tgt_id"] == "ENTITY2"
        assert result["description"] == "knows"
        assert result["weight"] == 0.8
        assert result["source_id"] == "chunk-123"
        
        # Relationship without weight
        attributes = ['"relationship"', 'ENTITY1', 'ENTITY2', 'knows', 'invalid']
        result = await _handle_single_relationship_extraction(attributes, chunk_key)
        assert result is not None
        assert result["weight"] == 1.0  # Default weight
        
        # Invalid relationship
        attributes = ['"entity"', 'E1', 'E2', 'desc']
        result = await _handle_single_relationship_extraction(attributes, chunk_key)
        assert result is None
        
    @pytest.mark.asyncio
    async def test_extract_entities_from_chunks(self, tokenizer):
        """Test entity extraction from chunks."""
        chunks = [
            {"content": "John works at Microsoft."},
            {"content": "Mary knows John."}
        ]
        
        # Mock LLM response with entities and relationships
        mock_response = '''
        ("entity"<|>JOHN<|>PERSON<|>John is a person)
        ##
        ("entity"<|>MICROSOFT<|>ORGANIZATION<|>Microsoft is a company)
        ##
        ("relationship"<|>JOHN<|>MICROSOFT<|>works at)
        ##
        ("entity"<|>MARY<|>PERSON<|>Mary is a person)
        ##
        ("relationship"<|>MARY<|>JOHN<|>knows)
        '''
        
        mock_llm = AsyncMock(return_value=mock_response)
        
        result = await extract_entities_from_chunks(
            chunks, mock_llm, tokenizer,
            max_gleaning=0,  # No additional gleaning
            summary_max_tokens=500
        )
        
        assert "nodes" in result
        assert "edges" in result
        assert len(result["nodes"]) == 3  # John, Microsoft, Mary
        # With 2 chunks, relationships may be extracted from each chunk
        # Since we're mocking the same response for all chunks, we get duplicates
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
        """Test extraction with malformed LLM response."""
        chunks = [{"content": "Test content"}]
        
        # Response with malformed entries
        mock_response = '''
        ("entity"JOHN<|>PERSON<|>Description)  # Missing delimiter
        ##
        (entity<|>MARY<|>PERSON<|>Description)  # Missing quotes
        ##
        ("entity"<|>VALID<|>PERSON<|>Valid entity)  # Valid entry
        '''
        
        mock_llm = AsyncMock(return_value=mock_response)
        
        result = await extract_entities_from_chunks(
            chunks, mock_llm, tokenizer
        )
        
        # Should only extract the valid entity
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["name"] == "VALID"
        
    @pytest.mark.asyncio
    async def test_extract_with_gleaning(self, tokenizer):
        """Test extraction with gleaning iterations."""
        chunks = [{"content": "Test content"}]
        
        # First response
        first_response = '("entity"<|>ENTITY1<|>TYPE<|>Description1)'
        # Gleaning response
        glean_response = '("entity"<|>ENTITY2<|>TYPE<|>Description2)'
        
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
        
        # Should have both entities now that we accumulate
        assert len(result["nodes"]) == 2  # Now accumulates both entities
        # Check both entities are present
        entity_names = {n["name"] for n in result["nodes"]}
        assert "ENTITY1" in entity_names
        assert "ENTITY2" in entity_names