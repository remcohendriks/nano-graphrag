"""Test that custom entity types are properly used in the system."""

import pytest
import os
import json
from unittest.mock import patch

from nano_graphrag.config import GraphRAGConfig, EntityExtractionConfig
from nano_graphrag.graphrag import GraphRAG


def test_entity_types_flow_through_system():
    """Test that custom entity types flow from config to extractor."""
    with patch.dict(os.environ, {
        "ENTITY_TYPES": "DRUG,DISEASE,PROTEIN",
        "RELATION_PATTERNS": json.dumps({"inhibits": "INHIBITS", "treats": "TREATS"})
    }):
        # Create config with custom types
        config = GraphRAGConfig(
            entity_extraction=EntityExtractionConfig.from_env()
        )

        # Verify config has custom types
        assert config.entity_extraction.entity_types == ["DRUG", "DISEASE", "PROTEIN"]

        # Create GraphRAG instance
        rag = GraphRAG(config)
        rag._init_extractor()

        # Verify extractor receives custom types
        assert rag.entity_extractor.config.entity_types == ["DRUG", "DISEASE", "PROTEIN"]


def test_relation_patterns_from_env():
    """Test that relation patterns are loaded from environment."""
    from nano_graphrag._extraction import get_relation_patterns, map_relation_type

    with patch.dict(os.environ, {
        "RELATION_PATTERNS": json.dumps({
            "inhibits": "INHIBITS",
            "activates": "ACTIVATES",
            "binds to": "BINDS_TO"
        })
    }):
        patterns = get_relation_patterns()
        assert "inhibits" in patterns
        assert patterns["inhibits"] == "INHIBITS"

        # Test mapping
        assert map_relation_type("Drug X inhibits enzyme Y") == "INHIBITS"
        assert map_relation_type("Protein A activates pathway B") == "ACTIVATES"
        assert map_relation_type("Molecule binds to receptor") == "BINDS_TO"