# SPLADE Sparse Embedding Service

A standalone microservice for generating sparse embeddings using the SPLADE model for hybrid search in nano-graphrag.

## Overview

This service provides sparse text embeddings using the SPLADE (Sparse Lexical AnD Expansion) model. It runs as a separate container to:
- Isolate heavy ML dependencies from the main API
- Pre-download the model during Docker build
- Share model across multiple API workers
- Enable independent scaling

## Model

Uses `prithivida/Splade_PP_en_v1` - a ~500MB BERT-based model that generates sparse representations.

## API Endpoints

### `GET /health`
Health check endpoint.

### `POST /embed`
Generate sparse embeddings for texts.

**Request:**
```json
{
  "texts": ["text1", "text2"],
  "max_length": 256,
  "batch_size": 32
}
```

**Response:**
```json
{
  "embeddings": [
    {
      "indices": [1, 10, 100],
      "values": [0.5, 0.3, 0.2]
    },
    {
      "indices": [2, 20, 200],
      "values": [0.6, 0.4, 0.1]
    }
  ]
}
```

## Building

```bash
docker build -t splade-service .
```

The model will be downloaded during build time, making the image ~2GB.

## Running Standalone

```bash
docker run -p 8001:8001 splade-service
```

## Environment Variables

- `TOKENIZERS_PARALLELISM`: Set to `false` to avoid fork warnings (optional)

## Testing

```bash
curl http://localhost:8001/health

curl -X POST http://localhost:8001/embed \
  -H "Content-Type: application/json" \
  -d '{
    "texts": ["Executive Order 14282"],
    "max_length": 256,
    "batch_size": 32
  }'
```