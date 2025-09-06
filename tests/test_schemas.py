"""Tests for TypedDict schemas and validation functions."""

import pytest
import numpy as np
from typing import Dict, Any

from nano_graphrag.schemas import (
    # Storage schemas
    NodeData,
    EdgeData,
    # View schemas
    NodeView,
    EdgeView,
    # Extraction schemas
    EntityExtractionResult,
    ExtractionRecord,
    RelationshipRecord,
    # Query schemas
    QueryContext,
    LocalQueryContext,
    GlobalQueryContext,
    # LLM schemas
    LLMMessage,
    BedrockMessage,
    # Embedding schemas
    EmbeddingResult,
    EmbeddingResponse,
    # Community schemas
    CommunityNodeInfo,
    CommunityEdgeInfo,
    CommunityReportData,
    # Validators
    is_valid_node_data,
    is_valid_edge_data,
    is_valid_llm_message,
    validate_extraction_record,
    validate_relationship_record,
    # Utilities
    parse_source_id,
    build_source_id,
)


class TestNodeSchemas:
    """Test node-related schemas."""
    
    def test_node_data_creation(self):
        """Test creating valid NodeData."""
        node: NodeData = {
            "entity_type": "Person",
            "description": "A test entity",
            "source_id": "chunk1<SEP>chunk2"
        }
        
        assert node["entity_type"] == "Person"
        assert node["description"] == "A test entity"
        assert node["source_id"] == "chunk1<SEP>chunk2"
    
    def test_node_view_creation(self):
        """Test creating valid NodeView."""
        node: NodeView = {
            "id": "node1",
            "entity_type": "Organization",
            "description": "A company",
            "source_chunks": ["chunk1", "chunk2"]
        }
        
        assert node["id"] == "node1"
        assert node["entity_type"] == "Organization"
        assert len(node["source_chunks"]) == 2
    
    def test_node_data_validation(self):
        """Test node validation function."""
        valid_node = {"entity_type": "Test"}
        empty_dict = {}
        invalid_node = {"unknown_field": "value"}
        
        # Only accepts dicts with valid NodeData fields
        assert is_valid_node_data(valid_node) is True
        assert is_valid_node_data(empty_dict) is True  # Empty is valid
        assert is_valid_node_data(invalid_node) is False  # Unknown field
        assert is_valid_node_data(None) is False


class TestEdgeSchemas:
    """Test edge-related schemas."""
    
    def test_edge_data_creation(self):
        """Test creating valid EdgeData."""
        edge: EdgeData = {
            "weight": 0.9,
            "description": "Works with",
            "source_id": "chunk1",
            "order": 1
        }
        
        assert edge["weight"] == 0.9
        assert edge["description"] == "Works with"
        assert edge["order"] == 1
    
    def test_edge_view_creation(self):
        """Test creating valid EdgeView."""
        edge: EdgeView = {
            "source": "node1",
            "target": "node2",
            "relationship": "KNOWS",
            "weight": 0.8,
            "description": "They know each other",
            "source_chunks": ["chunk1"]
        }
        
        assert edge["source"] == "node1"
        assert edge["target"] == "node2"
        assert edge["relationship"] == "KNOWS"
    
    def test_edge_data_validation(self):
        """Test edge validation function."""
        valid_edge = {"weight": 1.0}
        empty_dict = {}
        invalid_edge = {"unknown_field": "value"}
        
        # Only accepts dicts with valid EdgeData fields
        assert is_valid_edge_data(valid_edge) is True
        assert is_valid_edge_data(empty_dict) is True  # Empty is valid
        assert is_valid_edge_data(invalid_edge) is False  # Unknown field
        assert is_valid_edge_data(None) is False


class TestExtractionSchemas:
    """Test extraction-related schemas."""
    
    def test_entity_extraction_result(self):
        """Test EntityExtractionResult structure."""
        result: EntityExtractionResult = {
            "entities": [{"entity_name": "Test"}],
            "relationships": [{"source": "A", "target": "B"}],
            "chunk_id": "chunk1"
        }
        
        assert len(result["entities"]) == 1
        assert len(result["relationships"]) == 1
        assert result["chunk_id"] == "chunk1"
    
    def test_extraction_record_validation(self):
        """Test validate_extraction_record function."""
        valid_record = {
            "entity_name": "Test Entity",
            "entity_type": "Person",
            "description": "A test",
            "importance_score": 0.9
        }
        
        result = validate_extraction_record(valid_record)
        assert result["entity_name"] == "Test Entity"
        assert result["importance_score"] == 0.9
        
        # Test with missing optional fields
        minimal_record = {"entity_name": "Test"}
        result = validate_extraction_record(minimal_record)
        assert result["entity_type"] == ""
        assert result["importance_score"] == 0.0
        
        # Test invalid record
        invalid_record = {"no_name": "Test"}
        with pytest.raises(ValueError):
            validate_extraction_record(invalid_record)
    
    def test_relationship_record_validation(self):
        """Test validate_relationship_record function."""
        valid_record = {
            "source_entity": "Entity A",
            "target_entity": "Entity B",
            "relationship_description": "Works with",
            "weight": 0.8,
            "order": 2
        }
        
        result = validate_relationship_record(valid_record)
        assert result["source_entity"] == "Entity A"
        assert result["weight"] == 0.8
        assert result["order"] == 2
        
        # Test with missing optional fields
        minimal_record = {
            "source_entity": "A",
            "target_entity": "B"
        }
        result = validate_relationship_record(minimal_record)
        assert result["relationship_description"] == ""
        assert result["weight"] == 1.0
        assert result["order"] == 0
        
        # Test invalid records
        with pytest.raises(ValueError):
            validate_relationship_record({"source_entity": "A"})
        
        with pytest.raises(ValueError):
            validate_relationship_record({"target_entity": "B"})


class TestQuerySchemas:
    """Test query-related schemas."""
    
    def test_query_context_creation(self):
        """Test QueryContext structure."""
        context: QueryContext = {
            "query": "What is the relationship?",
            "entities": [],
            "relationships": [],
            "chunks": [],
            "communities": []
        }
        
        assert context["query"] == "What is the relationship?"
        assert len(context["entities"]) == 0
    
    def test_local_query_context(self):
        """Test LocalQueryContext structure."""
        context: LocalQueryContext = {
            "query": "Local query",
            "entities": "Entity context",
            "relationships": "Relationship context",
            "chunks": "Chunk context",
            "community_reports": "Reports"
        }
        
        assert context["query"] == "Local query"
        assert context["entities"] == "Entity context"
    
    def test_global_query_context(self):
        """Test GlobalQueryContext structure."""
        context: GlobalQueryContext = {
            "query": "Global query",
            "community_reports": "All reports",
            "response_type": "detailed"
        }
        
        assert context["query"] == "Global query"
        assert context["response_type"] == "detailed"


class TestLLMSchemas:
    """Test LLM-related schemas."""
    
    def test_llm_message_creation(self):
        """Test LLMMessage structure."""
        message: LLMMessage = {
            "role": "user",
            "content": "Hello"
        }
        
        assert message["role"] == "user"
        assert message["content"] == "Hello"
    
    def test_llm_message_validation(self):
        """Test is_valid_llm_message function."""
        valid_message = {"role": "system", "content": "You are helpful"}
        assert is_valid_llm_message(valid_message) is True
        
        valid_roles = ["system", "user", "assistant"]
        for role in valid_roles:
            msg = {"role": role, "content": "test"}
            assert is_valid_llm_message(msg) is True
        
        # Invalid cases
        assert is_valid_llm_message({"role": "invalid", "content": "test"}) is False
        assert is_valid_llm_message({"role": "user"}) is False
        assert is_valid_llm_message({"content": "test"}) is False
        assert is_valid_llm_message("not a dict") is False
    
    def test_bedrock_message_creation(self):
        """Test BedrockMessage structure."""
        message: BedrockMessage = {
            "role": "user",
            "content": [{"text": "Hello"}]
        }
        
        assert message["role"] == "user"
        assert len(message["content"]) == 1
        assert message["content"][0]["text"] == "Hello"


class TestEmbeddingSchemas:
    """Test embedding-related schemas."""
    
    def test_embedding_result_creation(self):
        """Test EmbeddingResult structure."""
        embeddings = np.array([[0.1, 0.2, 0.3]])
        result: EmbeddingResult = {
            "embeddings": embeddings,
            "model": "text-embedding-3-small",
            "dimensions": 3,
            "usage": {"prompt_tokens": 10}
        }
        
        assert result["model"] == "text-embedding-3-small"
        assert result["dimensions"] == 3
        assert result["embeddings"].shape == (1, 3)
    
    def test_embedding_response_creation(self):
        """Test EmbeddingResponse structure."""
        embeddings = np.array([[0.1, 0.2]])
        response: EmbeddingResponse = {
            "embeddings": embeddings,
            "dimensions": 2,
            "model": "test-model",
            "usage": {"total_tokens": 20}
        }
        
        assert response["dimensions"] == 2
        assert response["usage"]["total_tokens"] == 20


class TestCommunitySchemas:
    """Test community-related schemas."""
    
    def test_community_node_info(self):
        """Test CommunityNodeInfo structure."""
        node_info: CommunityNodeInfo = {
            "entity": "Entity A",
            "type": "Person",
            "description": "A person",
            "rank": 0.9
        }
        
        assert node_info["entity"] == "Entity A"
        assert node_info["rank"] == 0.9
    
    def test_community_edge_info(self):
        """Test CommunityEdgeInfo structure."""
        edge_info: CommunityEdgeInfo = {
            "source": "A",
            "target": "B",
            "relationship": "KNOWS",
            "weight": 0.7
        }
        
        assert edge_info["source"] == "A"
        assert edge_info["weight"] == 0.7
    
    def test_community_report_data(self):
        """Test CommunityReportData structure."""
        report: CommunityReportData = {
            "title": "Community 1",
            "summary": "A test community",
            "rating": 8.5,
            "importance": 0.9,
            "findings": ["Finding 1", "Finding 2"]
        }
        
        assert report["title"] == "Community 1"
        assert len(report["findings"]) == 2
        assert report["rating"] == 8.5


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_parse_source_id(self):
        """Test parse_source_id function."""
        from nano_graphrag.prompt import GRAPH_FIELD_SEP
        
        # Default separator (uses GRAPH_FIELD_SEP)
        source_id = f"chunk1{GRAPH_FIELD_SEP}chunk2{GRAPH_FIELD_SEP}chunk3"
        result = parse_source_id(source_id)
        assert result == ["chunk1", "chunk2", "chunk3"]
        
        # Custom separator
        source_id = "chunk1|chunk2|chunk3"
        result = parse_source_id(source_id, separator="|")
        assert result == ["chunk1", "chunk2", "chunk3"]
        
        # Empty string
        assert parse_source_id("") == []
    
    def test_build_source_id(self):
        """Test build_source_id function."""
        from nano_graphrag.prompt import GRAPH_FIELD_SEP
        
        # Default separator (uses GRAPH_FIELD_SEP)
        chunks = ["chunk1", "chunk2", "chunk3"]
        result = build_source_id(chunks)
        assert result == f"chunk1{GRAPH_FIELD_SEP}chunk2{GRAPH_FIELD_SEP}chunk3"
        
        # Custom separator
        result = build_source_id(chunks, separator="|")
        assert result == "chunk1|chunk2|chunk3"
        
        # Empty list
        assert build_source_id([]) == ""


class TestTypeCompatibility:
    """Test that TypedDict schemas are compatible with existing code patterns."""
    
    def test_dict_assignment_compatibility(self):
        """Test that TypedDict can be assigned from regular dicts."""
        # This mimics how the actual code creates these structures
        node_data: NodeData = {
            "entity_type": "Person",
            "description": "Test"
        }
        
        # Can access fields
        assert "entity_type" in node_data
        assert node_data.get("source_id", "default") == "default"
        
        # Can update fields
        node_data["source_id"] = "chunk1"
        assert node_data["source_id"] == "chunk1"
    
    def test_optional_fields(self):
        """Test that optional fields work correctly."""
        # NodeData has all fields optional (total=False)
        minimal_node: NodeData = {}
        assert isinstance(minimal_node, dict)
        
        # Can add fields later
        minimal_node["entity_type"] = "Unknown"
        assert minimal_node["entity_type"] == "Unknown"
    
    def test_function_parameter_typing(self):
        """Test that functions can accept TypedDict parameters."""
        def process_node(node: NodeData) -> str:
            return node.get("entity_type", "Unknown")
        
        # Can pass regular dict
        result = process_node({"entity_type": "Person"})
        assert result == "Person"
        
        # Can pass minimal dict
        result = process_node({})
        assert result == "Unknown"