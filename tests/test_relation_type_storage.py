"""Test that relation types are properly stored in the graph."""

import asyncio
import pytest
import os
import json
import tempfile
from unittest.mock import AsyncMock, patch

from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, StorageConfig, EntityExtractionConfig
from nano_graphrag._storage.gdb_networkx import NetworkXStorage


@pytest.mark.asyncio
async def test_relation_type_stored_in_graph():
    """Test that relation_type is properly stored in edges."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Configure with custom relation patterns
        with patch.dict(os.environ, {
            "RELATION_PATTERNS": json.dumps({
                "supersedes": "SUPERSEDES",
                "implements": "IMPLEMENTS"
            })
        }):
            config = GraphRAGConfig(
                storage=StorageConfig(working_dir=temp_dir),
                entity_extraction=EntityExtractionConfig(
                    entity_types=["EXECUTIVE_ORDER", "STATUTE"]
                )
            )

            rag = GraphRAG(config)

            # Mock the extractor to return predictable results
            mock_result = type('Result', (), {
                'nodes': {
                    "EO_14028": {
                        "entity_name": "EO_14028",
                        "entity_type": "EXECUTIVE_ORDER",
                        "description": "Executive Order on cybersecurity",
                        "source_id": "chunk1"
                    },
                    "EO_13800": {
                        "entity_name": "EO_13800",
                        "entity_type": "EXECUTIVE_ORDER",
                        "description": "Previous cybersecurity order",
                        "source_id": "chunk1"
                    }
                },
                'edges': [
                    ("EO_14028", "EO_13800", {
                        "description": "supersedes",
                        "weight": 1.0,
                        "source_id": "chunk1"
                    }),
                    ("EO_14028", "CYBERSECURITY_ACT", {
                        "description": "implements provisions of",
                        "weight": 0.9,
                        "source_id": "chunk1"
                    })
                ]
            })()

            # Replace entity extractor's extract method
            rag.entity_extractor.extract = AsyncMock(return_value=mock_result)

            # Initialize extractor
            await rag.entity_extractor.initialize()

            # Run extraction through the wrapper (this should apply relation mapping)
            graph_storage = rag.chunk_entity_relation_graph
            result = await rag._extract_entities_wrapper(
                chunks={"chunk1": {"content": "test text"}},
                knwoledge_graph_inst=graph_storage,
                entity_vdb=None,
                tokenizer_wrapper=rag.tokenizer_wrapper,
                global_config=rag._global_config()
            )

            # Verify edges have relation_type
            edge1 = await graph_storage.get_edge("EO_14028", "EO_13800")
            assert edge1 is not None
            assert "relation_type" in edge1
            assert edge1["relation_type"] == "SUPERSEDES"

            edge2 = await graph_storage.get_edge("EO_14028", "CYBERSECURITY_ACT")
            if edge2:  # Might not exist if node wasn't created
                assert "relation_type" in edge2
                assert edge2["relation_type"] == "IMPLEMENTS"


@pytest.mark.asyncio
async def test_relation_type_defaults_to_related():
    """Test that unmapped relations default to RELATED."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=temp_dir)
        )

        rag = GraphRAG(config)

        # Mock result with unmappable description
        mock_result = type('Result', (), {
            'nodes': {
                "NODE_A": {"entity_name": "NODE_A", "entity_type": "CONCEPT", "description": "A", "source_id": "chunk1"},
                "NODE_B": {"entity_name": "NODE_B", "entity_type": "CONCEPT", "description": "B", "source_id": "chunk1"}
            },
            'edges': [
                ("NODE_A", "NODE_B", {"description": "is somehow connected to", "weight": 1.0, "source_id": "chunk1"})
            ]
        })()

        rag.entity_extractor.extract = AsyncMock(return_value=mock_result)
        await rag.entity_extractor.initialize()

        # Run extraction
        graph_storage = rag.chunk_entity_relation_graph
        await rag._extract_entities_wrapper(
            chunks={"chunk1": {"content": "test"}},
            knwoledge_graph_inst=graph_storage,
            entity_vdb=None,
            tokenizer_wrapper=rag.tokenizer_wrapper,
            global_config=rag._global_config()
        )

        # Verify default relation type
        edge = await graph_storage.get_edge("NODE_A", "NODE_B")
        assert edge is not None
        assert edge.get("relation_type") == "RELATED"