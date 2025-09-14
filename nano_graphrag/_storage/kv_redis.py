"""Redis-based Key-Value storage backend for production deployments."""

import os
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import asyncio
import logging

try:
    import redis.asyncio as aioredis
    from redis.backoff import ExponentialBackoff
    from redis.retry import Retry
    from redis.exceptions import RedisError, ConnectionError as RedisConnectionError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    aioredis = None

from ..base import BaseKVStorage
from .._utils import logger


@dataclass
class RedisKVStorage(BaseKVStorage):
    """Redis-based Key-Value storage with production features."""

    _redis_client: Optional[Any] = field(init=False, default=None)
    _connection_pool: Optional[Any] = field(init=False, default=None)
    _ttl_config: Dict[str, int] = field(init=False, default_factory=dict)
    _initialized: bool = field(init=False, default=False)

    def __post_init__(self):
        """Initialize Redis connection synchronously."""
        if not REDIS_AVAILABLE:
            raise ImportError(
                "Redis support not available. Install with: pip install redis[hiredis]"
            )

        # Setup will be completed in async context
        self._setup_ttl_config()
        self._prefix = f"nano_graphrag:{self.namespace}:"

        # Get Redis configuration
        self.redis_url = self.global_config.get("redis_url", "redis://localhost:6379")
        self.redis_password = self.global_config.get("redis_password", None)
        self.max_connections = self.global_config.get("redis_max_connections", 50)
        self.socket_timeout = self.global_config.get("redis_socket_timeout", 5.0)
        self.connection_timeout = self.global_config.get("redis_connection_timeout", 5.0)
        self.health_check_interval = self.global_config.get("redis_health_check_interval", 30)

    async def _ensure_initialized(self):
        """Ensure Redis connection is initialized."""
        if self._initialized:
            return

        # Configure retry policy
        retry = Retry(
            ExponentialBackoff(cap=10, base=1),
            retries=3,
            supported_errors=(RedisConnectionError, TimeoutError, ConnectionError)
        )

        # Create connection pool
        self._connection_pool = aioredis.ConnectionPool.from_url(
            self.redis_url,
            password=self.redis_password,
            max_connections=self.max_connections,
            socket_timeout=self.socket_timeout,
            connection_timeout=self.connection_timeout,
            decode_responses=False,  # Handle bytes for flexibility
            retry=retry,
            health_check_interval=self.health_check_interval
        )

        # Create Redis client
        self._redis_client = aioredis.Redis(
            connection_pool=self._connection_pool,
            auto_close_connection_pool=False
        )

        # Verify connection
        try:
            await self._redis_client.ping()
            logger.info(f"Connected to Redis for namespace: {self.namespace}")
        except RedisError as e:
            logger.error(f"Redis connection failed: {e}")
            raise

        self._initialized = True

    def _setup_ttl_config(self):
        """Configure TTL settings per namespace."""
        # Default TTLs in seconds
        defaults = {
            "llm_response_cache": 43200,  # 12 hours
            "community_reports": 86400,   # 24 hours
            "text_chunks": 0,             # No expiry
            "full_docs": 0                # No expiry
        }

        # Override with environment variables if set
        for namespace, default_ttl in defaults.items():
            env_key = f"REDIS_TTL_{namespace.upper()}"
            self._ttl_config[namespace] = int(os.getenv(env_key, default_ttl))

    def _get_key(self, id: str) -> str:
        """Generate Redis key with namespace prefix."""
        return f"{self._prefix}{id}"

    def _serialize(self, data: Any) -> bytes:
        """Serialize data to JSON bytes."""
        return json.dumps(data, default=str).encode('utf-8')

    def _deserialize(self, data: bytes) -> Any:
        """Deserialize data from JSON bytes."""
        if data is None:
            return None
        try:
            return json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to deserialize data: {e}")
            return None

    async def all_keys(self) -> List[str]:
        """Get all keys in namespace."""
        await self._ensure_initialized()

        pattern = f"{self._prefix}*"
        keys = []

        # Use SCAN for memory efficiency with large keysets
        async for key in self._redis_client.scan_iter(match=pattern, count=1000):
            # Remove prefix to get original key
            keys.append(key.decode('utf-8').replace(self._prefix, '', 1))

        return keys

    async def get_by_id(self, id: str) -> Optional[Any]:
        """Get single item by ID."""
        await self._ensure_initialized()

        try:
            data = await self._redis_client.get(self._get_key(id))
            return self._deserialize(data)
        except RedisError as e:
            logger.error(f"Redis get error for {id}: {e}")
            raise

    async def get_by_ids(self, ids: List[str], fields: Optional[List[str]] = None) -> List[Optional[Any]]:
        """Get multiple items by IDs with optional field filtering."""
        if not ids:
            return []

        await self._ensure_initialized()

        # Use pipeline for batch operations
        async with self._redis_client.pipeline() as pipe:
            for id in ids:
                pipe.get(self._get_key(id))
            results = await pipe.execute()

        # Deserialize results
        items = []
        for data in results:
            item = self._deserialize(data)
            if item and fields:
                # Filter fields if specified
                if isinstance(item, dict):
                    item = {k: v for k, v in item.items() if k in fields}
            items.append(item)

        return items

    async def upsert(self, data: Dict[str, Any]) -> None:
        """Insert or update multiple items."""
        if not data:
            return

        await self._ensure_initialized()

        # Use pipeline for batch operations
        async with self._redis_client.pipeline() as pipe:
            for id, value in data.items():
                key = self._get_key(id)
                serialized = self._serialize(value)

                # Get TTL for this namespace
                ttl = self._ttl_config.get(self.namespace, 0)

                if ttl > 0:
                    pipe.setex(key, ttl, serialized)
                else:
                    pipe.set(key, serialized)

            await pipe.execute()

        logger.debug(f"Upserted {len(data)} items to Redis namespace: {self.namespace}")

    async def filter_keys(self, data: List[str]) -> set[str]:
        """Filter keys that don't exist in storage."""
        if not data:
            return set()

        await self._ensure_initialized()

        # Use pipeline to check existence
        async with self._redis_client.pipeline() as pipe:
            for key in data:
                pipe.exists(self._get_key(key))
            results = await pipe.execute()

        # Return keys that don't exist (result is 0)
        return {key for key, exists in zip(data, results) if not exists}

    async def drop(self) -> None:
        """Clear all keys in namespace."""
        await self._ensure_initialized()

        pattern = f"{self._prefix}*"
        cursor = 0

        # Delete in batches to avoid blocking
        while True:
            cursor, keys = await self._redis_client.scan(
                cursor, match=pattern, count=1000
            )
            if keys:
                await self._redis_client.delete(*keys)
            if cursor == 0:
                break

        logger.info(f"Dropped all data in Redis namespace: {self.namespace}")

    async def index_start_callback(self) -> None:
        """Called when indexing starts."""
        await self._ensure_initialized()

        # Optional: Clear namespace if rebuilding
        if self.global_config.get("clear_on_start", False):
            await self.drop()

    async def index_done_callback(self) -> None:
        """Called when indexing completes."""
        if not self._initialized:
            return

        # Force persistence to disk
        try:
            await self._redis_client.bgsave()
            logger.debug(f"Redis data persisted for namespace: {self.namespace}")
        except RedisError as e:
            logger.warning(f"Could not force Redis persistence: {e}")

    async def query_done_callback(self) -> None:
        """Called after query completes."""
        # No specific action needed for Redis
        pass

    def __del__(self):
        """Cleanup Redis connection on deletion."""
        if self._initialized and self._redis_client:
            # Schedule cleanup in event loop if available
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._cleanup())
            except RuntimeError:
                # Event loop not available, skip cleanup
                pass

    async def _cleanup(self):
        """Async cleanup of Redis connections."""
        if self._redis_client:
            await self._redis_client.close()
        if self._connection_pool:
            await self._connection_pool.disconnect()