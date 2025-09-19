"""Tests for relation type mapping functionality."""

import pytest
import os
import json
from unittest.mock import patch

from nano_graphrag._extraction import map_relation_type, get_relation_patterns


class TestRelationTypeMapping:
    """Test relation type mapping functionality."""

    def test_relation_mapping_defaults(self):
        """Test default relation pattern mapping."""
        assert map_relation_type("This order supersedes EO 13800") == "SUPERSEDES"
        assert map_relation_type("It amends section 2") == "AMENDS"
        assert map_relation_type("The module depends on X") == "DEPENDS_ON"
        assert map_relation_type("unrelated text") == "RELATED"

    def test_relation_mapping_case_insensitive(self):
        """Test that pattern matching is case insensitive."""
        assert map_relation_type("This SUPERSEDES that") == "SUPERSEDES"
        assert map_relation_type("it IMPLEMENTS the policy") == "IMPLEMENTS"

    def test_custom_relation_patterns(self):
        """Test custom relation patterns from environment."""
        custom_patterns = {
            "inhibits": "INHIBITS",
            "activates": "ACTIVATES",
            "treats": "TREATS"
        }
        with patch.dict(os.environ, {"RELATION_PATTERNS": json.dumps(custom_patterns)}):
            patterns = get_relation_patterns()
            assert map_relation_type("Drug X inhibits protein Y", patterns) == "INHIBITS"
            assert map_relation_type("Gene A activates pathway B", patterns) == "ACTIVATES"
            assert map_relation_type("Medicine treats disease", patterns) == "TREATS"
            assert map_relation_type("unrelated interaction", patterns) == "RELATED"

    def test_invalid_json_patterns(self):
        """Test that invalid JSON falls back to defaults."""
        with patch.dict(os.environ, {"RELATION_PATTERNS": "not-valid-json"}):
            patterns = get_relation_patterns()
            # Should fall back to defaults
            assert "supersedes" in patterns
            assert "amends" in patterns

    def test_legal_domain_patterns(self):
        """Test legal domain relation patterns."""
        legal_patterns = {
            "cites": "CITES",
            "overrules": "OVERRULES",
            "affirms": "AFFIRMS",
            "supersedes": "SUPERSEDES"
        }
        assert map_relation_type("Case A cites Case B", legal_patterns) == "CITES"
        assert map_relation_type("This ruling overrules the previous", legal_patterns) == "OVERRULES"

    def test_software_domain_patterns(self):
        """Test software engineering relation patterns."""
        software_patterns = {
            "imports": "IMPORTS",
            "calls": "CALLS",
            "implements": "IMPLEMENTS",
            "extends": "EXTENDS"
        }
        assert map_relation_type("Module A imports Module B", software_patterns) == "IMPORTS"
        assert map_relation_type("Function X calls Function Y", software_patterns) == "CALLS"
        assert map_relation_type("Class implements interface", software_patterns) == "IMPLEMENTS"