"""Document management endpoints."""

from fastapi import APIRouter, Depends, BackgroundTasks
from typing import Dict, Any
import asyncio
import time

from ..models import DocumentInsert, BatchDocumentInsert, DocumentResponse
from ..dependencies import get_graphrag
from ..exceptions import DocumentNotFoundError
from ..storage_adapter import StorageAdapter
from nano_graphrag import GraphRAG
from nano_graphrag._utils import compute_mdhash_id

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=201)
async def insert_document(
    document: DocumentInsert,
    background_tasks: BackgroundTasks,
    graphrag: GraphRAG = Depends(get_graphrag)
) -> DocumentResponse:
    """Insert a single document."""
    doc_id = document.doc_id or compute_mdhash_id(document.content, prefix="doc-")

    # Schedule insertion as background task for faster response
    background_tasks.add_task(graphrag.ainsert, document.content)

    return DocumentResponse(doc_id=doc_id)


@router.post("/batch", response_model=Dict[str, str], status_code=201)
async def insert_batch(
    batch: BatchDocumentInsert,
    graphrag: GraphRAG = Depends(get_graphrag)
) -> Dict[str, str]:
    """Insert multiple documents in batch."""
    results = {}
    documents = []

    for doc in batch.documents:
        doc_id = doc.doc_id or compute_mdhash_id(doc.content, prefix="doc-")
        results[doc_id] = "queued"
        documents.append(doc.content)

    # Process batch asynchronously
    await graphrag.ainsert(documents)

    for doc_id in results:
        results[doc_id] = "processed"

    return results


@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    graphrag: GraphRAG = Depends(get_graphrag)
) -> Dict[str, Any]:
    """Retrieve document by ID."""
    adapter = StorageAdapter(graphrag.full_docs)
    doc = await adapter.get_by_id(doc_id)
    if not doc:
        raise DocumentNotFoundError(doc_id)
    # Normalize response format
    if isinstance(doc, dict) and "content" in doc:
        return {"doc_id": doc_id, "content": doc["content"], "metadata": doc.get("metadata")}
    return {"doc_id": doc_id, "content": doc}


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    graphrag: GraphRAG = Depends(get_graphrag)
) -> Dict[str, str]:
    """Delete document by ID."""
    adapter = StorageAdapter(graphrag.full_docs)
    success = await adapter.delete_by_id(doc_id)
    if not success:
        raise DocumentNotFoundError(doc_id)
    return {"message": f"Document {doc_id} deleted"}