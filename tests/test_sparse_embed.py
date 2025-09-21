"""Tests for sparse embedding provider."""

import asyncio
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_sparse_embedding_disabled():
    """Test that sparse embeddings return empty when disabled."""
    from nano_graphrag.config import HybridSearchConfig
    from nano_graphrag.llm.providers.sparse import SparseEmbeddingProvider

    config = HybridSearchConfig(enabled=False)
    provider = SparseEmbeddingProvider(config=config)

    result = await provider.embed(["test text"])
    assert result == [{"indices": [], "values": []}]


@pytest.mark.asyncio
async def test_sparse_embedding_lru_cache():
    """Test that model is cached with LRU."""
    from nano_graphrag.config import HybridSearchConfig
    from nano_graphrag.llm.providers.sparse import SparseEmbeddingProvider, get_cached_model

    mock_tokenizer = MagicMock()
    mock_model = MagicMock()

    with patch("transformers.AutoTokenizer") as mock_auto_tok:
        with patch("transformers.AutoModelForMaskedLM") as mock_auto_model:
            mock_auto_tok.from_pretrained.return_value = mock_tokenizer
            mock_auto_model.from_pretrained.return_value = mock_model
            mock_model.eval = MagicMock()

            # Clear LRU cache
            get_cached_model.cache_clear()

            config = HybridSearchConfig(enabled=True, sparse_model="test-model")
            provider = SparseEmbeddingProvider(config=config)

            # Mock torch module
            import sys
            mock_torch = MagicMock()
            mock_torch.cuda.is_available.return_value = False
            sys.modules['torch'] = mock_torch

            # First call should load model
            get_cached_model("test-model", "cpu")
            assert mock_auto_tok.from_pretrained.call_count == 1

            # Second call should use cache
            get_cached_model("test-model", "cpu")
            assert mock_auto_tok.from_pretrained.call_count == 1  # Still 1


@pytest.mark.asyncio
async def test_sparse_embedding_timeout():
    """Test timeout handling."""
    from nano_graphrag.config import HybridSearchConfig
    from nano_graphrag.llm.providers.sparse import SparseEmbeddingProvider

    config = HybridSearchConfig(enabled=True, timeout_ms=1)  # Very short timeout
    provider = SparseEmbeddingProvider(config=config)

    # Mock slow encoding
    async def slow_embed_batch(*args, **kwargs):
        await asyncio.sleep(1)  # Longer than timeout
        return []

    with patch.object(provider, '_embed_batch', slow_embed_batch):
        result = await provider.embed(["test"])
        assert result == [{"indices": [], "values": []}]


@pytest.mark.asyncio
async def test_sparse_embedding_batch_processing():
    """Test batch processing logic."""
    from nano_graphrag.config import HybridSearchConfig
    from nano_graphrag.llm.providers.sparse import SparseEmbeddingProvider, get_cached_model

    # Clear LRU cache
    get_cached_model.cache_clear()

    # Mock torch to avoid actual model loading
    import sys
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = False
    mock_torch.no_grad = MagicMock()
    mock_torch.no_grad.return_value.__enter__ = MagicMock()
    mock_torch.no_grad.return_value.__exit__ = MagicMock()

    # Create mock tensors
    mock_logits = MagicMock()
    mock_logits.__getitem__ = lambda self, idx: MagicMock()
    mock_torch.max.return_value.values = MagicMock()
    mock_torch.log1p.return_value = MagicMock()
    mock_torch.relu.return_value = MagicMock()
    mock_torch.nonzero.return_value.squeeze.return_value.numel.return_value = 0

    sys.modules['torch'] = mock_torch

    mock_tokenizer = MagicMock()
    mock_model = MagicMock()

    # Setup tokenizer mock
    mock_tokenizer.return_value = {
        "input_ids": MagicMock(),
        "attention_mask": MagicMock()
    }

    # Setup model mock
    mock_output = MagicMock()
    mock_output.logits = mock_logits
    mock_model.return_value = mock_output
    mock_model.eval = MagicMock()

    with patch("transformers.AutoTokenizer") as mock_auto_tok:
        with patch("transformers.AutoModelForMaskedLM") as mock_auto_model:
            mock_auto_tok.from_pretrained.return_value = mock_tokenizer
            mock_auto_model.from_pretrained.return_value = mock_model

            config = HybridSearchConfig(enabled=True, batch_size=2)
            provider = SparseEmbeddingProvider(config=config)

            # Test with 3 texts (batch size 2)
            texts = ["text1", "text2", "text3"]
            result = await provider.embed(texts)

            assert len(result) == 3
            for item in result:
                assert "indices" in item
                assert "values" in item
                assert isinstance(item["indices"], list)
                assert isinstance(item["values"], list)


@pytest.mark.asyncio
async def test_sparse_embedding_error_handling():
    """Test graceful error handling."""
    from nano_graphrag.config import HybridSearchConfig
    from nano_graphrag.llm.providers.sparse import SparseEmbeddingProvider, get_cached_model

    # Clear LRU cache
    get_cached_model.cache_clear()

    with patch("transformers.AutoTokenizer") as mock_auto:
        mock_auto.from_pretrained.side_effect = Exception("Model load failed")

        config = HybridSearchConfig(enabled=True)
        provider = SparseEmbeddingProvider(config=config)

        result = await provider.embed(["test"])
        assert result == [{"indices": [], "values": []}]


@pytest.mark.asyncio
async def test_sparse_embedding_empty_input():
    """Test handling empty input."""
    from nano_graphrag.config import HybridSearchConfig
    from nano_graphrag.llm.providers.sparse import SparseEmbeddingProvider

    config = HybridSearchConfig(enabled=True)
    provider = SparseEmbeddingProvider(config=config)

    result = await provider.embed([])
    assert result == []