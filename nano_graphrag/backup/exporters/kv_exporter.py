"""Key-Value storage backup/restore exporter (Redis/JSON)."""

import json
import shutil
import asyncio
from pathlib import Path
from typing import Dict, Any, List

from ..._utils import logger


class KVExporter:
    """Export and restore key-value storage (Redis or JSON)."""

    def __init__(self, storages: Dict[str, Any]):
        """Initialize exporter with KV storage backends.

        Args:
            storages: Dictionary mapping namespace to storage instance
                     (e.g., {'full_docs': storage, 'text_chunks': storage, ...})
        """
        self.storages = storages

    async def export(self, output_dir: Path) -> Path:
        """Export all KV namespaces to JSON files.

        Args:
            output_dir: Directory to write export files

        Returns:
            Path to KV export directory
        """
        kv_dir = output_dir / "kv"
        kv_dir.mkdir(parents=True, exist_ok=True)

        for namespace, storage in self.storages.items():
            await self._export_namespace(storage, namespace, kv_dir)

        logger.info(f"KV export complete: {kv_dir}")
        return kv_dir

    async def _export_namespace(self, storage: Any, namespace: str, output_dir: Path) -> None:
        """Export single KV namespace.

        Args:
            storage: Storage backend instance
            namespace: Namespace identifier
            output_dir: Output directory
        """
        # Check storage type
        storage_type = type(storage).__name__

        if storage_type == "JsonKVStorage":
            # JSON storage - just copy the file
            await self._export_json_storage(storage, namespace, output_dir)
        elif storage_type == "RedisKVStorage":
            # Redis storage - export all keys
            await self._export_redis_storage(storage, namespace, output_dir)
        else:
            logger.warning(f"Unknown KV storage type: {storage_type}")

    async def _export_json_storage(self, storage: Any, namespace: str, output_dir: Path) -> None:
        """Export JSON file storage.

        Args:
            storage: JsonKVStorage instance
            namespace: Namespace identifier
            output_dir: Output directory
        """
        # Get all data from storage
        all_data = await storage.get_by_ids(await storage.all_keys())

        output_file = output_dir / f"{namespace}.json"
        with open(output_file, "w") as f:
            json.dump(all_data, f, indent=2, default=str)

        logger.debug(f"Exported JSON storage: {namespace} ({len(all_data)} items)")

    async def _export_redis_storage(self, storage: Any, namespace: str, output_dir: Path) -> None:
        """Export Redis storage to JSON.

        Args:
            storage: RedisKVStorage instance
            namespace: Namespace identifier
            output_dir: Output directory
        """
        await storage._ensure_initialized()

        prefix = storage._prefix
        logger.info(f"Exporting Redis storage: {namespace} with prefix: {prefix}")

        cursor = 0
        all_keys = []

        while True:
            cursor, keys = await storage._redis_client.scan(
                cursor, match=f"{prefix}*", count=1000
            )
            all_keys.extend(keys)
            if cursor == 0:
                break

        logger.info(f"Found {len(all_keys)} keys in Redis for {namespace}")

        if len(all_keys) > 0:
            sample = all_keys[:3]
            logger.debug(f"Sample keys: {[k.decode() if isinstance(k, bytes) else k for k in sample]}")

        all_data = {}
        for key in all_keys:
            original_key = key.decode() if isinstance(key, bytes) else key
            original_key = original_key.replace(prefix, "", 1)

            value = await storage._redis_client.get(key)
            if value:
                value_str = value.decode() if isinstance(value, bytes) else value
                try:
                    all_data[original_key] = json.loads(value_str)
                except json.JSONDecodeError:
                    all_data[original_key] = value_str

        output_file = output_dir / f"{namespace}.json"
        with open(output_file, "w") as f:
            json.dump(all_data, f, indent=2, default=str)

        logger.info(f"Exported Redis storage: {namespace} ({len(all_data)} items) to {output_file}")

    async def restore(self, kv_dir: Path) -> None:
        """Restore all KV namespaces from JSON files.

        Args:
            kv_dir: Directory containing JSON export files
        """
        for namespace, storage in self.storages.items():
            json_file = kv_dir / f"{namespace}.json"

            if not json_file.exists():
                logger.warning(f"No backup file for namespace: {namespace}")
                continue

            await self._restore_namespace(storage, namespace, json_file)

        logger.info(f"KV restore complete from: {kv_dir}")

    async def _restore_namespace(self, storage: Any, namespace: str, json_file: Path) -> None:
        """Restore single KV namespace.

        Args:
            storage: Storage backend instance
            namespace: Namespace identifier
            json_file: JSON backup file
        """
        with open(json_file, "r") as f:
            data = json.load(f)

        storage_type = type(storage).__name__

        if storage_type == "JsonKVStorage":
            await self._restore_json_storage(storage, data)
        elif storage_type == "RedisKVStorage":
            await self._restore_redis_storage(storage, data)

        logger.debug(f"Restored {namespace}: {len(data)} items")

    async def _restore_json_storage(self, storage: Any, data: Dict[str, Any]) -> None:
        """Restore JSON file storage.

        Args:
            storage: JsonKVStorage instance
            data: Data dictionary to restore
        """
        # Upsert all items
        for key, value in data.items():
            await storage.upsert({key: value})

    async def _restore_redis_storage(self, storage: Any, data: Dict[str, Any]) -> None:
        """Restore Redis storage from JSON data.

        Args:
            storage: RedisKVStorage instance
            data: Data dictionary to restore
        """
        logger.info(f"Restoring Redis storage for namespace: {storage.namespace}")
        logger.info(f"Number of items to restore: {len(data)}")

        if len(data) > 0:
            sample_keys = list(data.keys())[:3]
            logger.debug(f"Sample keys: {sample_keys}")
            for key in sample_keys:
                value = data[key]
                logger.debug(f"Key: {key}, Value type: {type(value)}, Value preview: {str(value)[:100]}")

        await storage.upsert(data)
        logger.info(f"Redis restore completed for {storage.namespace}, upserted {len(data)} items")

    async def get_statistics(self) -> Dict[str, int]:
        """Get KV storage statistics.

        Returns:
            Dictionary with item counts per namespace
        """
        stats = {}

        for namespace, storage in self.storages.items():
            storage_type = type(storage).__name__

            if storage_type == "JsonKVStorage":
                keys = await storage.all_keys()
                stats[namespace] = len(keys)
            elif storage_type == "RedisKVStorage":
                await storage._ensure_initialized()
                prefix = storage._prefix
                cursor = 0
                key_count = 0

                while True:
                    cursor, keys = await storage._redis_client.scan(
                        cursor, match=f"{prefix}*", count=1000
                    )
                    key_count += len(keys)
                    if cursor == 0:
                        break

                stats[namespace] = key_count

        # Aggregate statistics
        return {
            "documents": stats.get("full_docs", 0),
            "chunks": stats.get("text_chunks", 0),
            "reports": stats.get("community_reports", 0)
        }
