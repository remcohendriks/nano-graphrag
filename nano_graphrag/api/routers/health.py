"""Health check endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
import asyncio

from ..models import HealthStatus
from ..dependencies import get_graphrag
from nano_graphrag import GraphRAG

router = APIRouter(prefix="/health", tags=["health"])


async def check_neo4j(graphrag: GraphRAG) -> bool:
    """Check Neo4j connectivity."""
    try:
        if hasattr(graphrag.chunk_entity_relation_graph, 'check_health'):
            return await graphrag.chunk_entity_relation_graph.check_health()
        return True  # Assume healthy if using networkx
    except Exception:
        return False


async def check_qdrant(graphrag: GraphRAG) -> bool:
    """Check Qdrant connectivity."""
    try:
        if hasattr(graphrag.entities_vdb, 'check_health'):
            return await graphrag.entities_vdb.check_health()
        return True  # Assume healthy if using nano-vectordb
    except Exception:
        return False


async def check_redis(graphrag: GraphRAG) -> bool:
    """Check Redis connectivity."""
    try:
        if hasattr(graphrag.full_docs, '_redis_client'):
            await graphrag.full_docs._ensure_initialized()
            return await graphrag.full_docs._redis_client.ping()
        return True  # Assume healthy if using JSON storage
    except Exception:
        return False


@router.get("", response_model=HealthStatus)
async def health_check(graphrag: GraphRAG = Depends(get_graphrag)) -> HealthStatus:
    """Comprehensive health check of all backends."""
    neo4j_health, qdrant_health, redis_health = await asyncio.gather(
        check_neo4j(graphrag),
        check_qdrant(graphrag),
        check_redis(graphrag),
        return_exceptions=True
    )

    # Handle exceptions from gather
    neo4j_ok = neo4j_health is True
    qdrant_ok = qdrant_health is True
    redis_ok = redis_health is True

    all_healthy = all([neo4j_ok, qdrant_ok, redis_ok])
    all_unhealthy = not any([neo4j_ok, qdrant_ok, redis_ok])

    if all_healthy:
        status = "healthy"
    elif all_unhealthy:
        status = "unhealthy"
    else:
        status = "degraded"

    return HealthStatus(
        status=status,
        neo4j=neo4j_ok,
        qdrant=qdrant_ok,
        redis=redis_ok
    )


@router.get("/ready")
async def readiness_probe(graphrag: GraphRAG = Depends(get_graphrag)) -> Dict[str, str]:
    """Kubernetes readiness probe."""
    health = await health_check(graphrag)
    if health.status == "unhealthy":
        raise HTTPException(status_code=503, detail="Service not ready")
    return {"status": "ready"}


@router.get("/live")
async def liveness_probe() -> Dict[str, str]:
    """Kubernetes liveness probe."""
    return {"status": "alive"}