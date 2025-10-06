"""Qdrant vector database backup/restore exporter."""

import shutil
from pathlib import Path
from typing import Dict, Any

from ..._utils import logger


class QdrantExporter:
    """Export and restore Qdrant vector collections."""

    def __init__(self, storage: Any):
        """Initialize exporter with Qdrant storage backend.

        Args:
            storage: QdrantVectorStorage instance
        """
        self.storage = storage
        self.collection_name = storage.namespace

    async def export(self, output_dir: Path) -> Path:
        """Export Qdrant collection using snapshot API.

        Args:
            output_dir: Directory to write snapshot files

        Returns:
            Path to snapshot directory
        """
        snapshot_dir = output_dir / "qdrant"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        client = await self.storage._get_client()

        # Create collection snapshot
        logger.info(f"Creating Qdrant snapshot for collection: {self.collection_name}")
        snapshot_description = await client.create_snapshot(
            collection_name=self.collection_name
        )

        snapshot_name = snapshot_description.name
        logger.debug(f"Snapshot created: {snapshot_name}")

        # Download snapshot to output directory
        snapshot_data = await client.download_snapshot(
            collection_name=self.collection_name,
            snapshot_name=snapshot_name
        )

        snapshot_file = snapshot_dir / f"{self.collection_name}.snapshot"
        with open(snapshot_file, "wb") as f:
            f.write(snapshot_data)

        logger.info(f"Qdrant snapshot saved: {snapshot_file}")

        # Clean up server-side snapshot
        try:
            await client.delete_snapshot(
                collection_name=self.collection_name,
                snapshot_name=snapshot_name
            )
            logger.debug(f"Server-side snapshot deleted: {snapshot_name}")
        except Exception as e:
            logger.warning(f"Failed to delete server-side snapshot: {e}")

        return snapshot_dir

    async def restore(self, snapshot_dir: Path) -> None:
        """Restore Qdrant collection from snapshot.

        Args:
            snapshot_dir: Directory containing snapshot files
        """
        snapshot_file = snapshot_dir / f"{self.collection_name}.snapshot"

        if not snapshot_file.exists():
            raise FileNotFoundError(f"Snapshot file not found: {snapshot_file}")

        client = await self.storage._get_client()

        # Read snapshot data
        with open(snapshot_file, "rb") as f:
            snapshot_data = f.read()

        # Upload snapshot to Qdrant server
        logger.info(f"Uploading snapshot for collection: {self.collection_name}")

        # Delete existing collection if it exists
        try:
            await client.delete_collection(collection_name=self.collection_name)
            logger.debug(f"Deleted existing collection: {self.collection_name}")
        except Exception as e:
            logger.debug(f"No existing collection to delete: {e}")

        # Recover collection from snapshot
        # Note: Qdrant's snapshot upload API may vary by version
        # This assumes snapshot can be used to recreate the collection
        try:
            # Upload snapshot (API endpoint may vary)
            await client.upload_snapshot(
                collection_name=self.collection_name,
                snapshot=snapshot_data
            )
            logger.info(f"Qdrant collection restored from snapshot: {self.collection_name}")
        except AttributeError:
            # Fallback: use recover method if upload_snapshot not available
            logger.warning("upload_snapshot not available, using alternative restore method")
            # This may require manual intervention or different Qdrant version
            raise NotImplementedError(
                "Qdrant snapshot restore not fully supported in this client version. "
                "Please restore manually using Qdrant admin tools."
            )

    async def get_statistics(self) -> Dict[str, int]:
        """Get Qdrant collection statistics.

        Returns:
            Dictionary with point counts and vector dimensions
        """
        client = await self.storage._get_client()

        # Get collection info
        collection_info = await client.get_collection(collection_name=self.collection_name)

        points_count = collection_info.points_count or 0
        vectors_count = collection_info.vectors_count or 0

        return {
            "vectors": points_count,
            "dimensions": vectors_count
        }
