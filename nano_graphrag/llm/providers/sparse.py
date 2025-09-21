"""Sparse embedding provider for hybrid search."""

import os
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from functools import lru_cache
from dataclasses import dataclass

from ...config import HybridSearchConfig

logger = logging.getLogger(__name__)

# LRU cache for models (max 2 to prevent memory bloat)
@lru_cache(maxsize=2)
def get_cached_model(model_name: str, device: str) -> Tuple[Any, Any]:
    """Load and cache model with LRU eviction."""
    try:
        from transformers import AutoTokenizer, AutoModelForMaskedLM
        import torch

        logger.info(f"Loading sparse model: {model_name} on {device}")
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForMaskedLM.from_pretrained(model_name)

        # Move to GPU if available and requested
        if device == "cuda" and torch.cuda.is_available():
            model = model.cuda()
            logger.info(f"Moved model to GPU")
        elif device == "cuda":
            logger.warning(f"CUDA requested but not available, using CPU")
            device = "cpu"

        model.eval()
        return tokenizer, model
    except Exception as e:
        logger.error(f"Failed to load model {model_name}: {e}")
        raise


@dataclass
class SparseEmbeddingProvider:
    """SPLADE sparse embedding provider with singleton caching."""

    config: HybridSearchConfig
    _lock: asyncio.Lock = None

    def __post_init__(self):
        """Initialize lock."""
        self._lock = asyncio.Lock()

    async def embed(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Generate sparse embeddings with timeout and error handling."""
        if not texts:
            return []

        if not self.config.enabled:
            return [{"indices": [], "values": []} for _ in texts]

        try:
            # Apply timeout
            result = await asyncio.wait_for(
                self._embed_batch(texts),
                timeout=self.config.timeout_ms / 1000.0
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Sparse encoding timed out after {self.config.timeout_ms}ms")
            return [{"indices": [], "values": []} for _ in texts]
        except Exception as e:
            logger.warning(f"Sparse encoding failed: {e}")
            return [{"indices": [], "values": []} for _ in texts]

    async def _embed_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Encode texts in batches with GPU support."""
        try:
            import torch
            import numpy as np
        except ImportError:
            logger.error("torch/numpy not installed for sparse embeddings")
            return [{"indices": [], "values": []} for _ in texts]

        # Get cached model
        async with self._lock:
            try:
                tokenizer, model = get_cached_model(self.config.sparse_model, self.config.device)
            except Exception as e:
                logger.error(f"Failed to get model: {e}")
                return [{"indices": [], "values": []} for _ in texts]

        sparse_embeddings = []
        device = "cuda" if self.config.device == "cuda" and torch.cuda.is_available() else "cpu"

        # Process in batches
        for i in range(0, len(texts), self.config.batch_size):
            batch_texts = texts[i:i + self.config.batch_size]

            with torch.no_grad():
                inputs = tokenizer(
                    batch_texts,
                    return_tensors="pt",
                    max_length=self.config.max_length,
                    truncation=True,
                    padding=True
                )

                # Move to device
                if device == "cuda":
                    inputs = {k: v.cuda() for k, v in inputs.items()}

                outputs = model(**inputs)
                logits = outputs.logits

                # Process each item in batch
                for j in range(len(batch_texts)):
                    item_logits = logits[j]
                    # Max pooling then log(1 + ReLU(x)) sparsification
                    pooled = torch.max(item_logits, dim=0).values
                    sparse = torch.log1p(torch.relu(pooled))

                    # Convert to sparse format
                    nonzero = torch.nonzero(sparse).squeeze()
                    if nonzero.numel() > 0:
                        indices = nonzero.cpu().numpy()
                        indices = np.atleast_1d(indices).tolist()
                        values = sparse[nonzero].cpu().numpy()
                        values = np.atleast_1d(values).tolist()
                    else:
                        indices = []
                        values = []

                    sparse_embeddings.append({
                        "indices": indices,
                        "values": values
                    })

        return sparse_embeddings


# Backward compatibility function
async def get_sparse_embeddings(texts: List[str]) -> List[Dict[str, Any]]:
    """Legacy function for backward compatibility."""
    from ...config import HybridSearchConfig
    config = HybridSearchConfig.from_env()
    provider = SparseEmbeddingProvider(config=config)
    return await provider.embed(texts)