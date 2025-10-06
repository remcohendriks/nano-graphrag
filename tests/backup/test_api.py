"""Tests for backup API endpoints."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime, timezone
import io

from nano_graphrag.api.app import create_app
from nano_graphrag.backup.models import BackupMetadata


@pytest.fixture
def mock_app():
    """Create test FastAPI app with mocked dependencies."""
    app = create_app()

    # Mock GraphRAG
    app.state.graphrag = MagicMock()
    app.state.redis_client = None

    return app


@pytest.fixture
def client(mock_app):
    """Create test client."""
    return TestClient(mock_app)


def test_create_backup_endpoint(client):
    """Test POST /backup endpoint."""
    with patch('nano_graphrag.api.routers.backup.BackupManager') as mock_manager_class:
        mock_manager = mock_manager_class.return_value
        mock_manager.create_backup = AsyncMock(return_value=BackupMetadata(
            backup_id="test_backup",
            created_at=datetime.now(timezone.utc),
            size_bytes=1024,
            backends={"graph": "neo4j", "vector": "qdrant"},
            statistics={"entities": 100}
        ))

        with patch('nano_graphrag.api.routers.backup.JobManager') as mock_job_manager:
            mock_job_instance = mock_job_manager.return_value
            mock_job_instance.create_job = AsyncMock(return_value="job123")
            mock_job_instance.get_job = AsyncMock(return_value=MagicMock(
                job_id="job123",
                status="pending"
            ))

            response = client.post("/api/v1/backup")

            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "job123"


def test_list_backups_endpoint(client):
    """Test GET /backup endpoint."""
    with patch('nano_graphrag.api.routers.backup.BackupManager') as mock_manager_class:
        mock_manager = mock_manager_class.return_value
        mock_manager.list_backups = AsyncMock(return_value=[
            BackupMetadata(
                backup_id="backup1",
                created_at=datetime.now(timezone.utc),
                size_bytes=1024,
                backends={"graph": "neo4j"},
                statistics={"entities": 100}
            ),
            BackupMetadata(
                backup_id="backup2",
                created_at=datetime.now(timezone.utc),
                size_bytes=2048,
                backends={"graph": "neo4j"},
                statistics={"entities": 200}
            )
        ])

        response = client.get("/api/v1/backup")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["backup_id"] == "backup1"
        assert data[1]["backup_id"] == "backup2"


def test_download_backup_endpoint(client):
    """Test GET /backup/{backup_id}/download endpoint."""
    with tempfile.NamedTemporaryFile(suffix=".ngbak", delete=False) as tmpfile:
        tmpfile.write(b"fake backup content")
        tmppath = Path(tmpfile.name)

    try:
        with patch('nano_graphrag.api.routers.backup.BackupManager') as mock_manager_class:
            mock_manager = mock_manager_class.return_value
            mock_manager.get_backup_path = AsyncMock(return_value=tmppath)

            response = client.get("/api/v1/backup/test_backup/download")

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/gzip"
            assert "attachment" in response.headers["content-disposition"]
    finally:
        tmppath.unlink()


def test_download_backup_not_found(client):
    """Test download with non-existent backup."""
    with patch('nano_graphrag.api.routers.backup.BackupManager') as mock_manager_class:
        mock_manager = mock_manager_class.return_value
        mock_manager.get_backup_path = AsyncMock(return_value=None)

        response = client.get("/api/v1/backup/non_existent/download")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


def test_restore_backup_endpoint(client):
    """Test POST /backup/restore endpoint."""
    with patch('nano_graphrag.api.routers.backup.BackupManager') as mock_manager_class:
        mock_manager = mock_manager_class.return_value
        mock_manager.restore_backup = AsyncMock()

        with patch('nano_graphrag.api.routers.backup.JobManager') as mock_job_manager:
            mock_job_instance = mock_job_manager.return_value
            mock_job_instance.create_job = AsyncMock(return_value="job456")
            mock_job_instance.get_job = AsyncMock(return_value=MagicMock(
                job_id="job456",
                status="pending"
            ))

            # Create fake backup file
            fake_file = io.BytesIO(b"fake backup content")

            response = client.post(
                "/api/v1/backup/restore",
                files={"file": ("test_backup.ngbak", fake_file, "application/gzip")}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "job456"


def test_restore_invalid_file_type(client):
    """Test restore with invalid file type."""
    fake_file = io.BytesIO(b"not a backup")

    response = client.post(
        "/api/v1/backup/restore",
        files={"file": ("test.txt", fake_file, "text/plain")}
    )

    assert response.status_code == 400
    assert "must be a .ngbak archive" in response.json()["detail"]


def test_delete_backup_endpoint(client):
    """Test DELETE /backup/{backup_id} endpoint."""
    with patch('nano_graphrag.api.routers.backup.BackupManager') as mock_manager_class:
        mock_manager = mock_manager_class.return_value
        mock_manager.delete_backup = AsyncMock(return_value=True)

        response = client.delete("/api/v1/backup/test_backup")

        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()


def test_delete_backup_not_found(client):
    """Test delete with non-existent backup."""
    with patch('nano_graphrag.api.routers.backup.BackupManager') as mock_manager_class:
        mock_manager = mock_manager_class.return_value
        mock_manager.delete_backup = AsyncMock(return_value=False)

        response = client.delete("/api/v1/backup/non_existent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
