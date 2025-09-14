"""Query endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import time
import json
import asyncio
import logging
from typing import AsyncGenerator

from ..models import QueryRequest, QueryResponse, QueryMode
from ..dependencies import get_graphrag
from nano_graphrag import GraphRAG, QueryParam

router = APIRouter(prefix="/query", tags=["query"])
logger = logging.getLogger(__name__)

# Define allowed parameters for safe attribute setting
ALLOWED_QUERY_PARAMS = {
    'top_k', 'level', 'response_type',
    'local_max_token_for_text_unit', 'local_max_token_for_local_context',
    'local_max_token_for_community_report', 'local_community_single_one',
    'global_min_community_rating', 'global_max_consider_community',
    'global_max_token_for_community_report', 'naive_max_token_for_text_unit',
    'only_need_context'
}


@router.post("", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    graphrag: GraphRAG = Depends(get_graphrag)
) -> QueryResponse:
    """Execute a query against the knowledge graph."""
    start_time = time.time()

    # Build query parameters
    param = QueryParam(mode=request.mode.value)

    # Apply custom parameters - only allowed ones
    if request.params:
        for key, value in request.params.items():
            if key in ALLOWED_QUERY_PARAMS and hasattr(param, key):
                try:
                    setattr(param, key, value)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Invalid parameter {key}={value}: {e}")

    # Execute query with error handling for disabled modes
    try:
        answer = await graphrag.aquery(request.question, param=param)
    except ValueError as e:
        # Handle disabled naive mode or other value errors
        if "enable_naive_rag" in str(e):
            raise HTTPException(
                status_code=400,
                detail="Naive mode is not enabled. Set QUERY_ENABLE_NAIVE_RAG=true to enable it."
            )
        raise HTTPException(status_code=400, detail=str(e))

    latency_ms = (time.time() - start_time) * 1000

    return QueryResponse(
        answer=answer,
        mode=request.mode.value,
        latency_ms=latency_ms
    )


@router.post("/stream")
async def query_stream(
    request: QueryRequest,
    graphrag: GraphRAG = Depends(get_graphrag)
) -> StreamingResponse:
    """Stream query results using Server-Sent Events."""

    async def generate() -> AsyncGenerator[str, None]:
        start_time = time.time()

        # Send initial event
        yield f"data: {json.dumps({'event': 'start', 'mode': request.mode.value})}\n\n"

        # Build parameters
        param = QueryParam(mode=request.mode.value)
        if request.params:
            for key, value in request.params.items():
                if hasattr(param, key):
                    setattr(param, key, value)

        # Execute query
        answer = await graphrag.aquery(request.question, param=param)

        # Stream the answer in chunks
        chunk_size = 50  # characters per chunk
        for i in range(0, len(answer), chunk_size):
            chunk = answer[i:i + chunk_size]
            yield f"data: {json.dumps({'event': 'chunk', 'content': chunk})}\n\n"
            await asyncio.sleep(0.01)  # Small delay for streaming effect

        # Send completion event
        latency_ms = (time.time() - start_time) * 1000
        yield f"data: {json.dumps({'event': 'complete', 'latency_ms': latency_ms})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"}
    )


@router.get("/modes")
async def get_query_modes():
    """Get available query modes."""
    return {
        "modes": [
            {
                "name": mode.value,
                "description": {
                    "local": "Search within specific graph communities",
                    "global": "Search across all community reports",
                    "naive": "Simple vector similarity search"
                }.get(mode.value, "")
            }
            for mode in QueryMode
        ]
    }