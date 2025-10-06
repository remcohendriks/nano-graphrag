"""Tests for backup router logic without FastAPI dependency."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from nano_graphrag.backup.models import BackupMetadata
from nano_graphrag.backup.manager import BackupManager


@pytest.mark.asyncio
async def test_backup_manager_create_backup_workflow():
    """Test the backup creation workflow that the API would use."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create mock GraphRAG
        mock_graphrag = MagicMock()
        mock_graphrag.chunk_entity_relation_graph = MagicMock()
        mock_graphrag.entities_vdb = MagicMock()
        mock_graphrag.full_docs = MagicMock()
        mock_graphrag.text_chunks = MagicMock()
        mock_graphrag.community_reports = MagicMock()
        mock_graphrag.llm_response_cache = MagicMock()
        mock_graphrag.config = MagicMock()
        mock_graphrag.config.model_dump_json.return_value = '{"test": "config"}'

        # Mock exporters
        with patch('nano_graphrag.backup.manager.Neo4jExporter') as mock_neo4j:
            with patch('nano_graphrag.backup.manager.QdrantExporter') as mock_qdrant:
                with patch('nano_graphrag.backup.manager.KVExporter') as mock_kv:
                    # Setup exporter mocks
                    mock_neo4j.return_value.export = AsyncMock(return_value=Path("/fake/neo4j.dump"))
                    mock_neo4j.return_value.get_statistics = AsyncMock(return_value={
                        "entities": 150,
                        "relationships": 300,
                        "communities": 15
                    })

                    mock_qdrant.return_value.export = AsyncMock(return_value=Path("/fake/qdrant"))
                    mock_qdrant.return_value.get_statistics = AsyncMock(return_value={
                        "vectors": 150,
                        "dimensions": 1536
                    })

                    mock_kv.return_value.export = AsyncMock(return_value=Path("/fake/kv"))
                    mock_kv.return_value.get_statistics = AsyncMock(return_value={
                        "documents": 20,
                        "chunks": 80,
                        "reports": 10
                    })

                    # Mock archive creation
                    async def mock_create_archive(source_dir, archive_path):
                        archive_path.write_text("fake archive data")
                        return len("fake archive data")

                    with patch('nano_graphrag.backup.manager.create_archive', new=mock_create_archive):
                        with patch('nano_graphrag.backup.manager.compute_checksum', return_value="sha256:test123"):
                            manager = BackupManager(mock_graphrag, tmpdir)

                            # This is what the API endpoint does
                            metadata = await manager.create_backup(backup_id="api_test_backup")

                            # Verify the metadata that would be returned to API
                            assert metadata.backup_id == "api_test_backup"
                            assert metadata.size_bytes > 0
                            assert "entities" in metadata.statistics
                            assert metadata.statistics["entities"] == 150
                            assert metadata.statistics["documents"] == 20


@pytest.mark.asyncio
async def test_backup_manager_list_workflow():
    """Test the list backups workflow that the API would use."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create mock GraphRAG
        mock_graphrag = MagicMock()

        # Create a fake backup archive
        backup_archive = tmpdir / "test_backup_123.ngbak"
        backup_archive.write_text("fake archive")

        # Mock extract and load
        with patch('nano_graphrag.backup.manager.extract_archive', new=AsyncMock()):
            with patch('nano_graphrag.backup.manager.load_manifest', new=AsyncMock(return_value={
                "backup_id": "test_backup_123",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "nano_graphrag_version": "0.1.0",
                "storage_backends": {"graph": "neo4j", "vector": "qdrant"},
                "statistics": {"entities": 100, "relationships": 200},
                "checksum": "sha256:abc123"
            })):
                manager = BackupManager(mock_graphrag, str(tmpdir))

                # This is what the API endpoint does
                backups = await manager.list_backups()

                # Verify the list that would be returned to API
                assert len(backups) == 1
                assert backups[0].backup_id == "test_backup_123"
                assert backups[0].size_bytes > 0


@pytest.mark.asyncio
async def test_backup_manager_delete_workflow():
    """Test the delete backup workflow that the API would use."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create mock GraphRAG
        mock_graphrag = MagicMock()

        # Create a fake backup file
        backup_file = tmpdir / "delete_me.ngbak"
        backup_file.write_text("to be deleted")

        manager = BackupManager(mock_graphrag, str(tmpdir))

        # This is what the API endpoint does
        deleted = await manager.delete_backup("delete_me")

        assert deleted is True
        assert not backup_file.exists()


@pytest.mark.asyncio
async def test_backup_manager_get_path_workflow():
    """Test the get backup path workflow that the API would use."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create mock GraphRAG
        mock_graphrag = MagicMock()

        # Create a fake backup file
        backup_file = tmpdir / "download_me.ngbak"
        backup_file.write_text("downloadable content")

        manager = BackupManager(mock_graphrag, str(tmpdir))

        # This is what the API download endpoint does
        path = await manager.get_backup_path("download_me")

        assert path is not None
        assert path.exists()
        assert path.name == "download_me.ngbak"


@pytest.mark.asyncio
async def test_backup_manager_restore_workflow():
    """Test the restore workflow that the API would use."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create mock GraphRAG with all storages
        mock_graphrag = MagicMock()
        mock_graphrag.chunk_entity_relation_graph = MagicMock()
        mock_graphrag.entities_vdb = MagicMock()
        mock_graphrag.full_docs = MagicMock()
        mock_graphrag.text_chunks = MagicMock()
        mock_graphrag.community_reports = MagicMock()
        mock_graphrag.llm_response_cache = MagicMock()

        # Create a fake backup archive
        backup_file = tmpdir / "restore_me.ngbak"
        backup_file.write_text("backup to restore")

        # Mock the restore chain
        with patch('nano_graphrag.backup.manager.extract_archive', new=AsyncMock()):
            with patch('nano_graphrag.backup.manager.load_manifest', new=AsyncMock(return_value={
                "backup_id": "restore_me",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "nano_graphrag_version": "0.1.0",
                "storage_backends": {"graph": "neo4j"},
                "statistics": {},
                "checksum": "sha256:test"
            })):
                with patch('nano_graphrag.backup.manager.Neo4jExporter') as mock_neo4j:
                    with patch('nano_graphrag.backup.manager.QdrantExporter') as mock_qdrant:
                        with patch('nano_graphrag.backup.manager.KVExporter') as mock_kv:
                            mock_neo4j.return_value.restore = AsyncMock()
                            mock_qdrant.return_value.restore = AsyncMock()
                            mock_kv.return_value.restore = AsyncMock()

                            manager = BackupManager(mock_graphrag, str(tmpdir))

                            # This is what the API restore endpoint does
                            await manager.restore_backup("restore_me")

                            # Verify restore was called
                            mock_neo4j.return_value.restore.assert_called_once()
                            mock_qdrant.return_value.restore.assert_called_once()
                            mock_kv.return_value.restore.assert_called_once()
