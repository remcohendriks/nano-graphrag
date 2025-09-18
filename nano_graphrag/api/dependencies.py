"""Dependency injection for FastAPI."""

from fastapi import Request
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from nano_graphrag import GraphRAG
    import redis.asyncio as redis


async def get_graphrag(request: Request) -> "GraphRAG":
    """Get GraphRAG instance from app state."""
    return request.app.state.graphrag


async def get_redis(request: Request) -> Optional["redis.Redis"]:
    """Get Redis client from app state if available."""
    return getattr(request.app.state, "redis_client", None)