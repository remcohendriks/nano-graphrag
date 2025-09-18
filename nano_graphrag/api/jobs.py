"""Job tracking for async document processing."""
import asyncio
import json
import os
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from pydantic import BaseModel

from nano_graphrag._utils import logger
from nano_graphrag.api.models import JobProgress, JobResponse, JobStatus


class JobManager:
    """Manages job lifecycle and tracking with Redis backend."""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        # Configurable TTL via environment variable (default: 7 days)
        self.job_ttl = int(os.getenv("REDIS_JOB_TTL", "604800"))

    async def create_job(
        self,
        job_type: str,
        doc_ids: List[str],
        metadata: Optional[Dict] = None
    ) -> str:
        """Create a new job and store in Redis."""
        job_id = str(uuid.uuid4())

        job_data = JobResponse(
            job_id=job_id,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            doc_ids=doc_ids,
            progress=JobProgress(
                current=0,
                total=len(doc_ids),
                phase="initializing"
            ),
            metadata=metadata or {}
        )

        if self.redis:
            await self.redis.setex(
                f"job:{job_id}",
                self.job_ttl,
                job_data.model_dump_json()
            )

        logger.info(f"Created job {job_id} for {len(doc_ids)} documents")
        return job_id

    async def get_job(self, job_id: str) -> Optional[JobResponse]:
        """Retrieve job details from Redis."""
        if not self.redis:
            return None

        job_data = await self.redis.get(f"job:{job_id}")
        if job_data:
            return JobResponse.model_validate_json(job_data)
        return None

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error: Optional[str] = None
    ) -> bool:
        """Update job status."""
        if not self.redis:
            return False

        job = await self.get_job(job_id)
        if not job:
            return False

        job.status = status
        if status == JobStatus.COMPLETED:
            job.completed_at = datetime.now(timezone.utc)
        elif status == JobStatus.FAILED:
            job.error = error
            job.completed_at = datetime.now(timezone.utc)

        await self.redis.setex(
            f"job:{job_id}",
            self.job_ttl,
            job.model_dump_json()
        )

        logger.info(f"Updated job {job_id} status to {status}")
        return True

    async def update_job_progress(
        self,
        job_id: str,
        current: int,
        phase: str
    ) -> bool:
        """Update job progress."""
        if not self.redis:
            return False

        job = await self.get_job(job_id)
        if not job:
            return False

        job.progress.current = current
        job.progress.phase = phase

        await self.redis.setex(
            f"job:{job_id}",
            self.job_ttl,
            job.model_dump_json()
        )

        return True

    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 100
    ) -> List[JobResponse]:
        """List all jobs, optionally filtered by status."""
        if not self.redis:
            return []

        # Use SCAN instead of KEYS to avoid blocking Redis
        cursor = 0
        job_keys = []

        while True:
            cursor, keys = await self.redis.scan(
                cursor, match="job:*", count=100
            )
            job_keys.extend(keys)

            # Stop if we have enough keys or finished scanning
            if cursor == 0 or len(job_keys) >= limit * 2:  # Get extra to account for filtering
                break

        jobs = []
        for key in job_keys:
            if len(jobs) >= limit:
                break

            job_data = await self.redis.get(key)
            if job_data:
                try:
                    job = JobResponse.model_validate_json(job_data)
                    if status is None or job.status == status:
                        jobs.append(job)
                except Exception as e:
                    logger.warning(f"Failed to parse job data for {key}: {e}")
                    continue

        # Sort by created_at descending
        jobs.sort(key=lambda x: x.created_at, reverse=True)
        return jobs[:limit]

    async def verify_document_indexed(
        self,
        doc_id: str,
        graphrag: Any
    ) -> bool:
        """Verify if a document has been successfully indexed."""
        try:
            # Check if document exists in KV storage
            doc = await graphrag.chunk_entity_relation_graph.get(doc_id)
            return doc is not None
        except Exception:
            return False