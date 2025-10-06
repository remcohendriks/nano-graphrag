"""Backup and restore API endpoints."""

import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from typing import List
from pathlib import Path

from ..models import JobResponse, JobStatus
from ..dependencies import get_graphrag, get_redis
from ..jobs import JobManager
from nano_graphrag import GraphRAG
from nano_graphrag.backup import BackupManager
from nano_graphrag.backup.models import BackupMetadata
from nano_graphrag._utils import logger

router = APIRouter(prefix="/backup", tags=["backup"])

# Get backup directory from environment
BACKUP_DIR = os.getenv("BACKUP_DIR", "./backups")


def get_backup_manager(graphrag: GraphRAG = Depends(get_graphrag)) -> BackupManager:
    """Dependency to get BackupManager instance."""
    return BackupManager(graphrag, BACKUP_DIR)


async def _create_backup_task(
    backup_manager: BackupManager,
    job_manager: JobManager,
    job_id: str
):
    """Background task to create backup."""
    try:
        await job_manager.update_job_status(job_id, JobStatus.PROCESSING)

        # Create backup
        metadata = await backup_manager.create_backup()

        # Store backup metadata in job
        job = await job_manager.get_job(job_id)
        if job:
            job.metadata["backup_id"] = metadata.backup_id
            job.metadata["size_bytes"] = metadata.size_bytes
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)

            if job_manager.redis:
                await job_manager.redis.setex(
                    f"job:{job_id}",
                    job_manager.job_ttl,
                    job.model_dump_json()
                )

        logger.info(f"Backup job {job_id} completed: {metadata.backup_id}")

    except Exception as e:
        logger.error(f"Backup job {job_id} failed: {e}")
        await job_manager.update_job_status(job_id, JobStatus.FAILED, str(e))


@router.post("", response_model=JobResponse)
async def create_backup(
    background_tasks: BackgroundTasks,
    graphrag: GraphRAG = Depends(get_graphrag),
    backup_manager: BackupManager = Depends(get_backup_manager),
    redis_client = Depends(get_redis)
) -> JobResponse:
    """Create new backup asynchronously.

    Returns job ID for tracking backup progress.
    """
    job_manager = JobManager(redis_client)

    # Create job
    job_id = await job_manager.create_job(
        job_type="backup",
        doc_ids=[],  # No documents for backup job
        metadata={"operation": "backup"}
    )

    # Schedule backup task
    background_tasks.add_task(
        _create_backup_task,
        backup_manager,
        job_manager,
        job_id
    )

    # Return job info
    job = await job_manager.get_job(job_id)
    return job


@router.get("", response_model=List[BackupMetadata])
async def list_backups(
    backup_manager: BackupManager = Depends(get_backup_manager)
) -> List[BackupMetadata]:
    """List all available backups."""
    backups = await backup_manager.list_backups()
    return backups


@router.get("/{backup_id}/download")
async def download_backup(
    backup_id: str,
    backup_manager: BackupManager = Depends(get_backup_manager)
) -> FileResponse:
    """Download backup archive as .ngbak file."""
    backup_path = await backup_manager.get_backup_path(backup_id)

    if not backup_path:
        raise HTTPException(status_code=404, detail=f"Backup not found: {backup_id}")

    return FileResponse(
        path=backup_path,
        media_type="application/gzip",
        filename=f"{backup_id}.ngbak",
        headers={"Content-Disposition": f"attachment; filename={backup_id}.ngbak"}
    )


async def _restore_backup_task(
    backup_manager: BackupManager,
    job_manager: JobManager,
    job_id: str,
    backup_id: str
):
    """Background task to restore backup."""
    try:
        await job_manager.update_job_status(job_id, JobStatus.PROCESSING)

        # Restore backup
        await backup_manager.restore_backup(backup_id)

        await job_manager.update_job_status(job_id, JobStatus.COMPLETED)
        logger.info(f"Restore job {job_id} completed: {backup_id}")

    except Exception as e:
        logger.error(f"Restore job {job_id} failed: {e}")
        await job_manager.update_job_status(job_id, JobStatus.FAILED, str(e))


@router.post("/restore", response_model=JobResponse)
async def restore_backup(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    backup_manager: BackupManager = Depends(get_backup_manager),
    redis_client = Depends(get_redis)
) -> JobResponse:
    """Restore from uploaded backup archive.

    Upload a .ngbak file to restore the system state.
    Returns job ID for tracking restore progress.
    """
    if not file.filename.endswith(".ngbak"):
        raise HTTPException(status_code=400, detail="File must be a .ngbak archive")

    # Extract backup_id from filename
    backup_id = file.filename.replace(".ngbak", "")

    # Save uploaded file
    backup_path = Path(BACKUP_DIR) / file.filename
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    with open(backup_path, "wb") as f:
        content = await file.read()
        f.write(content)

    logger.info(f"Uploaded backup file: {backup_path} ({len(content):,} bytes)")

    # Create restore job
    job_manager = JobManager(redis_client)
    job_id = await job_manager.create_job(
        job_type="restore",
        doc_ids=[],
        metadata={"operation": "restore", "backup_id": backup_id}
    )

    # Schedule restore task
    background_tasks.add_task(
        _restore_backup_task,
        backup_manager,
        job_manager,
        job_id,
        backup_id
    )

    # Return job info
    job = await job_manager.get_job(job_id)
    return job


@router.delete("/{backup_id}")
async def delete_backup(
    backup_id: str,
    backup_manager: BackupManager = Depends(get_backup_manager)
) -> dict:
    """Delete a backup archive."""
    deleted = await backup_manager.delete_backup(backup_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Backup not found: {backup_id}")

    return {"message": f"Backup deleted: {backup_id}"}
