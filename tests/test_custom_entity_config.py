"""Tests for custom entity type configuration."""

import pytest
import os
from unittest.mock import patch

from nano_graphrag.config import EntityExtractionConfig


class TestCustomEntityTypes:
    """Test custom entity type configuration."""

    def test_entity_types_from_env(self):
        """Test entity types can be configured from environment."""
        # Test with mixed case to verify uppercasing
        with patch.dict(os.environ, {"ENTITY_TYPES": "executive_order,Statute,REGULATION"}):
            config = EntityExtractionConfig.from_env()
            assert config.entity_types == ["EXECUTIVE_ORDER", "STATUTE", "REGULATION"]

    def test_entity_types_default(self):
        """Test default entity types are provided."""
        config = EntityExtractionConfig()
        assert "PERSON" in config.entity_types
        assert "ORGANIZATION" in config.entity_types
        assert len(config.entity_types) == 10

    def test_entity_types_empty_env(self):
        """Test empty env var uses defaults."""
        with patch.dict(os.environ, {"ENTITY_TYPES": ""}):
            config = EntityExtractionConfig.from_env()
            assert "PERSON" in config.entity_types
            assert len(config.entity_types) == 10

    def test_entity_types_medical_domain(self):
        """Test medical domain entity types."""
        with patch.dict(os.environ, {"ENTITY_TYPES": "DRUG,DISEASE,SYMPTOM,PROTEIN,GENE"}):
            config = EntityExtractionConfig.from_env()
            assert config.entity_types == ["DRUG", "DISEASE", "SYMPTOM", "PROTEIN", "GENE"]

    def test_entity_types_financial_domain(self):
        """Test financial domain entity types."""
        with patch.dict(os.environ, {"ENTITY_TYPES": "COMPANY,EXECUTIVE,INVESTOR,TRANSACTION"}):
            config = EntityExtractionConfig.from_env()
            assert config.entity_types == ["COMPANY", "EXECUTIVE", "INVESTOR", "TRANSACTION"]