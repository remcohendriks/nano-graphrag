"""Tests for sparse embedding provider."""

import asyncio
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_sparse_embedding_disabled():
    """Test that sparse embeddings return empty when disabled."""
    with patch.dict(os.environ, {"ENABLE_HYBRID_SEARCH": "false"}):
        from nano_graphrag._storage.sparse_embed import get_sparse_embeddings

        result = await get_sparse_embeddings(["test text"])
        assert result == [{"indices": [], "values": []}]


@pytest.mark.asyncio
async def test_sparse_embedding_singleton():
    """Test that model is cached and reused."""
    with patch.dict(os.environ, {
        "ENABLE_HYBRID_SEARCH": "true",
        "SPARSE_MODEL_CACHE": "true"
    }):
        mock_tokenizer = MagicMock()
        mock_model = MagicMock()

        with patch("transformers.AutoTokenizer") as mock_auto_tok:
            with patch("transformers.AutoModelForMaskedLM") as mock_auto_model:
                mock_auto_tok.from_pretrained.return_value = mock_tokenizer
                mock_auto_model.from_pretrained.return_value = mock_model

                # Mock the model output
                mock_output = MagicMock()
                mock_output.logits = MagicMock()
                mock_model.return_value = mock_output

                import nano_graphrag._storage.sparse_embed as sparse_module
                sparse_module._model_cache.clear()  # Clear cache

                # First call should load model
                await sparse_module.get_sparse_embeddings(["test"])
                assert mock_auto_tok.from_pretrained.call_count == 1

                # Second call should use cache
                await sparse_module.get_sparse_embeddings(["test2"])
                assert mock_auto_tok.from_pretrained.call_count == 1  # Still 1


@pytest.mark.asyncio
async def test_sparse_embedding_timeout():
    """Test timeout handling."""
    with patch.dict(os.environ, {
        "ENABLE_HYBRID_SEARCH": "true",
        "SPARSE_TIMEOUT_MS": "1"  # Very short timeout
    }):
        from nano_graphrag._storage.sparse_embed import get_sparse_embeddings

        # Mock slow encoding
        async def slow_encode(*args, **kwargs):
            await asyncio.sleep(1)  # Longer than timeout
            return []

        with patch("nano_graphrag._storage.sparse_embed._encode_batch", slow_encode):
            result = await get_sparse_embeddings(["test"])
            assert result == [{"indices": [], "values": []}]


@pytest.mark.asyncio
async def test_sparse_embedding_batch_processing():
    """Test batch processing logic."""
    with patch.dict(os.environ, {
        "ENABLE_HYBRID_SEARCH": "true",
        "SPARSE_BATCH_SIZE": "2"
    }):
        import torch
        mock_tokenizer = MagicMock()
        mock_model = MagicMock()

        # Setup tokenizer mock
        mock_tokenizer.return_value = {
            "input_ids": torch.zeros(2, 10),
            "attention_mask": torch.ones(2, 10)
        }

        # Setup model mock
        mock_logits = torch.rand(2, 10, 30522)  # batch_size, seq_len, vocab_size
        mock_output = MagicMock()
        mock_output.logits = mock_logits
        mock_model.return_value = mock_output

        with patch("transformers.AutoTokenizer") as mock_auto_tok:
            with patch("transformers.AutoModelForMaskedLM") as mock_auto_model:
                mock_auto_tok.from_pretrained.return_value = mock_tokenizer
                mock_auto_model.from_pretrained.return_value = mock_model
                mock_model.eval = MagicMock()

                from nano_graphrag._storage.sparse_embed import get_sparse_embeddings
                import nano_graphrag._storage.sparse_embed as sparse_module
                sparse_module._model_cache.clear()

                # Test with 3 texts (batch size 2)
                texts = ["text1", "text2", "text3"]
                result = await get_sparse_embeddings(texts)

                assert len(result) == 3
                for item in result:
                    assert "indices" in item
                    assert "values" in item
                    assert isinstance(item["indices"], list)
                    assert isinstance(item["values"], list)


@pytest.mark.asyncio
async def test_sparse_embedding_error_handling():
    """Test graceful error handling."""
    with patch.dict(os.environ, {"ENABLE_HYBRID_SEARCH": "true"}):
        with patch("transformers.AutoTokenizer") as mock_auto:
            mock_auto.from_pretrained.side_effect = Exception("Model load failed")

            from nano_graphrag._storage.sparse_embed import get_sparse_embeddings
            import nano_graphrag._storage.sparse_embed as sparse_module
            sparse_module._model_cache.clear()

            result = await get_sparse_embeddings(["test"])
            assert result == [{"indices": [], "values": []}]


@pytest.mark.asyncio
async def test_sparse_embedding_empty_input():
    """Test handling empty input."""
    from nano_graphrag._storage.sparse_embed import get_sparse_embeddings

    result = await get_sparse_embeddings([])
    assert result == []