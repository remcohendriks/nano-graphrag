"""Mock entity extractors for testing."""

from typing import Dict, Optional, Any
from nano_graphrag.entity_extraction.base import (
    BaseEntityExtractor,
    ExtractorConfig,
    ExtractionResult,
    TextChunkSchema
)


class MockEntityExtractor(BaseEntityExtractor):
    """Mock extractor with predictable output for testing."""

    async def _initialize_impl(self):
        """No initialization needed for mock."""
        pass

    async def extract(
        self,
        chunks: Dict[str, TextChunkSchema],
        storage: Optional[Any] = None
    ) -> ExtractionResult:
        """Extract entities with predictable pattern."""
        nodes = {}
        edges = []

        for chunk_id, chunk_data in chunks.items():
            # Create predictable entities
            nodes[f"ENTITY_{chunk_id}"] = {
                "entity_name": f"ENTITY_{chunk_id}",
                "entity_type": "PERSON",
                "description": f"Mock entity from {chunk_id}",
                "source_id": chunk_id
            }

            # Create predictable relationships
            if len(nodes) > 1:
                edges.append((
                    f"ENTITY_{chunk_id}",
                    list(nodes.keys())[0],
                    {
                        "weight": 1.0,
                        "description": "Mock relationship",
                        "source_id": chunk_id
                    }
                ))

        return ExtractionResult(nodes=nodes, edges=edges)

    async def extract_single(
        self,
        text: str,
        chunk_id: Optional[str] = None
    ) -> ExtractionResult:
        """Extract from single text with predictable output."""
        chunk_id = chunk_id or "mock_chunk"

        nodes = {
            f"ENTITY_{chunk_id}": {
                "entity_name": f"ENTITY_{chunk_id}",
                "entity_type": "PERSON",
                "description": f"Mock entity from {chunk_id}",
                "source_id": chunk_id
            }
        }

        edges = []
        if "relationship" in text.lower():
            edges.append((
                f"ENTITY_{chunk_id}",
                "ENTITY_OTHER",
                {
                    "weight": 1.0,
                    "description": "Mock relationship",
                    "source_id": chunk_id
                }
            ))

        return ExtractionResult(
            nodes=nodes,
            edges=edges,
            metadata={"chunk_id": chunk_id, "method": "mock"}
        )


class EmptyEntityExtractor(BaseEntityExtractor):
    """Mock extractor that returns empty results."""

    async def _initialize_impl(self):
        """No initialization needed."""
        pass

    async def extract(
        self,
        chunks: Dict[str, TextChunkSchema],
        storage: Optional[Any] = None
    ) -> ExtractionResult:
        """Return empty extraction result."""
        return ExtractionResult(nodes={}, edges=[])

    async def extract_single(
        self,
        text: str,
        chunk_id: Optional[str] = None
    ) -> ExtractionResult:
        """Return empty extraction result."""
        return ExtractionResult(nodes={}, edges=[])


class ErrorEntityExtractor(BaseEntityExtractor):
    """Mock extractor that raises errors for testing error handling."""

    async def _initialize_impl(self):
        """Initialization that might fail."""
        if self.config.strategy_params.get("fail_on_init"):
            raise RuntimeError("Initialization failed as requested")

    async def extract(
        self,
        chunks: Dict[str, TextChunkSchema],
        storage: Optional[Any] = None
    ) -> ExtractionResult:
        """Raise error during extraction."""
        raise RuntimeError("Extraction failed as expected")

    async def extract_single(
        self,
        text: str,
        chunk_id: Optional[str] = None
    ) -> ExtractionResult:
        """Raise error during single extraction."""
        raise RuntimeError("Single extraction failed as expected")