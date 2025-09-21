"""Sparse embedding provider for hybrid search."""

import os
import asyncio
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

_model_cache = {}
_model_lock = asyncio.Lock()


async def get_sparse_embeddings(texts: List[str]) -> List[Dict[str, Any]]:
    """Generate sparse embeddings for hybrid search.

    Returns list of dicts with 'indices' and 'values' for each text.
    Falls back to empty embeddings on error.
    """
    if not texts:
        return []

    enable_hybrid = os.getenv("ENABLE_HYBRID_SEARCH", "false").lower() == "true"
    if not enable_hybrid:
        return [{"indices": [], "values": []} for _ in texts]

    try:
        model_name = os.getenv("SPARSE_MODEL", "prithvida/Splade_PP_en_v1")
        cache_enabled = os.getenv("SPARSE_MODEL_CACHE", "true").lower() == "true"
        timeout_ms = int(os.getenv("SPARSE_TIMEOUT_MS", "5000"))
        batch_size = int(os.getenv("SPARSE_BATCH_SIZE", "32"))
        max_length = int(os.getenv("SPARSE_MAX_LENGTH", "256"))

        async with _model_lock:
            if cache_enabled and model_name in _model_cache:
                tokenizer, model = _model_cache[model_name]
            else:
                try:
                    from transformers import AutoTokenizer, AutoModelForMaskedLM
                    import torch

                    logger.info(f"Loading sparse model: {model_name}")
                    tokenizer = AutoTokenizer.from_pretrained(model_name)
                    model = AutoModelForMaskedLM.from_pretrained(model_name)
                    model.eval()

                    if cache_enabled:
                        _model_cache[model_name] = (tokenizer, model)

                    logger.info(f"Loaded sparse model: {model_name}")
                except Exception as e:
                    logger.error(f"Failed to load sparse model: {e}")
                    return [{"indices": [], "values": []} for _ in texts]

        result = await asyncio.wait_for(
            _encode_batch(texts, tokenizer, model, batch_size, max_length),
            timeout=timeout_ms / 1000.0
        )
        return result

    except asyncio.TimeoutError:
        logger.warning(f"Sparse encoding timed out, returning empty embeddings")
        return [{"indices": [], "values": []} for _ in texts]
    except Exception as e:
        logger.warning(f"Sparse encoding failed: {e}")
        return [{"indices": [], "values": []} for _ in texts]


async def _encode_batch(texts, tokenizer, model, batch_size, max_length):
    """Encode texts in batches."""
    import torch

    sparse_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]

        with torch.no_grad():
            inputs = tokenizer(
                batch_texts,
                return_tensors="pt",
                max_length=max_length,
                truncation=True,
                padding=True
            )

            outputs = model(**inputs)
            logits = outputs.logits

            for j in range(len(batch_texts)):
                # Max pooling then log(1 + ReLU(x)) sparsification
                item_logits = logits[j]
                pooled = torch.max(item_logits, dim=0).values
                sparse = torch.log1p(torch.relu(pooled))

                nonzero = torch.nonzero(sparse).squeeze()
                if nonzero.numel() > 0:
                    indices = nonzero.cpu().tolist()
                    if not isinstance(indices, list):
                        indices = [indices]
                    values = sparse[nonzero].cpu().tolist()
                    if not isinstance(values, list):
                        values = [values]
                else:
                    indices = []
                    values = []

                sparse_embeddings.append({
                    "indices": indices,
                    "values": values
                })

    return sparse_embeddings