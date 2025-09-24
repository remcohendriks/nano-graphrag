"""Sparse embedding provider for hybrid search using external SPLADE service."""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class SparseEmbeddingProvider:
    """Provider for sparse embeddings using external SPLADE service."""

    config: Any  # HybridSearchConfig

    def __post_init__(self):
        """Initialize provider and check service configuration."""
        self._service_url = os.environ.get("SPARSE_SERVICE_URL")

        if not self._service_url and self.config.enabled:
            logger.warning(
                "Hybrid search enabled but SPARSE_SERVICE_URL not configured. "
                "Sparse embeddings will return empty vectors."
            )

    async def embed(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Generate sparse embeddings via external service."""
        if not texts:
            return []

        if not self.config.enabled:
            return [{"indices": [], "values": []} for _ in texts]

        if not self._service_url:
            logger.debug("No SPARSE_SERVICE_URL configured, returning empty sparse vectors")
            return [{"indices": [], "values": []} for _ in texts]

        import httpx

        logger.debug(f"Sending {len(texts)} texts to SPLADE service at {self._service_url}")

        try:
            # Use default timeout of 30 seconds for service calls
            timeout = 30.0
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self._service_url}/embed",
                    json={"texts": texts}
                )
                response.raise_for_status()
                result = response.json()
                embeddings = result["embeddings"]

                # Log statistics
                if embeddings and logger.isEnabledFor(logging.DEBUG):
                    non_zeros = [len(emb["indices"]) for emb in embeddings]
                    avg_non_zeros = sum(non_zeros) / len(non_zeros) if non_zeros else 0
                    logger.debug(
                        f"Sparse encoding via service: {len(texts)} texts, "
                        f"avg {avg_non_zeros:.1f} non-zero dims"
                    )

                return embeddings

        except httpx.TimeoutException:
            logger.warning(f"SPLADE service timed out")
            return [{"indices": [], "values": []} for _ in texts]

        except httpx.HTTPStatusError as e:
            logger.error(f"SPLADE service HTTP error {e.response.status_code}: {e.response.text}")
            return [{"indices": [], "values": []} for _ in texts]

        except Exception as e:
            logger.error(f"SPLADE service call failed: {e}")
            return [{"indices": [], "values": []} for _ in texts]