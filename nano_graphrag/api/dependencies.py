"""Dependency injection for FastAPI."""

from fastapi import Request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nano_graphrag import GraphRAG


async def get_graphrag(request: Request) -> "GraphRAG":
    """Get GraphRAG instance from app state."""
    return request.app.state.graphrag