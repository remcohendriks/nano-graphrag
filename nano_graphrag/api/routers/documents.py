"""Document management endpoints."""

from fastapi import APIRouter, Depends, BackgroundTasks
from typing import Dict, Any
import asyncio
import time
import traceback

from ..models import DocumentInsert, BatchDocumentInsert, DocumentResponse, JobResponse, JobStatus
from ..dependencies import get_graphrag, get_redis
from ..exceptions import DocumentNotFoundError
from ..storage_adapter import StorageAdapter
from ..jobs import JobManager
from nano_graphrag import GraphRAG
from nano_graphrag._utils import compute_mdhash_id, logger

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


async def _process_batch_with_tracking(
    documents: list,
    doc_ids: list,
    job_id: str,
    graphrag: GraphRAG,
    job_manager: JobManager
):
    """Process document batch with job tracking."""
    try:
        # Update job to processing
        await job_manager.update_job_status(job_id, JobStatus.PROCESSING)
        await job_manager.update_job_progress(job_id, 0, "chunking")

        # Log document statistics
        total_chars = sum(len(doc) for doc in documents)
        logger.info(f"Job {job_id}: Starting batch processing for {len(documents)} documents ({total_chars:,} total chars)")

        # Process documents
        for i, content in enumerate(documents):
            try:
                await job_manager.update_job_progress(
                    job_id,
                    i,
                    f"processing document {i+1}/{len(documents)}"
                )
                await graphrag.ainsert(content)
            except Exception as e:
                logger.error(f"Job {job_id}: Failed to process document {i}: {e}")
                logger.error(f"Job {job_id}: Traceback: {traceback.format_exc()}")

        # Mark as completed
        await job_manager.update_job_progress(
            job_id,
            len(documents),
            "completed"
        )
        await job_manager.update_job_status(job_id, JobStatus.COMPLETED)
        logger.info(f"Job {job_id}: Successfully completed batch processing")

    except Exception as e:
        logger.error(f"Job {job_id}: Failed to process batch: {type(e).__name__}: {e}")
        logger.error(f"Job {job_id}: Full traceback:\n{traceback.format_exc()}")
        await job_manager.update_job_status(job_id, JobStatus.FAILED, str(e))


@router.post("/batch", response_model=JobResponse, status_code=201)
async def insert_batch(
    batch: BatchDocumentInsert,
    background_tasks: BackgroundTasks,
    graphrag: GraphRAG = Depends(get_graphrag),
    redis_client = Depends(get_redis)
) -> JobResponse:
    """Insert multiple documents in batch with job tracking."""
    doc_ids = []
    documents = []

    for doc in batch.documents:
        doc_id = doc.doc_id or compute_mdhash_id(doc.content, prefix="doc-")
        doc_ids.append(doc_id)
        documents.append(doc.content)

    # Create job
    job_manager = JobManager(redis_client)
    job_id = await job_manager.create_job("batch_insert", doc_ids)

    # Schedule processing as background task
    background_tasks.add_task(
        _process_batch_with_tracking,
        documents,
        doc_ids,
        job_id,
        graphrag,
        job_manager
    )

    # Return job response
    job = await job_manager.get_job(job_id)
    return job


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