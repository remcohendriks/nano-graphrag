"""Tests for backup utility functions."""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone

from nano_graphrag.backup.utils import (
    create_archive,
    extract_archive,
    compute_checksum,
    verify_checksum,
    generate_backup_id,
    save_manifest,
    load_manifest,
)


@pytest.mark.asyncio
async def test_create_and_extract_archive():
    """Test archive creation and extraction."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create source directory with test files
        source_dir = tmpdir / "source"
        source_dir.mkdir()
        (source_dir / "test1.txt").write_text("Hello World")
        (source_dir / "test2.json").write_text('{"key": "value"}')

        # Create archive
        archive_path = tmpdir / "test.ngbak"
        size = await create_archive(source_dir, archive_path)

        assert archive_path.exists()
        assert size > 0

        # Extract archive
        extract_dir = tmpdir / "extracted"
        await extract_archive(archive_path, extract_dir)

        # Verify extracted files
        assert (extract_dir / "test1.txt").exists()
        assert (extract_dir / "test2.json").exists()
        assert (extract_dir / "test1.txt").read_text() == "Hello World"


def test_compute_and_verify_checksum():
    """Test checksum computation and verification."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("Test content for checksum")
        filepath = Path(f.name)

    try:
        # Compute checksum
        checksum = compute_checksum(filepath)
        assert checksum.startswith("sha256:")
        assert len(checksum) > 10

        # Verify checksum
        assert verify_checksum(filepath, checksum) is True

        # Modify file and verify again
        filepath.write_text("Modified content")
        assert verify_checksum(filepath, checksum) is False

    finally:
        filepath.unlink()


def test_generate_backup_id():
    """Test backup ID generation."""
    backup_id = generate_backup_id()

    assert backup_id.startswith("snapshot_")
    assert "T" in backup_id
    assert "Z" in backup_id


@pytest.mark.asyncio
async def test_save_and_load_manifest():
    """Test manifest save and load."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.json"

        # Create test manifest
        manifest_data = {
            "backup_id": "test_backup",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "nano_graphrag_version": "0.1.0",
            "storage_backends": {"graph": "neo4j", "vector": "qdrant"},
            "statistics": {"entities": 100, "relationships": 200},
            "checksum": "sha256:abc123"
        }

        # Save manifest
        await save_manifest(manifest_data, manifest_path)
        assert manifest_path.exists()

        # Load manifest
        loaded_data = await load_manifest(manifest_path)
        assert loaded_data["backup_id"] == "test_backup"
        assert loaded_data["storage_backends"]["graph"] == "neo4j"
        assert loaded_data["statistics"]["entities"] == 100
