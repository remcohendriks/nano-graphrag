"""Qdrant vector database backup/restore exporter."""

import httpx
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

        logger.info(f"Creating Qdrant snapshot for collection: {self.collection_name}")
        snapshot_description = await client.create_snapshot(
            collection_name=self.collection_name
        )

        snapshot_name = snapshot_description.name
        logger.debug(f"Snapshot created: {snapshot_name}")

        qdrant_url = getattr(self.storage, "_url", "http://localhost:6333")
        download_url = f"{qdrant_url}/collections/{self.collection_name}/snapshots/{snapshot_name}"

        snapshot_file = snapshot_dir / f"{self.collection_name}.snapshot"

        headers = {}
        api_key = getattr(self.storage, "_api_key", None)
        if api_key:
            headers["api-key"] = api_key

        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(download_url, headers=headers, timeout=300.0)
            response.raise_for_status()

            with open(snapshot_file, "wb") as f:
                f.write(response.content)

        logger.info(f"Qdrant snapshot saved: {snapshot_file}")

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
        logger.info(f"Restoring Qdrant collection from snapshot: {self.collection_name}")

        try:
            await client.delete_collection(collection_name=self.collection_name)
            logger.debug(f"Deleted existing collection: {self.collection_name}")
        except Exception as e:
            logger.debug(f"No existing collection to delete: {e}")

        qdrant_url = getattr(self.storage, "_url", "http://localhost:6333")
        upload_url = f"{qdrant_url}/collections/{self.collection_name}/snapshots/upload?priority=snapshot"

        headers = {}
        api_key = getattr(self.storage, "_api_key", None)
        if api_key:
            headers["api-key"] = api_key

        async with httpx.AsyncClient() as http_client:
            with open(snapshot_file, "rb") as f:
                files = {"snapshot": (snapshot_file.name, f, "application/octet-stream")}
                response = await http_client.post(
                    upload_url,
                    files=files,
                    headers=headers,
                    timeout=300.0
                )
                response.raise_for_status()

        logger.info(f"Qdrant collection restored: {self.collection_name}")

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
