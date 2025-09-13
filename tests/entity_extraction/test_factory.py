"""Tests for entity extractor factory."""

import pytest
from unittest.mock import AsyncMock
from nano_graphrag.entity_extraction.factory import create_extractor
from nano_graphrag.entity_extraction.llm import LLMEntityExtractor
from nano_graphrag.entity_extraction.dspy_extractor import DSPyEntityExtractor
from nano_graphrag.entity_extraction.base import BaseEntityExtractor


class TestExtractorFactory:
    """Test entity extractor factory."""

    def test_create_llm_extractor(self):
        """Test creating LLM extractor."""
        mock_model_func = AsyncMock(return_value="test response")

        extractor = create_extractor(
            strategy="llm",
            model_func=mock_model_func,
            entity_types=["PERSON", "LOCATION"],
            max_gleaning=2
        )

        assert isinstance(extractor, LLMEntityExtractor)
        assert extractor.config.model_func == mock_model_func
        assert extractor.config.entity_types == ["PERSON", "LOCATION"]
        assert extractor.config.max_gleaning == 2

    def test_create_dspy_extractor(self):
        """Test creating DSPy extractor."""
        mock_model_func = AsyncMock(return_value="test response")

        extractor = create_extractor(
            strategy="dspy",
            model_func=mock_model_func,
            model_name="gpt-5-mini",
            num_refine_turns=2,
            self_refine=False
        )

        assert isinstance(extractor, DSPyEntityExtractor)
        assert extractor.config.model_func == mock_model_func
        assert extractor.config.model_name == "gpt-5-mini"
        assert extractor.config.strategy_params["num_refine_turns"] == 2
        assert extractor.config.strategy_params["self_refine"] == False

    def test_create_custom_extractor(self):
        """Test creating custom extractor."""
        extractor = create_extractor(
            strategy="custom",
            custom_extractor_class="tests.entity_extraction.mock_extractors.MockEntityExtractor"
        )

        assert isinstance(extractor, BaseEntityExtractor)
        # Should be instance of MockEntityExtractor
        assert extractor.__class__.__name__ == "MockEntityExtractor"

    def test_invalid_strategy(self):
        """Test invalid strategy raises error."""
        with pytest.raises(ValueError, match="Unknown extraction strategy"):
            create_extractor(strategy="invalid")

    def test_invalid_custom_class(self):
        """Test invalid custom class raises error."""
        with pytest.raises(ValueError, match="Failed to load custom extractor"):
            create_extractor(
                strategy="custom",
                custom_extractor_class="non.existent.Class"
            )

    def test_default_entity_types(self):
        """Test default entity types are set correctly."""
        mock_model_func = AsyncMock()

        extractor = create_extractor(
            strategy="llm",
            model_func=mock_model_func
        )

        assert extractor.config.entity_types == [
            "PERSON", "ORGANIZATION", "LOCATION", "EVENT", "CONCEPT"
        ]

    def test_strategy_case_insensitive(self):
        """Test strategy is case insensitive."""
        mock_model_func = AsyncMock()

        extractor1 = create_extractor(strategy="LLM", model_func=mock_model_func)
        extractor2 = create_extractor(strategy="llm", model_func=mock_model_func)

        assert isinstance(extractor1, LLMEntityExtractor)
        assert isinstance(extractor2, LLMEntityExtractor)