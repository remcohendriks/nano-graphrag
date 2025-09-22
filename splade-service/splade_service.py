"""SPLADE Sparse Embedding Service - Separate microservice for sparse embeddings."""

import logging
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import torch
from transformers import AutoModelForMaskedLM, AutoTokenizer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SPLADE Embedding Service")

# Global model storage
model = None
tokenizer = None
device = None


class EmbedRequest(BaseModel):
    """Request model for embedding."""
    texts: List[str]
    max_length: int = 256
    batch_size: int = 32


class EmbedResponse(BaseModel):
    """Response model for embedding."""
    embeddings: List[Dict[str, List]]


@app.on_event("startup")
async def load_model():
    """Load SPLADE model on startup."""
    global model, tokenizer, device

    model_name = "prithivida/Splade_PP_en_v1"
    logger.info(f"Loading SPLADE model: {model_name}")

    try:
        # Load model and tokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForMaskedLM.from_pretrained(model_name)

        # Detect device
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device)
        model.eval()

        logger.info(f"Model loaded successfully on {device}")
        logger.info(f"Model parameters: {sum(p.numel() for p in model.parameters()) / 1e6:.1f}M")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise


@app.get("/health")
async def health():
    """Health check endpoint."""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "healthy", "device": device}


@app.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest):
    """Generate sparse embeddings for texts."""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    texts = request.texts
    max_length = request.max_length
    batch_size = request.batch_size

    if not texts:
        return EmbedResponse(embeddings=[])

    logger.info(f"Encoding {len(texts)} texts")

    try:
        sparse_embeddings = []

        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]

            with torch.no_grad():
                # Tokenize
                inputs = tokenizer(
                    batch_texts,
                    return_tensors="pt",
                    max_length=max_length,
                    truncation=True,
                    padding=True
                ).to(device)

                # Get model output
                outputs = model(**inputs)
                logits = outputs.logits

                # Process each item in batch
                for j in range(len(batch_texts)):
                    item_logits = logits[j]

                    # Max pooling over sequence dimension
                    pooled = torch.max(item_logits, dim=0).values

                    # Apply ReLU then log(1 + x) for sparsity
                    sparse = torch.log1p(torch.relu(pooled))

                    # Convert to sparse format (only non-zero values)
                    nonzero = torch.nonzero(sparse).squeeze()

                    if nonzero.numel() > 0:
                        indices = nonzero.cpu().numpy().tolist()
                        values = sparse[nonzero].cpu().numpy().tolist()

                        # Ensure lists even for single values
                        if isinstance(indices, int):
                            indices = [indices]
                            values = [values]
                    else:
                        indices = []
                        values = []

                    sparse_embeddings.append({
                        "indices": indices,
                        "values": values
                    })

        # Log statistics
        non_zero_counts = [len(e["indices"]) for e in sparse_embeddings]
        avg_non_zeros = sum(non_zero_counts) / len(non_zero_counts) if non_zero_counts else 0
        logger.info(
            f"Generated sparse embeddings: {len(texts)} texts, "
            f"avg {avg_non_zeros:.1f} non-zero dims"
        )

        return EmbedResponse(embeddings=sparse_embeddings)

    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)