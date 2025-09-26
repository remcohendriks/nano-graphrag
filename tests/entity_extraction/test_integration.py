"""Integration tests for entity extraction with GraphRAG."""

import pytest
import os
from unittest.mock import AsyncMock, MagicMock
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, EntityExtractionConfig
from nano_graphrag.entity_extraction.base import ExtractionResult


class TestGraphRAGIntegration:
    """Test entity extraction integration with GraphRAG."""

    @pytest.mark.asyncio
    async def test_graphrag_with_llm_extraction(self, tmp_path):
        """Test GraphRAG with LLM extraction strategy."""
        from nano_graphrag.config import StorageConfig

        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=str(tmp_path)),
            entity_extraction=EntityExtractionConfig(
                strategy="llm",
                max_gleaning=1
            )
        )

        # Create GraphRAG instance
        rag = GraphRAG(config)

        # Verify extractor was initialized correctly
        assert rag.entity_extractor is not None
        assert rag.entity_extractor.__class__.__name__ == "LLMEntityExtractor"
        assert rag.entity_extraction_func is not None

    @pytest.mark.asyncio
    async def test_graphrag_with_dspy_extraction(self, tmp_path):
        """Test GraphRAG with DSPy extraction strategy."""
        from nano_graphrag.config import StorageConfig

        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=str(tmp_path)),
            entity_extraction=EntityExtractionConfig(
                strategy="dspy",
                max_gleaning=0
            )
        )

        # Create GraphRAG instance
        rag = GraphRAG(config)

        # Verify extractor was initialized correctly
        assert rag.entity_extractor is not None
        assert rag.entity_extractor.__class__.__name__ == "DSPyEntityExtractor"
        assert rag.entity_extraction_func is not None

    @pytest.mark.asyncio
    async def test_extraction_wrapper_function(self, tmp_path):
        """Test the extraction wrapper function works correctly."""
        from nano_graphrag.config import StorageConfig

        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=str(tmp_path)),
            entity_extraction=EntityExtractionConfig(strategy="llm")
        )

        rag = GraphRAG(config)

        # Mock the extractor's extract method
        mock_result = ExtractionResult(
            nodes={
                "ENTITY1": {
                    "entity_name": "ENTITY1",
                    "entity_type": "PERSON",
                    "description": "Test entity",
                    "source_id": "chunk1"
                }
            },
            edges=[("ENTITY1", "ENTITY2", {"weight": 1.0, "description": "knows", "source_id": "chunk1"})]
        )

        rag.entity_extractor.extract = AsyncMock(return_value=mock_result)
        rag.entity_extractor.initialize = AsyncMock()

        # Create mock storage instances
        mock_graph = MagicMock()
        mock_graph.upsert_node = AsyncMock()
        mock_graph.upsert_edge = AsyncMock()
        mock_graph.execute_document_batch = AsyncMock()  # Add batch execution mock
        mock_graph.get_node = AsyncMock(return_value=None)
        mock_graph.has_node = AsyncMock(return_value=False)
        mock_graph.has_edge = AsyncMock(return_value=False)

        mock_vdb = MagicMock()
        mock_vdb.upsert = AsyncMock()

        mock_tokenizer = MagicMock()
        mock_tokenizer.encode = MagicMock(return_value=[1, 2, 3])
        mock_tokenizer.decode = MagicMock(return_value="decoded text")

        # Test the wrapper function
        chunks = {"chunk1": {"content": "Test content"}}
        global_config = {
            "cheap_model_func": AsyncMock(return_value="summary"),
            "entity_summary_to_max_tokens": 100,
            "cheap_model_max_token_size": 1000
        }

        result = await rag._extract_entities_wrapper(
            chunks,
            mock_graph,
            mock_vdb,
            mock_tokenizer,
            global_config
        )

        # Verify initialization was called
        rag.entity_extractor.initialize.assert_called_once()

        # Verify extraction was called with correct chunks
        rag.entity_extractor.extract.assert_called_once_with(chunks)

        # Verify graph storage was updated with batch operation
        assert mock_graph.execute_document_batch.called
        assert mock_vdb.upsert.called
        assert result == mock_graph

    @pytest.mark.asyncio
    async def test_strategy_switching(self, tmp_path):
        """Test switching between extraction strategies."""
        from nano_graphrag.config import StorageConfig

        # Start with LLM strategy
        config_llm = GraphRAGConfig(
            storage=StorageConfig(working_dir=str(tmp_path)),
            entity_extraction=EntityExtractionConfig(strategy="llm")
        )
        rag_llm = GraphRAG(config_llm)
        assert rag_llm.entity_extractor.__class__.__name__ == "LLMEntityExtractor"

        # Create new instance with DSPy strategy
        config_dspy = GraphRAGConfig(
            storage=StorageConfig(working_dir=str(tmp_path) + "_dspy"),
            entity_extraction=EntityExtractionConfig(strategy="dspy")
        )
        rag_dspy = GraphRAG(config_dspy)
        assert rag_dspy.entity_extractor.__class__.__name__ == "DSPyEntityExtractor"

    def test_extraction_config_in_graphrag_config(self):
        """Test EntityExtractionConfig is properly integrated."""
        config = GraphRAGConfig()

        # Check default values
        assert config.entity_extraction.strategy == "llm"
        assert config.entity_extraction.max_gleaning == 1
        assert config.entity_extraction.summary_max_tokens == 500

        # Check custom values
        custom_config = GraphRAGConfig(
            entity_extraction=EntityExtractionConfig(
                strategy="dspy",
                max_gleaning=3,
                summary_max_tokens=1000
            )
        )

        assert custom_config.entity_extraction.strategy == "dspy"
        assert custom_config.entity_extraction.max_gleaning == 3
        assert custom_config.entity_extraction.summary_max_tokens == 1000