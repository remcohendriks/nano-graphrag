"""Base interface for entity extraction strategies."""

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field
import asyncio
from collections import defaultdict

from nano_graphrag._utils import logger, clean_str
from nano_graphrag.base import BaseKVStorage, TextChunkSchema


@dataclass
class ExtractionResult:
    """Result of entity extraction."""

    nodes: Dict[str, Dict[str, Any]]  # node_id -> node_data
    edges: List[Tuple[str, str, Dict[str, Any]]]  # (source, target, edge_data)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def merge(self, other: "ExtractionResult") -> "ExtractionResult":
        """Merge with another extraction result."""
        merged_nodes = {**self.nodes, **other.nodes}
        merged_edges = self.edges + other.edges
        merged_metadata = {**self.metadata, **other.metadata}

        return ExtractionResult(
            nodes=merged_nodes,
            edges=merged_edges,
            metadata=merged_metadata
        )


@dataclass
class ExtractorConfig:
    """Configuration for entity extractors."""

    entity_types: List[str] = field(default_factory=lambda: [
        "PERSON", "ORGANIZATION", "LOCATION", "EVENT", "CONCEPT"
    ])
    max_entities_per_chunk: int = 20
    max_relationships_per_chunk: int = 30
    max_gleaning: int = 1
    summary_max_tokens: int = 500

    model_func: Optional[Any] = None  # LLM function
    model_name: Optional[str] = None

    strategy_params: Dict[str, Any] = field(default_factory=dict)


class BaseEntityExtractor(ABC):
    """Abstract base class for entity extraction strategies."""

    def __init__(self, config: ExtractorConfig):
        """Initialize extractor with configuration."""
        self.config = config
        self._initialized = False

    async def initialize(self):
        """Initialize the extractor (load models, etc)."""
        if not self._initialized:
            await self._initialize_impl()
            self._initialized = True

    @abstractmethod
    async def _initialize_impl(self):
        """Implementation-specific initialization."""
        pass

    @abstractmethod
    async def extract(
        self,
        chunks: Dict[str, TextChunkSchema],
        storage: Optional[BaseKVStorage] = None
    ) -> ExtractionResult:
        """Extract entities and relationships from text chunks.

        Args:
            chunks: Dictionary of chunk_id -> chunk_data
            storage: Optional storage for caching

        Returns:
            ExtractionResult containing nodes and edges
        """
        pass

    @abstractmethod
    async def extract_single(
        self,
        text: str,
        chunk_id: Optional[str] = None
    ) -> ExtractionResult:
        """Extract from a single text chunk.

        Args:
            text: Text to extract from
            chunk_id: Optional chunk identifier

        Returns:
            ExtractionResult for this chunk
        """
        pass

    async def batch_extract(
        self,
        chunks: Dict[str, TextChunkSchema],
        batch_size: int = 10
    ) -> List[ExtractionResult]:
        """Batch extraction for multiple chunks.

        Args:
            chunks: Dictionary of chunk_id -> chunk_data
            batch_size: Number of chunks to process concurrently

        Returns:
            List of extraction results
        """
        results = []
        chunk_items = list(chunks.items())

        for i in range(0, len(chunk_items), batch_size):
            batch = chunk_items[i:i + batch_size]
            batch_tasks = [
                self.extract_single(chunk_data["content"], chunk_id=chunk_id)
                for chunk_id, chunk_data in batch
            ]
            batch_results = await asyncio.gather(*batch_tasks)
            results.extend(batch_results)

        return results

    @staticmethod
    def deduplicate_entities(
        results: List[ExtractionResult],
    ) -> ExtractionResult:
        """Deduplicate entities across multiple extraction results.

        Args:
            results: List of extraction results

        Returns:
            Merged and deduplicated result
        """
        merged_nodes = defaultdict(list)
        merged_edges = []

        for result in results:
            for node_id, node_data in result.nodes.items():
                merged_nodes[node_id].append(node_data)
            merged_edges.extend(result.edges)

        # Merge node data for duplicates
        final_nodes = {}
        for node_id, node_data_list in merged_nodes.items():
            if len(node_data_list) == 1:
                final_nodes[node_id] = node_data_list[0]
            else:
                # Merge descriptions and keep most common type
                merged_data = node_data_list[0].copy()
                descriptions = [d.get("description", "") for d in node_data_list]
                merged_data["description"] = " ".join(descriptions)
                final_nodes[node_id] = merged_data

        # Deduplicate edges
        unique_edges = []
        seen_edges = set()

        for edge in merged_edges:
            # Use description as key since extractors don't set "relation"
            edge_key = (edge[0], edge[1], edge[2].get("description", ""))
            if edge_key not in seen_edges:
                unique_edges.append(edge)
                seen_edges.add(edge_key)

        return ExtractionResult(nodes=final_nodes, edges=unique_edges)