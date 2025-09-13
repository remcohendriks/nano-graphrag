"""Tests for base entity extraction abstraction."""

import pytest
from nano_graphrag.entity_extraction.base import (
    BaseEntityExtractor,
    ExtractorConfig,
    ExtractionResult
)
from .mock_extractors import MockEntityExtractor, EmptyEntityExtractor


class TestExtractionResult:
    """Test ExtractionResult dataclass."""

    def test_create_extraction_result(self):
        """Test creating extraction result."""
        nodes = {"ENTITY1": {"type": "PERSON", "description": "Test"}}
        edges = [("ENTITY1", "ENTITY2", {"relation": "knows"})]

        result = ExtractionResult(nodes=nodes, edges=edges)

        assert result.nodes == nodes
        assert result.edges == edges
        assert result.metadata == {}

    def test_merge_extraction_results(self):
        """Test merging two extraction results."""
        result1 = ExtractionResult(
            nodes={"E1": {"type": "PERSON"}},
            edges=[("E1", "E2", {"relation": "knows"})],
            metadata={"source": "chunk1"}
        )

        result2 = ExtractionResult(
            nodes={"E3": {"type": "LOCATION"}},
            edges=[("E3", "E4", {"relation": "located_in"})],
            metadata={"source": "chunk2"}
        )

        merged = result1.merge(result2)

        assert len(merged.nodes) == 2
        assert "E1" in merged.nodes
        assert "E3" in merged.nodes
        assert len(merged.edges) == 2


class TestExtractorConfig:
    """Test ExtractorConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ExtractorConfig()

        assert config.entity_types == ["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "CONCEPT"]
        assert config.max_entities_per_chunk == 20
        assert config.max_relationships_per_chunk == 30
        assert config.max_gleaning == 1
        assert config.summary_max_tokens == 500

    def test_custom_config(self):
        """Test custom configuration."""
        config = ExtractorConfig(
            entity_types=["CUSTOM_TYPE"],
            max_entities_per_chunk=10,
            model_func=lambda x: x
        )

        assert config.entity_types == ["CUSTOM_TYPE"]
        assert config.max_entities_per_chunk == 10
        assert config.model_func is not None


class TestBaseEntityExtractor:
    """Test base entity extractor functionality."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test extractor initialization."""
        config = ExtractorConfig()
        extractor = MockEntityExtractor(config)

        assert not extractor._initialized
        await extractor.initialize()
        assert extractor._initialized

        # Second initialization should be no-op
        await extractor.initialize()
        assert extractor._initialized

    @pytest.mark.asyncio
    async def test_extract_single(self):
        """Test single chunk extraction."""
        config = ExtractorConfig()
        extractor = MockEntityExtractor(config)
        await extractor.initialize()

        result = await extractor.extract_single("Test text", chunk_id="chunk1")

        assert len(result.nodes) == 1
        assert "ENTITY_chunk1" in result.nodes
        assert result.metadata["chunk_id"] == "chunk1"

    @pytest.mark.asyncio
    async def test_batch_extract(self):
        """Test batch extraction."""
        config = ExtractorConfig()
        extractor = MockEntityExtractor(config)
        await extractor.initialize()

        chunks = {
            "chunk1": {"content": "Text 1"},
            "chunk2": {"content": "Text 2"},
            "chunk3": {"content": "Text 3"}
        }

        results = await extractor.batch_extract(chunks, batch_size=2)

        assert len(results) == 3
        assert all(isinstance(r, ExtractionResult) for r in results)

    @pytest.mark.asyncio
    async def test_deduplicate_entities(self):
        """Test entity deduplication."""
        result1 = ExtractionResult(
            nodes={
                "ENTITY1": {"entity_name": "ENTITY1", "description": "Desc 1"},
                "ENTITY2": {"entity_name": "ENTITY2", "description": "Desc 2"}
            },
            edges=[("ENTITY1", "ENTITY2", {"relation": "knows"})]
        )

        result2 = ExtractionResult(
            nodes={
                "ENTITY1": {"entity_name": "ENTITY1", "description": "Desc 1 alt"},
                "ENTITY3": {"entity_name": "ENTITY3", "description": "Desc 3"}
            },
            edges=[
                ("ENTITY1", "ENTITY3", {"relation": "works_with"}),
                ("ENTITY1", "ENTITY2", {"relation": "knows"})  # Duplicate
            ]
        )

        deduplicated = BaseEntityExtractor.deduplicate_entities([result1, result2])

        # Should have 3 unique entities
        assert len(deduplicated.nodes) == 3
        assert "ENTITY1" in deduplicated.nodes
        assert "ENTITY2" in deduplicated.nodes
        assert "ENTITY3" in deduplicated.nodes

        # Should have 2 unique edges (one duplicate removed)
        assert len(deduplicated.edges) == 2

    @pytest.mark.asyncio
    async def test_empty_extraction(self):
        """Test extraction with empty results."""
        config = ExtractorConfig()
        extractor = EmptyEntityExtractor(config)
        await extractor.initialize()

        chunks = {"chunk1": {"content": "Test"}}
        result = await extractor.extract(chunks)

        assert len(result.nodes) == 0
        assert len(result.edges) == 0