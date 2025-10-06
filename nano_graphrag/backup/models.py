"""Data models for backup/restore operations."""

from datetime import datetime
from typing import Dict, Any
from pydantic import BaseModel, Field


class BackupManifest(BaseModel):
    """Backup archive manifest with metadata and statistics."""

    backup_id: str = Field(..., description="Unique backup identifier")
    created_at: datetime = Field(..., description="Backup creation timestamp")
    nano_graphrag_version: str = Field(..., description="nano-graphrag version")
    storage_backends: Dict[str, str] = Field(..., description="Storage backend types")
    statistics: Dict[str, int] = Field(..., description="Data statistics")
    checksum: str = Field(..., description="SHA-256 checksum of archive contents")


class BackupMetadata(BaseModel):
    """Backup metadata for API responses."""

    backup_id: str
    created_at: datetime
    size_bytes: int
    backends: Dict[str, str]
    statistics: Dict[str, int]
