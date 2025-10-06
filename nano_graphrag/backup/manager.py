"""Backup and restore orchestration for GraphRAG storage backends."""

import asyncio
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from ..graphrag import GraphRAG
from .._utils import logger
from .exporters import Neo4jExporter, QdrantExporter, KVExporter
from .models import BackupManifest, BackupMetadata
from .utils import (
    create_archive,
    extract_archive,
    compute_directory_checksum,
    generate_backup_id,
    save_manifest,
    load_manifest,
)


class BackupManager:
    """Orchestrate backup and restore operations across all storage backends."""

    def __init__(self, graphrag: GraphRAG, backup_dir: str = "./backups"):
        """Initialize backup manager.

        Args:
            graphrag: GraphRAG instance with configured storage backends
            backup_dir: Directory for backup archives
        """
        self.graphrag = graphrag
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    async def create_backup(
        self,
        backup_id: Optional[str] = None
    ) -> BackupMetadata:
        """Create full backup of all storage backends.

        Args:
            backup_id: Optional custom backup ID. If None, generates timestamp-based ID.

        Returns:
            BackupMetadata with backup information
        """
        backup_id = backup_id or generate_backup_id()
        logger.info(f"Starting backup: {backup_id}")

        # Create temporary directory for exports
        temp_dir = self.backup_dir / f"temp_{backup_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Export all backends
            graph_stats = await self._export_graph(temp_dir)
            vector_stats = await self._export_vectors(temp_dir)
            kv_stats = await self._export_kv(temp_dir)

            # Combine statistics
            statistics = {
                **graph_stats,
                **vector_stats,
                **kv_stats
            }

            # Save GraphRAG config for reference
            config_path = temp_dir / "config" / "graphrag_config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            import json
            from dataclasses import asdict
            with open(config_path, "w") as f:
                json.dump(asdict(self.graphrag.config), f, indent=2)

            # Create manifest
            manifest = BackupManifest(
                backup_id=backup_id,
                created_at=datetime.now(timezone.utc),
                nano_graphrag_version=self._get_version(),
                storage_backends=self._get_backend_types(),
                statistics=statistics,
                checksum=""  # Will be computed
            )

            # Save manifest WITHOUT checksum field to temp directory
            manifest_path = temp_dir / "manifest.json"
            await save_manifest(manifest.model_dump(exclude={"checksum"}), manifest_path)

            # Compute checksum of payload directory (includes manifest without checksum field)
            checksum = compute_directory_checksum(temp_dir)

            # Update manifest object and save WITH checksum field
            manifest.checksum = checksum
            await save_manifest(manifest.model_dump(), manifest_path)

            # Create archive with finalized manifest
            archive_path = self.backup_dir / f"{backup_id}.ngbak"
            archive_size = await create_archive(temp_dir, archive_path)

            # Save checksum alongside archive for convenience
            checksum_path = self.backup_dir / f"{backup_id}.checksum"
            with open(checksum_path, "w") as f:
                f.write(checksum)

            logger.info(f"Backup complete: {backup_id} ({archive_size:,} bytes)")

            # Return metadata
            return BackupMetadata(
                backup_id=backup_id,
                created_at=manifest.created_at,
                size_bytes=archive_size,
                backends=manifest.storage_backends,
                statistics=manifest.statistics
            )

        finally:
            # Clean up temp directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    async def restore_backup(self, backup_id: str) -> None:
        """Restore from backup archive.

        Args:
            backup_id: Backup ID to restore
        """
        archive_path = self.backup_dir / f"{backup_id}.ngbak"

        if not archive_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_id}")

        logger.info(f"Starting restore: {backup_id}")

        # Create temporary extraction directory
        temp_dir = self.backup_dir / f"restore_{backup_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Extract archive
            await extract_archive(archive_path, temp_dir)

            # Load and verify manifest
            manifest_path = temp_dir / "manifest.json"
            manifest_data = await load_manifest(manifest_path)
            manifest = BackupManifest(**manifest_data)

            # Verify payload checksum for data integrity
            if manifest.checksum:
                # Save manifest WITHOUT checksum field for verification
                stored_checksum = manifest.checksum
                await save_manifest(manifest.model_dump(exclude={"checksum"}), manifest_path)

                # Compute checksum (same way as backup: manifest without checksum field)
                computed_checksum = compute_directory_checksum(temp_dir)

                # Restore full manifest
                await save_manifest(manifest.model_dump(), manifest_path)

                if computed_checksum == stored_checksum:
                    logger.info(f"Payload checksum verified: {stored_checksum}")
                else:
                    logger.warning(f"Checksum mismatch! Expected: {stored_checksum}, Got: {computed_checksum}")

            # Restore backends
            await self._restore_graph(temp_dir)
            await self._restore_vectors(temp_dir)
            await self._restore_kv(temp_dir)

            logger.info(f"Restore complete: {backup_id}")

        finally:
            # Clean up temp directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    async def list_backups(self) -> List[BackupMetadata]:
        """List all available backups.

        Returns:
            List of BackupMetadata
        """
        backups = []

        for archive_path in self.backup_dir.glob("*.ngbak"):
            try:
                # Read checksum from external file (created during backup)
                backup_id = archive_path.stem
                checksum_path = self.backup_dir / f"{backup_id}.checksum"

                temp_dir = self.backup_dir / f"read_{backup_id}"
                temp_dir.mkdir(parents=True, exist_ok=True)

                try:
                    await extract_archive(archive_path, temp_dir)

                    manifest_path = temp_dir / "manifest.json"
                    manifest_data = await load_manifest(manifest_path)
                    manifest = BackupManifest(**manifest_data)

                    # Verify payload checksum if external checksum file exists
                    if checksum_path.exists():
                        with open(checksum_path, "r") as f:
                            stored_checksum = f.read().strip()

                        # Manifest checksum should match (it's payload checksum)
                        if manifest.checksum != stored_checksum:
                            logger.warning(f"Checksum mismatch for {backup_id}: manifest={manifest.checksum}, file={stored_checksum}")

                    backups.append(BackupMetadata(
                        backup_id=manifest.backup_id,
                        created_at=manifest.created_at,
                        size_bytes=archive_path.stat().st_size,
                        backends=manifest.storage_backends,
                        statistics=manifest.statistics
                    ))
                finally:
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir)

            except Exception as e:
                logger.warning(f"Failed to read backup {archive_path.name}: {e}")

        # Sort by creation time (newest first)
        backups.sort(key=lambda b: b.created_at, reverse=True)

        return backups

    async def delete_backup(self, backup_id: str) -> bool:
        """Delete backup archive.

        Args:
            backup_id: Backup ID to delete

        Returns:
            True if deleted, False if not found
        """
        archive_path = self.backup_dir / f"{backup_id}.ngbak"
        checksum_path = self.backup_dir / f"{backup_id}.checksum"

        if not archive_path.exists():
            return False

        archive_path.unlink()

        # Also delete checksum file if it exists
        if checksum_path.exists():
            checksum_path.unlink()

        logger.info(f"Deleted backup: {backup_id}")

        return True

    async def get_backup_path(self, backup_id: str) -> Optional[Path]:
        """Get path to backup archive.

        Args:
            backup_id: Backup ID

        Returns:
            Path to archive or None if not found
        """
        archive_path = self.backup_dir / f"{backup_id}.ngbak"
        return archive_path if archive_path.exists() else None

    # Private helper methods

    async def _export_graph(self, output_dir: Path) -> Dict[str, int]:
        """Export graph storage."""
        exporter = Neo4jExporter(self.graphrag.chunk_entity_relation_graph)
        graph_dir = output_dir / "graph"
        await exporter.export(graph_dir)
        return await exporter.get_statistics()

    async def _export_vectors(self, output_dir: Path) -> Dict[str, int]:
        """Export vector storage."""
        stats = {}

        # Export entities vector database
        if self.graphrag.entities_vdb is not None:
            entities_exporter = QdrantExporter(self.graphrag.entities_vdb)
            await entities_exporter.export(output_dir)
            entities_stats = await entities_exporter.get_statistics()
            stats.update({f"entities_{k}": v for k, v in entities_stats.items()})

        # Export chunks vector database (if naive RAG enabled)
        if self.graphrag.chunks_vdb is not None:
            chunks_exporter = QdrantExporter(self.graphrag.chunks_vdb)
            await chunks_exporter.export(output_dir)
            chunks_stats = await chunks_exporter.get_statistics()
            stats.update({f"chunks_{k}": v for k, v in chunks_stats.items()})

        return stats

    async def _export_kv(self, output_dir: Path) -> Dict[str, int]:
        """Export key-value storages."""
        # Collect all KV storages
        kv_storages = {
            "full_docs": self.graphrag.full_docs,
            "text_chunks": self.graphrag.text_chunks,
            "community_reports": self.graphrag.community_reports,
            "llm_response_cache": self.graphrag.llm_response_cache
        }

        exporter = KVExporter(kv_storages)
        await exporter.export(output_dir)
        return await exporter.get_statistics()

    async def _restore_graph(self, input_dir: Path) -> None:
        """Restore graph storage."""
        exporter = Neo4jExporter(self.graphrag.chunk_entity_relation_graph)
        dump_file = input_dir / "graph" / "neo4j.dump"
        await exporter.restore(dump_file)

    async def _restore_vectors(self, input_dir: Path) -> None:
        """Restore vector storage."""
        snapshot_dir = input_dir / "qdrant"

        # Restore entities vector database
        if self.graphrag.entities_vdb is not None:
            entities_exporter = QdrantExporter(self.graphrag.entities_vdb)
            await entities_exporter.restore(snapshot_dir)

        # Restore chunks vector database (if naive RAG enabled)
        if self.graphrag.chunks_vdb is not None:
            chunks_exporter = QdrantExporter(self.graphrag.chunks_vdb)
            await chunks_exporter.restore(snapshot_dir)

    async def _restore_kv(self, input_dir: Path) -> None:
        """Restore key-value storages."""
        kv_storages = {
            "full_docs": self.graphrag.full_docs,
            "text_chunks": self.graphrag.text_chunks,
            "community_reports": self.graphrag.community_reports,
            "llm_response_cache": self.graphrag.llm_response_cache
        }

        exporter = KVExporter(kv_storages)
        kv_dir = input_dir / "kv"
        await exporter.restore(kv_dir)

    def _get_version(self) -> str:
        """Get nano-graphrag version."""
        try:
            from .. import __version__
            return __version__
        except ImportError:
            return "unknown"

    def _get_backend_types(self) -> Dict[str, str]:
        """Get storage backend types."""
        return {
            "graph": type(self.graphrag.chunk_entity_relation_graph).__name__.replace("Storage", "").lower(),
            "vector": type(self.graphrag.entities_vdb).__name__.replace("VectorStorage", "").replace("Storage", "").lower(),
            "kv": type(self.graphrag.full_docs).__name__.replace("KVStorage", "").replace("Storage", "").lower()
        }
