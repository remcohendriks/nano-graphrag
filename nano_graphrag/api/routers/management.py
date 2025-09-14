"""Management endpoints."""

from fastapi import APIRouter, Depends
from typing import Dict
import platform
import sys

from ..dependencies import get_graphrag
from ..config import settings
from nano_graphrag import GraphRAG
from nano_graphrag import __version__ as nano_version

router = APIRouter(tags=["management"])


@router.get("/info")
async def get_info() -> Dict:
    """Get system information."""
    return {
        "nano_graphrag_version": nano_version,
        "api_version": settings.api_version,
        "python_version": sys.version,
        "platform": platform.platform(),
        "backends": {
            "graph": settings.graph_backend,
            "vector": settings.vector_backend,
            "kv": settings.kv_backend
        },
        "llm": {
            "provider": settings.llm_provider,
            "model": settings.llm_model
        },
        "embedding": {
            "provider": settings.embedding_provider,
            "model": settings.embedding_model
        }
    }


@router.get("/stats")
async def get_stats(graphrag: GraphRAG = Depends(get_graphrag)) -> Dict:
    """Get storage statistics."""
    stats = {}

    # Get KV storage stats
    try:
        if hasattr(graphrag.full_docs, 'get_stats'):
            stats["documents"] = await graphrag.full_docs.get_stats()
        if hasattr(graphrag.text_chunks, 'get_stats'):
            stats["chunks"] = await graphrag.text_chunks.get_stats()
        if hasattr(graphrag.community_reports, 'get_stats'):
            stats["communities"] = await graphrag.community_reports.get_stats()
    except Exception as e:
        stats["kv_error"] = str(e)

    # Get graph stats
    try:
        if hasattr(graphrag.chunk_entity_relation_graph, 'node_count'):
            stats["graph"] = {
                "nodes": await graphrag.chunk_entity_relation_graph.node_count(),
                "edges": await graphrag.chunk_entity_relation_graph.edge_count()
            }
    except Exception as e:
        stats["graph_error"] = str(e)

    return stats


@router.post("/cache/clear")
async def clear_cache(graphrag: GraphRAG = Depends(get_graphrag)) -> Dict[str, str]:
    """Clear LLM response cache."""
    try:
        if hasattr(graphrag.llm_response_cache, 'drop'):
            await graphrag.llm_response_cache.drop()
            return {"message": "Cache cleared successfully"}
        return {"message": "No cache to clear"}
    except Exception as e:
        return {"error": f"Failed to clear cache: {str(e)}"}