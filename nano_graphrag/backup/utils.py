"""Utility functions for backup/restore operations."""

import hashlib
import tarfile
import json
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timezone

from .._utils import logger


async def create_archive(source_dir: Path, output_path: Path) -> int:
    """Create tar.gz archive from directory.

    Args:
        source_dir: Directory to archive
        output_path: Output .ngbak file path

    Returns:
        Size of created archive in bytes
    """
    logger.info(f"Creating archive: {output_path}")

    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(source_dir, arcname=".")

    archive_size = output_path.stat().st_size
    logger.info(f"Archive created: {archive_size:,} bytes")

    return archive_size


async def extract_archive(archive_path: Path, output_dir: Path) -> None:
    """Extract tar.gz archive to directory.

    Args:
        archive_path: Path to .ngbak archive
        output_dir: Directory to extract to
    """
    logger.info(f"Extracting archive: {archive_path} to {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(output_dir)

    logger.info("Archive extracted successfully")


def compute_checksum(file_path: Path) -> str:
    """Compute SHA-256 checksum of file.

    Args:
        file_path: Path to file

    Returns:
        SHA-256 checksum as hex string with 'sha256:' prefix
    """
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)

    return f"sha256:{sha256.hexdigest()}"


def compute_directory_checksum(directory: Path) -> str:
    """Compute SHA-256 checksum of directory contents.

    Computes a deterministic checksum by hashing files in sorted order.
    This enables including the checksum in the manifest without creating
    a self-reference paradox.

    Args:
        directory: Directory to compute checksum for

    Returns:
        SHA-256 checksum as hex string with 'sha256:' prefix
    """
    sha256 = hashlib.sha256()

    # Get all files in sorted order for deterministic hash
    all_files = sorted(directory.rglob("*"))

    for file_path in all_files:
        if file_path.is_file():
            # Hash relative path
            relative_path = file_path.relative_to(directory)
            sha256.update(str(relative_path).encode('utf-8'))

            # Hash file contents
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)

    return f"sha256:{sha256.hexdigest()}"


def verify_checksum(file_path: Path, expected_checksum: str) -> bool:
    """Verify file checksum.

    Args:
        file_path: Path to file
        expected_checksum: Expected checksum (with 'sha256:' prefix)

    Returns:
        True if checksum matches, False otherwise
    """
    actual_checksum = compute_checksum(file_path)
    return actual_checksum == expected_checksum


def generate_backup_id() -> str:
    """Generate backup ID with timestamp.

    Returns:
        Backup ID in format: snapshot_YYYY-MM-DDTHH-MM-SSZ
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"snapshot_{timestamp}"


async def save_manifest(manifest: Dict[str, Any], output_path: Path) -> None:
    """Save manifest JSON to file.

    Args:
        manifest: Manifest dictionary
        output_path: Output file path
    """
    with open(output_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    logger.debug(f"Manifest saved: {output_path}")


async def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load manifest JSON from file.

    Args:
        manifest_path: Manifest file path

    Returns:
        Manifest dictionary
    """
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    logger.debug(f"Manifest loaded: {manifest_path}")
    return manifest
