"""Pydantic models for API requests and responses."""

from pydantic import BaseModel, Field, field_validator
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
    documents: List[DocumentInsert] = Field(..., min_length=1)

    @field_validator('documents')
    @classmethod
    def validate_batch_size(cls, v):
        from .config import settings
        if len(v) > settings.max_batch_size:
            raise ValueError(f"Batch size {len(v)} exceeds maximum allowed size of {settings.max_batch_size}")
        return v


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


class JobStatus(str, Enum):
    """Job status enum."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobProgress(BaseModel):
    """Job progress tracking."""
    current: int = 0
    total: int = 0
    phase: str = "initializing"


class JobResponse(BaseModel):
    """Job response model."""
    job_id: str
    status: JobStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    doc_ids: List[str]
    progress: JobProgress
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)