# SPLADE Sparse Embedding Service
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Download and cache the SPLADE model during build time
# This ensures the model is baked into the image
RUN python -c "from transformers import AutoModelForMaskedLM, AutoTokenizer; \
    import torch; \
    print('Downloading SPLADE model...'); \
    model_name = 'prithivida/Splade_PP_en_v1'; \
    tokenizer = AutoTokenizer.from_pretrained(model_name); \
    model = AutoModelForMaskedLM.from_pretrained(model_name); \
    print(f'Model downloaded successfully: {model_name}'); \
    print(f'Model size: {sum(p.numel() for p in model.parameters()) / 1e6:.1f}M parameters')"

# Copy the SPLADE service code
COPY . /app/

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8001/health')"

# Run the service
CMD ["uvicorn", "splade_service:app", "--host", "0.0.0.0", "--port", "8001"]