"""Tests for sparse embedding provider with external service."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from nano_graphrag.config import HybridSearchConfig
from nano_graphrag.llm.providers.sparse import SparseEmbeddingProvider


@pytest.mark.asyncio
async def test_sparse_provider_no_service():
    """Test sparse provider returns empty when no service configured."""
    config = HybridSearchConfig(enabled=True)

    with patch.dict("os.environ", {}, clear=True):
        provider = SparseEmbeddingProvider(config=config)
        result = await provider.embed(["test text"])

        assert len(result) == 1
        assert result[0]["indices"] == []
        assert result[0]["values"] == []


@pytest.mark.asyncio
async def test_sparse_provider_disabled():
    """Test sparse provider returns empty when disabled."""
    config = HybridSearchConfig(enabled=False)

    with patch.dict("os.environ", {"SPARSE_SERVICE_URL": "http://test:8001"}):
        provider = SparseEmbeddingProvider(config=config)
        result = await provider.embed(["test text"])

        assert len(result) == 1
        assert result[0]["indices"] == []
        assert result[0]["values"] == []


@pytest.mark.asyncio
async def test_sparse_provider_with_service():
    """Test sparse provider calls external service correctly."""
    config = HybridSearchConfig(
        enabled=True
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "embeddings": [
            {"indices": [1, 10, 100], "values": [0.5, 0.3, 0.2]},
            {"indices": [2, 20, 200], "values": [0.6, 0.4, 0.1]}
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.dict("os.environ", {"SPARSE_SERVICE_URL": "http://test:8001"}):
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            provider = SparseEmbeddingProvider(config=config)
            result = await provider.embed(["text1", "text2"])

            # Check service was called
            mock_client.post.assert_called_once_with(
                "http://test:8001/embed",
                json={"texts": ["text1", "text2"]}
            )

            # Check results
            assert len(result) == 2
            assert result[0]["indices"] == [1, 10, 100]
            assert result[0]["values"] == [0.5, 0.3, 0.2]
            assert result[1]["indices"] == [2, 20, 200]
            assert result[1]["values"] == [0.6, 0.4, 0.1]


@pytest.mark.asyncio
async def test_sparse_provider_service_timeout():
    """Test sparse provider handles service timeout gracefully."""
    import httpx

    config = HybridSearchConfig(enabled=True)

    with patch.dict("os.environ", {"SPARSE_SERVICE_URL": "http://test:8001"}):
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("timeout")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            provider = SparseEmbeddingProvider(config=config)
            result = await provider.embed(["test"])

            # Should return empty on timeout
            assert len(result) == 1
            assert result[0]["indices"] == []
            assert result[0]["values"] == []


@pytest.mark.asyncio
async def test_sparse_provider_service_error():
    """Test sparse provider handles service errors gracefully."""
    import httpx

    config = HybridSearchConfig(enabled=True)

    with patch.dict("os.environ", {"SPARSE_SERVICE_URL": "http://test:8001"}):
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_client.post.return_value = mock_response
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500", request=None, response=mock_response
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            provider = SparseEmbeddingProvider(config=config)
            result = await provider.embed(["test"])

            # Should return empty on error
            assert len(result) == 1
            assert result[0]["indices"] == []
            assert result[0]["values"] == []