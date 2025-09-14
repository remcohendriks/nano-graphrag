"""Storage adapter for handling both sync and async storage backends."""

import asyncio
import inspect
from typing import Any, Optional, List, Union, Dict


class StorageAdapter:
    """Adapter to handle both synchronous and asynchronous storage backends."""

    def __init__(self, backend):
        """Initialize with a storage backend."""
        self.backend = backend

    async def get_by_id(self, id: str) -> Optional[Any]:
        """Get single item by ID, handling sync/async."""
        if hasattr(self.backend, 'get_by_id'):
            if asyncio.iscoroutinefunction(self.backend.get_by_id):
                return await self.backend.get_by_id(id)
            else:
                # Run sync function in thread pool
                return await asyncio.to_thread(self.backend.get_by_id, id)
        return None

    async def delete_by_id(self, id: str) -> bool:
        """Delete single item by ID, handling sync/async."""
        if hasattr(self.backend, 'delete_by_id'):
            if asyncio.iscoroutinefunction(self.backend.delete_by_id):
                return await self.backend.delete_by_id(id)
            else:
                # Run sync function in thread pool
                return await asyncio.to_thread(self.backend.delete_by_id, id)
        return False

    async def upsert(self, data: Dict[str, Any]) -> None:
        """Upsert data, handling sync/async."""
        if hasattr(self.backend, 'upsert'):
            if asyncio.iscoroutinefunction(self.backend.upsert):
                await self.backend.upsert(data)
            else:
                # Run sync function in thread pool
                await asyncio.to_thread(self.backend.upsert, data)

    async def drop(self) -> None:
        """Drop all data, handling sync/async."""
        if hasattr(self.backend, 'drop'):
            if asyncio.iscoroutinefunction(self.backend.drop):
                await self.backend.drop()
            else:
                # Run sync function in thread pool
                await asyncio.to_thread(self.backend.drop)

    async def check_health(self) -> bool:
        """Check backend health, handling sync/async."""
        if hasattr(self.backend, 'check_health'):
            if asyncio.iscoroutinefunction(self.backend.check_health):
                return await self.backend.check_health()
            else:
                return await asyncio.to_thread(self.backend.check_health)
        # If no health check method, assume healthy if backend exists
        return self.backend is not None