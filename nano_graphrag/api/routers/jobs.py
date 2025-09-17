"""Job tracking router."""
import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from nano_graphrag.api.dependencies import get_redis
from nano_graphrag.api.jobs import JobManager
from nano_graphrag.api.models import JobResponse, JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])
templates = Jinja2Templates(directory="nano_graphrag/api/templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def jobs_dashboard(request: Request):
    """Serve the main dashboard HTML page."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/", response_model=List[JobResponse])
async def list_jobs(
    status: Optional[JobStatus] = None,
    limit: int = 100,
    redis_client=Depends(get_redis),
):
    """List all jobs with optional status filter."""
    job_manager = JobManager(redis_client)
    jobs = await job_manager.list_jobs(status=status, limit=limit)
    return jobs


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    redis_client=Depends(get_redis),
):
    """Get specific job details."""
    job_manager = JobManager(redis_client)
    job = await job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return job


@router.get("/{job_id}/stream")
async def stream_job_progress(
    job_id: str,
    redis_client=Depends(get_redis),
):
    """Stream job progress updates via Server-Sent Events."""
    async def event_generator():
        job_manager = JobManager(redis_client)
        last_status = None
        last_progress = None

        while True:
            job = await job_manager.get_job(job_id)

            if not job:
                yield f"data: {{'error': 'Job not found'}}\n\n"
                break

            # Send update if status or progress changed
            if job.status != last_status or job.progress != last_progress:
                yield f"data: {job.model_dump_json()}\n\n"
                last_status = job.status
                last_progress = job.progress

            # Stop streaming if job is complete or failed
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                break

            await asyncio.sleep(1)  # Poll every second

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )