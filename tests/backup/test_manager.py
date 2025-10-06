"""Tests for BackupManager."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from dataclasses import dataclass

from nano_graphrag.backup.manager import BackupManager
from nano_graphrag.backup.models import BackupManifest


class MockStorage:
    """Mock storage backend for testing."""

    def __init__(self, name: str):
        self.name = name


class MockGraphRAG:
    """Mock GraphRAG instance for testing."""

    def __init__(self):
        self.chunk_entity_relation_graph = MockStorage("neo4j")
        self.entities_vdb = MockStorage("qdrant")
        self.chunks_vdb = None  # Default: naive RAG disabled
        self.full_docs = MockStorage("json")
        self.text_chunks = MockStorage("json")
        self.community_reports = MockStorage("json")
        self.llm_response_cache = MockStorage("json")

        # Add config as a simple object that can be serialized
        @dataclass
        class MockConfig:
            test: str = "config"

        self.config = MockConfig()


@pytest.fixture
def mock_graphrag():
    """Create mock GraphRAG instance."""
    return MockGraphRAG()


@pytest.fixture
def temp_backup_dir():
    """Create temporary backup directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.mark.asyncio
async def test_backup_manager_initialization(mock_graphrag, temp_backup_dir):
    """Test BackupManager initialization."""
    manager = BackupManager(mock_graphrag, str(temp_backup_dir))

    assert manager.graphrag == mock_graphrag
    assert manager.backup_dir == temp_backup_dir
    assert temp_backup_dir.exists()


@pytest.mark.asyncio
@patch('nano_graphrag.backup.manager.Neo4jExporter')
@patch('nano_graphrag.backup.manager.QdrantExporter')
@patch('nano_graphrag.backup.manager.KVExporter')
async def test_create_backup(
    mock_kv_exporter,
    mock_qdrant_exporter,
    mock_neo4j_exporter,
    mock_graphrag,
    temp_backup_dir
):
    """Test backup creation."""
    # Setup mocks
    neo4j_instance = mock_neo4j_exporter.return_value
    neo4j_instance.export = AsyncMock(return_value=Path("/fake/neo4j.dump"))
    neo4j_instance.get_statistics = AsyncMock(return_value={
        "entities": 100,
        "relationships": 200,
        "communities": 10
    })

    qdrant_instance = mock_qdrant_exporter.return_value
    qdrant_instance.export = AsyncMock(return_value=Path("/fake/qdrant"))
    qdrant_instance.get_statistics = AsyncMock(return_value={
        "vectors": 100,
        "dimensions": 1536
    })

    kv_instance = mock_kv_exporter.return_value
    kv_instance.export = AsyncMock(return_value=Path("/fake/kv"))
    kv_instance.get_statistics = AsyncMock(return_value={
        "documents": 10,
        "chunks": 50,
        "reports": 5
    })

    manager = BackupManager(mock_graphrag, str(temp_backup_dir))

    # Create backup
    async def mock_create_archive(source_dir, archive_path):
        # Create the actual file for stat() to work
        archive_path.write_text("fake archive")
        return 1024

    with patch('nano_graphrag.backup.manager.create_archive', new=mock_create_archive):
        with patch('nano_graphrag.backup.manager.compute_directory_checksum', return_value="sha256:test123"):
            metadata = await manager.create_backup(backup_id="test_backup")

    # Verify metadata
    assert metadata.backup_id == "test_backup"
    assert metadata.size_bytes > 0  # Size should be positive
    assert "mock" in metadata.backends.values()  # Mock storage types
    assert metadata.statistics["entities"] == 100
    assert metadata.statistics["documents"] == 10


@pytest.mark.asyncio
async def test_list_backups(mock_graphrag, temp_backup_dir):
    """Test listing backups."""
    manager = BackupManager(mock_graphrag, str(temp_backup_dir))

    # Create mock backup archives
    with patch('nano_graphrag.backup.manager.extract_archive', new=AsyncMock()):
        with patch('nano_graphrag.backup.manager.load_manifest', new=AsyncMock(return_value={
            "backup_id": "backup1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "nano_graphrag_version": "0.1.0",
            "storage_backends": {"graph": "neo4j"},
            "statistics": {"entities": 100},
            "checksum": "sha256:test"
        })):
            # Create a fake .ngbak file
            (temp_backup_dir / "backup1.ngbak").write_text("fake backup")

            backups = await manager.list_backups()

            assert len(backups) == 1
            assert backups[0].backup_id == "backup1"


@pytest.mark.asyncio
async def test_delete_backup(mock_graphrag, temp_backup_dir):
    """Test backup deletion."""
    manager = BackupManager(mock_graphrag, str(temp_backup_dir))

    # Create a fake backup file
    backup_file = temp_backup_dir / "test_backup.ngbak"
    backup_file.write_text("fake backup")

    # Delete backup
    deleted = await manager.delete_backup("test_backup")
    assert deleted is True
    assert not backup_file.exists()

    # Try to delete non-existent backup
    deleted = await manager.delete_backup("non_existent")
    assert deleted is False


@pytest.mark.asyncio
async def test_get_backup_path(mock_graphrag, temp_backup_dir):
    """Test getting backup path."""
    manager = BackupManager(mock_graphrag, str(temp_backup_dir))

    # Create a fake backup file
    backup_file = temp_backup_dir / "test_backup.ngbak"
    backup_file.write_text("fake backup")

    # Get existing backup path
    path = await manager.get_backup_path("test_backup")
    assert path == backup_file
    assert path.exists()

    # Get non-existent backup path
    path = await manager.get_backup_path("non_existent")
    assert path is None
