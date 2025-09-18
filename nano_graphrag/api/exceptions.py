"""Custom exceptions for FastAPI application."""

from fastapi import HTTPException
from starlette.status import (
    HTTP_404_NOT_FOUND,
    HTTP_503_SERVICE_UNAVAILABLE,
    HTTP_504_GATEWAY_TIMEOUT,
)


class GraphRAGError(HTTPException):
    """Base exception for GraphRAG API errors."""
    pass


class DocumentNotFoundError(GraphRAGError):
    def __init__(self, doc_id: str):
        super().__init__(HTTP_404_NOT_FOUND, f"Document {doc_id} not found")


class StorageUnavailableError(GraphRAGError):
    def __init__(self, backend: str):
        super().__init__(HTTP_503_SERVICE_UNAVAILABLE, f"{backend} backend temporarily unavailable")


class QueryTimeoutError(GraphRAGError):
    def __init__(self, timeout: int):
        super().__init__(HTTP_504_GATEWAY_TIMEOUT, f"Query exceeded {timeout}s timeout")