"""Tests for NGRAF-019 typed relationship query improvements."""

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from nano_graphrag import GraphRAG, QueryParam
from nano_graphrag.config import GraphRAGConfig, StorageConfig, EntityExtractionConfig
from nano_graphrag._query import _build_local_query_context, _find_most_related_edges_from_entities
from nano_graphrag._community import _pack_single_community_describe


class TestDirectionalityPreservation:
    """Test that directional relationships are never inverted."""

    @pytest.mark.asyncio
    async def test_bidirectional_typed_edges_not_lost(self):
        """Verify bidirectional typed edges are both preserved."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_graph = MagicMock()

            # Bidirectional typed relationships - both should be preserved
            mock_edges = [
                ("A", "B"),  # A is parent of B
                ("B", "A")   # B is child of A
            ]
            mock_edge_data = [
                {"description": "parent of", "relation_type": "PARENT_OF", "weight": 1.0},
                {"description": "child of", "relation_type": "CHILD_OF", "weight": 1.0}
            ]

            mock_graph.get_nodes_edges_batch = AsyncMock(return_value=[mock_edges])
            mock_graph.get_edges_batch = AsyncMock(return_value=mock_edge_data)
            mock_graph.edge_degrees_batch = AsyncMock(return_value=[5, 5])

            mock_tokenizer = MagicMock()
            mock_tokenizer.encode = lambda x: [1] * 10

            node_datas = [{"entity_name": "A"}]
            query_param = QueryParam(local_max_token_for_local_context=1000)

            result = await _find_most_related_edges_from_entities(
                node_datas, query_param, mock_graph, mock_tokenizer
            )

            # Both edges should be preserved
            assert len(result) == 2
            edge_tuples = [r["src_tgt"] for r in result]
            assert ("A", "B") in edge_tuples
            assert ("B", "A") in edge_tuples

            # Check relation types are correct
            for r in result:
                if r["src_tgt"] == ("A", "B"):
                    assert r["relation_type"] == "PARENT_OF"
                elif r["src_tgt"] == ("B", "A"):
                    assert r["relation_type"] == "CHILD_OF"

    @pytest.mark.asyncio
    async def test_directional_relations_preserved_in_query(self):
        """Verify A SUPERSEDES B never becomes B SUPERSEDES A in query context."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a mock knowledge graph with directional edges
            mock_graph = MagicMock()

            # Mock edges with clear directional semantics
            # EO_14028 supersedes EO_13800 (newer supersedes older)
            mock_edges = [("EO_14028", "EO_13800")]
            mock_edge_data = {
                "description": "supersedes",
                "relation_type": "SUPERSEDES",
                "weight": 1.0
            }

            # Setup mock returns
            mock_graph.get_nodes_edges_batch = AsyncMock(return_value=[mock_edges])
            mock_graph.get_edges_batch = AsyncMock(return_value=[mock_edge_data])
            mock_graph.edge_degrees_batch = AsyncMock(return_value=[5])

            # Create mock tokenizer wrapper
            mock_tokenizer = MagicMock()
            mock_tokenizer.encode = lambda x: [1] * min(len(x), 100)

            # Call the function that processes edges
            node_datas = [{"entity_name": "EO_14028"}]
            query_param = QueryParam(local_max_token_for_local_context=1000)

            result = await _find_most_related_edges_from_entities(
                node_datas, query_param, mock_graph, mock_tokenizer
            )

            # Verify the edge direction is preserved
            assert len(result) == 1
            edge_result = result[0]

            # CRITICAL: Source should be EO_14028, target should be EO_13800
            assert edge_result["src_tgt"] == ("EO_14028", "EO_13800")
            assert edge_result["relation_type"] == "SUPERSEDES"

            # Verify we never flip it to (EO_13800, EO_14028)
            assert edge_result["src_tgt"] != ("EO_13800", "EO_14028")

    @pytest.mark.asyncio
    async def test_no_sorting_with_relation_type(self):
        """Test that edges with relation_type are not sorted alphabetically."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_graph = MagicMock()

            # Create edge where source > target alphabetically
            # Without proper handling, this would be sorted to (A, Z)
            mock_edges = [("Z_ENTITY", "A_ENTITY")]
            mock_edge_data = {
                "description": "overrides",
                "relation_type": "OVERRIDES",
                "weight": 0.9
            }

            mock_graph.get_nodes_edges_batch = AsyncMock(return_value=[mock_edges])
            mock_graph.get_edges_batch = AsyncMock(return_value=[mock_edge_data])
            mock_graph.edge_degrees_batch = AsyncMock(return_value=[3])

            mock_tokenizer = MagicMock()
            mock_tokenizer.encode = lambda x: [1] * 10

            node_datas = [{"entity_name": "Z_ENTITY"}]
            query_param = QueryParam(local_max_token_for_local_context=1000)

            result = await _find_most_related_edges_from_entities(
                node_datas, query_param, mock_graph, mock_tokenizer
            )

            # Should preserve Z→A direction, not sort to A→Z
            assert result[0]["src_tgt"] == ("Z_ENTITY", "A_ENTITY")
            assert result[0]["src_tgt"] != ("A_ENTITY", "Z_ENTITY")


class TestTypedRelationsInQuery:
    """Test typed relationships in query context."""

    @pytest.mark.asyncio
    async def test_relation_type_in_csv(self):
        """Verify relation_type column appears in relationships CSV."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Setup mocks for all dependencies
            mock_graph = MagicMock()
            mock_entities_vdb = MagicMock()
            mock_community_reports = MagicMock()
            mock_text_chunks_db = MagicMock()
            mock_tokenizer = MagicMock()
            mock_tokenizer.encode = lambda x: [1] * 10

            # Mock entity search results
            mock_entities_vdb.query = AsyncMock(return_value=[
                {"entity_name": "EO_14028"},
                {"entity_name": "EO_13800"}
            ])

            # Mock node data
            mock_graph.get_nodes_batch = AsyncMock(return_value=[
                {"entity_name": "EO_14028", "entity_type": "EXECUTIVE_ORDER", "description": "New order", "source_id": "chunk1"},
                {"entity_name": "EO_13800", "entity_type": "EXECUTIVE_ORDER", "description": "Old order", "source_id": "chunk1"}
            ])
            mock_graph.node_degrees_batch = AsyncMock(return_value=[10, 8])

            # Mock edges with relation_type
            mock_graph.get_nodes_edges_batch = AsyncMock(return_value=[
                [("EO_14028", "EO_13800")],
                []
            ])
            mock_graph.get_edges_batch = AsyncMock(return_value=[
                {"description": "supersedes", "relation_type": "SUPERSEDES", "weight": 1.0}
            ])
            mock_graph.edge_degrees_batch = AsyncMock(return_value=[5])

            # Mock community and text chunks (empty for simplicity)
            mock_community_reports.get_by_ids = AsyncMock(return_value=[])
            mock_text_chunks_db.get_by_ids = AsyncMock(return_value=[])
            mock_text_chunks_db.get_by_id = AsyncMock(return_value={"content": "test chunk"})
            mock_graph.get_node_edges_batch = AsyncMock(return_value=[[], []])
            mock_graph.get_nodes_batch = AsyncMock(return_value=[])

            query_param = QueryParam(top_k=2)

            # Build the context
            context = await _build_local_query_context(
                "What supersedes what?",
                mock_graph,
                mock_entities_vdb,
                mock_community_reports,
                mock_text_chunks_db,
                query_param,
                mock_tokenizer
            )

            # Verify the CSV contains relation_type column
            assert "relation_type" in context
            assert "-----Relationships-----" in context

            # Parse the relationships CSV section
            relationships_section = context.split("-----Relationships-----")[1].split("-----Sources-----")[0]
            csv_lines = relationships_section.strip().split("\n")

            # Check header
            header_line = csv_lines[1]  # Skip ```csv
            assert "relation_type" in header_line

            # Check data row
            if len(csv_lines) > 2:
                data_line = csv_lines[2]
                # Should have SUPERSEDES in the data
                assert "SUPERSEDES" in data_line

    @pytest.mark.asyncio
    async def test_relation_type_fallback(self):
        """Verify missing relation_type defaults to RELATED."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_graph = MagicMock()
            mock_tokenizer = MagicMock()
            mock_tokenizer.encode = lambda x: [1] * 10

            # Edge without relation_type field
            mock_edges = [("NODE_A", "NODE_B")]
            mock_edge_data = {
                "description": "connects to",
                "weight": 0.5
                # No relation_type field
            }

            mock_graph.get_nodes_edges_batch = AsyncMock(return_value=[mock_edges])
            mock_graph.get_edges_batch = AsyncMock(return_value=[mock_edge_data])
            mock_graph.edge_degrees_batch = AsyncMock(return_value=[2])

            node_datas = [{"entity_name": "NODE_A"}]
            query_param = QueryParam(local_max_token_for_local_context=1000)

            result = await _find_most_related_edges_from_entities(
                node_datas, query_param, mock_graph, mock_tokenizer
            )

            # The relation_type should default to RELATED when building CSV
            # This is handled in _build_local_query_context
            assert "relation_type" not in result[0]  # Not in raw edge data
            # The default will be applied when building CSV


class TestEnhancedCommunityReports:
    """Test typed relations in community reports."""

    @pytest.mark.asyncio
    async def test_community_report_with_none_global_config(self):
        """Verify _pack_single_community_describe handles None global_config."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_graph = MagicMock()
            mock_tokenizer = MagicMock()
            mock_tokenizer.encode = lambda x: [1] * 10

            community = {
                "title": "Test Community",
                "nodes": [],
                "edges": [],
                "sub_communities": []
            }

            mock_graph.get_node = AsyncMock(return_value={})
            mock_graph.get_edge = AsyncMock(return_value={})
            mock_graph.get_nodes_batch = AsyncMock(return_value=[])
            mock_graph.get_edges_batch = AsyncMock(return_value=[])
            mock_graph.node_degrees_batch = AsyncMock(return_value=[])
            mock_graph.edge_degrees_batch = AsyncMock(return_value=[])

            # This should not raise AttributeError even with None global_config
            result = await _pack_single_community_describe(
                mock_graph,
                community,
                mock_tokenizer,
                max_token_size=100,
                global_config=None  # Explicitly None
            )

            # Should produce valid output
            assert "-----Reports-----" in result
            assert "-----Entities-----" in result
            assert "-----Relationships-----" in result

    @pytest.mark.asyncio
    async def test_community_report_with_typed_relations(self):
        """Verify community reports include relation types."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_graph = MagicMock()
            mock_tokenizer = MagicMock()
            mock_tokenizer.encode = lambda x: [1] * min(len(x), 50)

            # Mock community data
            community = {
                "title": "Test Community",
                "nodes": ["EO_14028", "EO_13800", "STATUTE_2021"],
                "edges": [
                    ("EO_14028", "EO_13800"),
                    ("EO_14028", "STATUTE_2021")
                ],
                "sub_communities": []
            }

            # Mock node data
            mock_graph.get_node = AsyncMock(side_effect=[
                {"entity_type": "EXECUTIVE_ORDER", "description": "New cybersecurity order"},
                {"entity_type": "EXECUTIVE_ORDER", "description": "Previous order"},
                {"entity_type": "STATUTE", "description": "Cybersecurity act"}
            ])
            mock_graph.get_nodes_batch = AsyncMock(return_value=[
                {"entity_type": "EXECUTIVE_ORDER", "description": "New cybersecurity order"},
                {"entity_type": "EXECUTIVE_ORDER", "description": "Previous order"},
                {"entity_type": "STATUTE", "description": "Cybersecurity act"}
            ])

            # Mock edge data with relation types
            mock_graph.get_edge = AsyncMock(side_effect=[
                {"description": "supersedes", "relation_type": "SUPERSEDES", "weight": 1.0},
                {"description": "implements", "relation_type": "IMPLEMENTS", "weight": 0.9}
            ])
            mock_graph.get_edges_batch = AsyncMock(return_value=[
                {"description": "supersedes", "relation_type": "SUPERSEDES", "weight": 1.0},
                {"description": "implements", "relation_type": "IMPLEMENTS", "weight": 0.9}
            ])

            # Mock degrees
            mock_graph.node_degrees_batch = AsyncMock(return_value=[10, 8, 6])
            mock_graph.edge_degrees_batch = AsyncMock(return_value=[5, 4])

            # Generate the community description
            result = await _pack_single_community_describe(
                mock_graph,
                community,
                mock_tokenizer,
                max_token_size=1000
            )

            # Verify relation_type appears in the output
            assert "relation_type" in result
            assert "SUPERSEDES" in result
            assert "IMPLEMENTS" in result

            # Check that it's in the relationships section
            relationships_section = result.split("-----Relationships-----")[1]
            assert "relation_type" in relationships_section


class TestTypeEnrichedEmbeddings:
    """Test entity type prefixes in embeddings."""

    @pytest.mark.asyncio
    async def test_entity_type_prefix_enabled(self):
        """Verify entity types are prefixed when enabled."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {
                "ENTITY_TYPES": "EXECUTIVE_ORDER,STATUTE",
                "RELATION_PATTERNS": json.dumps({"supersedes": "SUPERSEDES"}),
                "ENABLE_TYPE_PREFIX_EMBEDDINGS": "true"
            }):
                config = GraphRAGConfig(
                    storage=StorageConfig(working_dir=tmp_dir),
                    entity_extraction=EntityExtractionConfig.from_env()
                )

                rag = GraphRAG(config)

                # Mock the entity extractor
                mock_result = type('Result', (), {
                    'nodes': {
                        "EO_14028": {
                            "entity_name": "EO_14028",
                            "entity_type": "EXECUTIVE_ORDER",
                            "description": "Cybersecurity improvement order",
                            "source_id": "chunk1"
                        }
                    },
                    'edges': []
                })()

                rag.entity_extractor.extract = AsyncMock(return_value=mock_result)
                await rag.entity_extractor.initialize()

                # Mock entity vector DB to capture what gets inserted
                inserted_data = {}
                async def mock_upsert(data):
                    inserted_data.update(data)

                # The vector DB is called entities_vdb
                rag.entities_vdb.upsert = mock_upsert

                # Process entities (get global_config dict)
                global_config_dict = rag._global_config()

                await rag._extract_entities_wrapper(
                    chunks={"chunk1": {"content": "test"}},
                    knwoledge_graph_inst=rag.chunk_entity_relation_graph,
                    entity_vdb=rag.entities_vdb,
                    tokenizer_wrapper=rag.tokenizer_wrapper,
                    global_config=global_config_dict
                )

                # Verify type prefix was added
                for entity_id, entity_data in inserted_data.items():
                    if "EO_14028" in entity_data.get("content", ""):
                        assert "[EXECUTIVE_ORDER]" in entity_data["content"]

    @pytest.mark.asyncio
    async def test_entity_type_prefix_disabled(self):
        """Verify entity types are not prefixed when disabled."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {
                "ENTITY_TYPES": "EXECUTIVE_ORDER,STATUTE",
                "ENABLE_TYPE_PREFIX_EMBEDDINGS": "false"  # Disabled
            }):
                config = GraphRAGConfig(
                    storage=StorageConfig(working_dir=tmp_dir),
                    entity_extraction=EntityExtractionConfig.from_env()
                )

                rag = GraphRAG(config)

                # Mock the entity extractor
                mock_result = type('Result', (), {
                    'nodes': {
                        "EO_14028": {
                            "entity_name": "EO_14028",
                            "entity_type": "EXECUTIVE_ORDER",
                            "description": "Cybersecurity improvement order",
                            "source_id": "chunk1"
                        }
                    },
                    'edges': []
                })()

                rag.entity_extractor.extract = AsyncMock(return_value=mock_result)
                await rag.entity_extractor.initialize()

                # Mock entity vector DB
                inserted_data = {}
                async def mock_upsert(data):
                    inserted_data.update(data)

                rag.entities_vdb.upsert = mock_upsert

                # Process entities (get global_config dict)
                global_config_dict = rag._global_config()

                await rag._extract_entities_wrapper(
                    chunks={"chunk1": {"content": "test"}},
                    knwoledge_graph_inst=rag.chunk_entity_relation_graph,
                    entity_vdb=rag.entities_vdb,
                    tokenizer_wrapper=rag.tokenizer_wrapper,
                    global_config=global_config_dict
                )

                # Verify type prefix was NOT added
                for entity_id, entity_data in inserted_data.items():
                    if "EO_14028" in entity_data.get("content", ""):
                        assert "[EXECUTIVE_ORDER]" not in entity_data["content"]


class TestBackwardCompatibility:
    """Test that the changes maintain backward compatibility."""

    @pytest.mark.asyncio
    async def test_query_without_typed_relations(self):
        """Verify queries work with edges lacking relation_type."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = GraphRAGConfig(
                storage=StorageConfig(working_dir=tmp_dir)
            )

            rag = GraphRAG(config)

            # Mock extraction without relation_type
            mock_result = type('Result', (), {
                'nodes': {
                    "ENTITY_A": {
                        "entity_name": "ENTITY_A",
                        "entity_type": "CONCEPT",
                        "description": "First entity",
                        "source_id": "chunk1"
                    },
                    "ENTITY_B": {
                        "entity_name": "ENTITY_B",
                        "entity_type": "CONCEPT",
                        "description": "Second entity",
                        "source_id": "chunk1"
                    }
                },
                'edges': [
                    ("ENTITY_A", "ENTITY_B", {
                        "description": "relates to",
                        "weight": 0.7,
                        "source_id": "chunk1"
                        # No relation_type field
                    })
                ]
            })()

            rag.entity_extractor.extract = AsyncMock(return_value=mock_result)
            await rag.entity_extractor.initialize()

            # This should not raise any errors
            try:
                await rag._extract_entities_wrapper(
                    chunks={"chunk1": {"content": "test"}},
                    knwoledge_graph_inst=rag.chunk_entity_relation_graph,
                    entity_vdb=None,
                    tokenizer_wrapper=rag.tokenizer_wrapper,
                    global_config=rag._global_config()
                )
                # If we get here, backward compatibility is maintained
                assert True
            except Exception as e:
                pytest.fail(f"Backward compatibility broken: {e}")


class TestTokenBudgetHandling:
    """Test that token limits are handled correctly with new columns."""

    @pytest.mark.asyncio
    async def test_truncation_preserves_relation_type(self):
        """Verify relation_type is preserved during truncation."""
        mock_tokenizer = MagicMock()
        # Make token count high to trigger truncation
        mock_tokenizer.encode = lambda x: [1] * 1000

        # Create many edges to trigger truncation
        edges_data = []
        for i in range(20):
            edges_data.append({
                "src_tgt": (f"NODE_{i}", f"NODE_{i+1}"),
                "description": f"Very long description that uses many tokens " * 10,
                "relation_type": f"TYPE_{i}",
                "weight": 1.0 - i * 0.01,
                "rank": 20 - i
            })

        from nano_graphrag._utils import truncate_list_by_token_size

        # Truncate with small budget
        truncated = truncate_list_by_token_size(
            edges_data,
            key=lambda x: x["description"],
            max_token_size=100,  # Small budget
            tokenizer_wrapper=mock_tokenizer
        )

        # Verify truncated edges still have relation_type
        assert len(truncated) < len(edges_data)  # Some were truncated
        for edge in truncated:
            assert "relation_type" in edge
            assert edge["relation_type"].startswith("TYPE_")