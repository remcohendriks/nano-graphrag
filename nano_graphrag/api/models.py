"""Pydantic models for API requests and responses."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


class QueryMode(str, Enum):
    LOCAL = "local"
    GLOBAL = "global"
    NAIVE = "naive"


class DocumentInsert(BaseModel):
    content: str = Field(..., min_length=1)
    metadata: Optional[Dict[str, Any]] = None
    doc_id: Optional[str] = None


class BatchDocumentInsert(BaseModel):
    documents: List[DocumentInsert] = Field(..., min_length=1, max_length=100)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    mode: QueryMode = QueryMode.LOCAL
    params: Optional[Dict[str, Any]] = None


class QueryResponse(BaseModel):
    answer: str
    mode: str
    latency_ms: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthStatus(BaseModel):
    status: str  # "healthy", "degraded", "unhealthy"
    neo4j: bool
    qdrant: bool
    redis: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DocumentResponse(BaseModel):
    doc_id: str
    message: str = "Document processed successfully"


class ErrorResponse(BaseModel):
    detail: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)