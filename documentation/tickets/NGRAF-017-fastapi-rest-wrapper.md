# NGRAF-017: FastAPI REST API Wrapper for Production Deployment

## Ticket ID
NGRAF-017

## Title
Implement FastAPI REST API Wrapper with Full Async Stack

## Description
Create a production-ready REST API wrapper for nano-graphrag using FastAPI and Starlette's native async capabilities. This implementation will provide a scalable, high-performance HTTP interface for GraphRAG operations, supporting concurrent requests through the fully async storage stack (Neo4j + Qdrant + Redis).

## Background & Motivation

### Current Limitations
- No HTTP interface for remote access
- Cannot handle concurrent requests efficiently
- File-based storage creates lock contention issues
- No standardized API for integration with other services

### Why FastAPI?
- Built on Starlette ASGI framework for native async support
- Automatic OpenAPI/Swagger documentation
- Pydantic integration for request/response validation
- Production-proven with excellent performance
- Native support for WebSockets (future streaming)

### Why This Stack?
The combination of FastAPI with async backends (Neo4j, Qdrant, Redis) eliminates file lock issues and enables:
- Horizontal scaling with multiple workers
- Thousands of concurrent requests
- Efficient resource utilization via event loops
- Connection pooling across all backends

## User Story
As a **developer deploying nano-graphrag in production**,
I want **a REST API that can handle concurrent requests**,
So that **I can integrate GraphRAG into my applications at scale**.

## Technical Requirements

### Core Architecture
```
Client → FastAPI → GraphRAG(async) → Neo4j + Qdrant + Redis
         ↓
      Starlette/ASGI → Uvicorn/Gunicorn
```

### API Endpoints

#### 1. Document Management
```python
POST   /api/v1/documents           # Insert single document
POST   /api/v1/documents/batch     # Batch insert
GET    /api/v1/documents/{doc_id}  # Retrieve document
DELETE /api/v1/documents/{doc_id}  # Remove document
```

#### 2. Query Operations
```python
POST   /api/v1/query               # Execute query
POST   /api/v1/query/stream        # Streaming query (SSE)
GET    /api/v1/query/modes         # Available query modes
```

#### 3. Health & Monitoring
```python
GET    /api/v1/health              # Health check all backends
GET    /api/v1/health/ready        # Readiness probe
GET    /api/v1/health/live         # Liveness probe
GET    /api/v1/metrics             # Prometheus metrics
```

#### 4. Management
```python
GET    /api/v1/info                # System information
POST   /api/v1/cache/clear         # Clear LLM cache
GET    /api/v1/stats               # Storage statistics
```

### Request/Response Models

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

class QueryMode(str, Enum):
    LOCAL = "local"
    GLOBAL = "global"
    NAIVE = "naive"

class DocumentInsert(BaseModel):
    content: str = Field(..., min_length=1)
    metadata: Optional[Dict[str, Any]] = None
    doc_id: Optional[str] = None

class BatchDocumentInsert(BaseModel):
    documents: List[DocumentInsert] = Field(..., min_items=1, max_items=100)

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    mode: QueryMode = QueryMode.LOCAL
    params: Optional[Dict[str, Any]] = None
    stream: bool = False

class QueryResponse(BaseModel):
    answer: str
    mode: str
    latency_ms: float
    metadata: Optional[Dict[str, Any]] = None

class HealthStatus(BaseModel):
    status: str  # "healthy", "degraded", "unhealthy"
    neo4j: bool
    qdrant: bool
    redis: bool
    timestamp: str
```

### Application Structure

```python
# app/main.py
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, StorageConfig

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage GraphRAG lifecycle."""
    # Startup
    logger.info("Initializing GraphRAG...")

    config = GraphRAGConfig(
        storage=StorageConfig(
            graph_backend="neo4j",
            vector_backend="qdrant",
            kv_backend="redis",
            neo4j_url=settings.neo4j_url,
            qdrant_url=settings.qdrant_url,
            redis_url=settings.redis_url,
        )
    )

    app.state.graphrag = GraphRAG(config=config)

    # Verify backends are accessible
    try:
        await app.state.graphrag.health_check()
        logger.info("All backends connected successfully")
    except Exception as e:
        logger.error(f"Backend initialization failed: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down GraphRAG...")
    # Cleanup connections if needed

app = FastAPI(
    title="nano-graphrag API",
    version="1.0.0",
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency for GraphRAG access
async def get_graphrag() -> GraphRAG:
    return app.state.graphrag
```

### Error Handling

```python
from fastapi import HTTPException
from starlette.status import HTTP_503_SERVICE_UNAVAILABLE

@app.exception_handler(StorageUnavailableError)
async def storage_unavailable_handler(request, exc):
    return JSONResponse(
        status_code=HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Storage backend temporarily unavailable"}
    )

class GraphRAGError(HTTPException):
    """Base exception for GraphRAG API errors."""
    pass

class DocumentNotFoundError(GraphRAGError):
    def __init__(self, doc_id: str):
        super().__init__(404, f"Document {doc_id} not found")

class QueryTimeoutError(GraphRAGError):
    def __init__(self, timeout: int):
        super().__init__(504, f"Query exceeded {timeout}s timeout")
```

### Configuration Management

```python
# app/config.py
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # API Configuration
    api_prefix: str = "/api/v1"
    allowed_origins: List[str] = ["*"]
    max_query_timeout: int = 300  # 5 minutes

    # Backend URLs
    neo4j_url: str
    neo4j_username: str
    neo4j_password: str
    qdrant_url: str
    redis_url: str

    # Performance
    max_concurrent_inserts: int = 10
    max_batch_size: int = 100

    # Security
    api_key_enabled: bool = False
    api_keys: List[str] = []

    class Config:
        env_file = ".env"

settings = Settings()
```

## Implementation Plan

### Phase 1: Core API (Week 1)
1. Project structure setup
2. FastAPI application with lifespan management
3. Basic document insert/query endpoints
4. Health check implementation
5. Error handling framework

### Phase 2: Advanced Features (Week 2)
1. Batch operations
2. Streaming responses (SSE)
3. Caching strategies
4. Metrics collection
5. Rate limiting

### Phase 3: Production Hardening (Week 3)
1. Authentication/authorization
2. Request validation & sanitization
3. Comprehensive error handling
4. Performance optimization
5. Docker containerization

### Phase 4: Deployment & Monitoring (Week 4)
1. Docker optimization
2. Prometheus/Grafana integration
3. API documentation
4. Performance optimization
5. CI/CD pipeline

## Testing Strategy

### Unit Tests
```python
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_document_insert(client: AsyncClient, mock_graphrag):
    mock_graphrag.ainsert = AsyncMock(return_value=None)

    response = await client.post(
        "/api/v1/documents",
        json={"content": "Test document"}
    )

    assert response.status_code == 201
    mock_graphrag.ainsert.assert_called_once()

@pytest.mark.asyncio
async def test_concurrent_queries(client: AsyncClient):
    """Test handling multiple concurrent requests."""
    tasks = [
        client.post("/api/v1/query", json={"question": f"Query {i}"})
        for i in range(100)
    ]
    responses = await asyncio.gather(*tasks)

    assert all(r.status_code == 200 for r in responses)
```

### Integration Tests
- Test with real backends using docker-compose
- Verify connection pooling behavior
- Test failover scenarios
- Concurrent request handling

### Performance Benchmarks
- Target: 1000+ requests/second
- P95 latency: <100ms for cached queries
- Memory usage: <500MB per worker
- Connection pools: Stable under load

## Acceptance Criteria

### Functional Requirements
1. ✅ All endpoints return correct responses
2. ✅ Concurrent requests handled without locks
3. ✅ Proper error messages for failures
4. ✅ OpenAPI documentation auto-generated
5. ✅ Health checks reflect backend status

### Non-Functional Requirements
1. ✅ Supports 100+ concurrent connections
2. ✅ P95 latency under 100ms for cached queries
3. ✅ Zero data loss during graceful shutdown
4. ✅ Horizontal scaling with multiple workers
5. ✅ Prometheus metrics exposed

### Production Requirements
1. ✅ Docker image optimized
2. ✅ Health/readiness probes implemented
3. ✅ Environment-based configuration
4. ✅ Structured JSON logging
5. ✅ CORS properly configured

## Dependencies

### Python Packages
```toml
[dependencies]
fastapi = ">=0.115.0"
uvicorn = { extras = ["standard"], version = ">=0.30.0" }
pydantic = ">=2.0.0"
pydantic-settings = ">=2.0.0"
httpx = ">=0.27.0"  # For testing
prometheus-fastapi-instrumentator = ">=7.0.0"
python-multipart = ">=0.0.9"  # For file uploads
sse-starlette = ">=2.0.0"  # For streaming
```

### Infrastructure
- Redis 7.0+ (already implemented)
- Neo4j 5.0+ with APOC
- Qdrant 1.7+
- Docker 20.10+ (for containerization)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Backend connection failures | High | Circuit breakers, health checks, graceful degradation |
| Memory leaks in long-running processes | Medium | Periodic worker recycling, memory monitoring |
| Rate limit abuse | Medium | API key authentication, rate limiting middleware |
| Large document uploads | Low | Request size limits, streaming uploads |

## Success Metrics

1. **Availability**: 99.9% uptime
2. **Performance**: P95 latency <100ms
3. **Scalability**: Linear scaling to 10K req/s
4. **Error Rate**: <0.1% 5xx errors
5. **Adoption**: 100+ API calls/minute

## Future Enhancements

1. **WebSocket Support**: Real-time query streaming
2. **GraphQL Interface**: Alternative query language
3. **Multi-tenancy**: Namespace isolation per client
4. **Caching Layer**: Redis-based response cache
5. **Admin UI**: Web interface for management

## Definition of Done

- [ ] All endpoints implemented and tested
- [ ] Unit test coverage >80%
- [ ] Integration tests passing
- [ ] API documentation complete
- [ ] Performance benchmarks met
- [ ] Docker image built and tested
- [ ] Environment configuration documented
- [ ] Production deployment guide written

## Feature Branch
`feature/ngraf-017-fastapi-wrapper`

## Pull Request Requirements
The PR should include:
1. Complete FastAPI application code
2. Comprehensive test suite
3. Docker configuration
4. API documentation
5. Deployment guides
6. Performance test results
7. Security checklist completed