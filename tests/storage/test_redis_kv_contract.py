"""Contract-based tests for Redis KV storage."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from tests.storage.base import BaseKVStorageTestSuite, KVStorageContract


class TestRedisKVContract(BaseKVStorageTestSuite):
    """Redis KV storage contract tests with mocks."""

    @pytest_asyncio.fixture
    async def storage(self):
        """Provide mocked Redis KV storage instance."""
        config = {
            "redis_url": "redis://localhost:6379",
            "redis_max_connections": 10,
            "redis_connection_timeout": 5.0,
            "redis_socket_timeout": 5.0,
            "redis_health_check_interval": 30
        }

        # Patch at module level before import
        import sys
        mock_redis_module = MagicMock()
        sys.modules['redis.asyncio'] = mock_redis_module
        sys.modules['redis.backoff'] = MagicMock()
        sys.modules['redis.retry'] = MagicMock()
        sys.modules['redis.exceptions'] = MagicMock()

        with patch('nano_graphrag._storage.kv_redis.REDIS_AVAILABLE', True):

            # Mock Redis client
            mock_client = AsyncMock()
            mock_pool = MagicMock()

            # Setup mock Redis module
            mock_redis_module.ConnectionPool.from_url.return_value = mock_pool
            mock_redis_module.Redis.return_value = mock_client

            # Storage for mock data
            mock_data = {}

            # Mock basic operations
            mock_client.ping = AsyncMock(return_value=True)

            async def mock_get(key):
                return mock_data.get(key, None)
            mock_client.get = AsyncMock(side_effect=mock_get)

            async def mock_set(key, value):
                mock_data[key] = value
                return True
            mock_client.set = AsyncMock(side_effect=mock_set)

            async def mock_setex(key, ttl, value):
                mock_data[key] = value
                return True
            mock_client.setex = AsyncMock(side_effect=mock_setex)

            async def mock_exists(key):
                return 1 if key in mock_data else 0
            mock_client.exists = AsyncMock(side_effect=mock_exists)

            async def mock_delete(*keys):
                count = sum(1 for k in keys if mock_data.pop(k, None) is not None)
                return count
            mock_client.delete = AsyncMock(side_effect=mock_delete)

            async def mock_scan(cursor, match=None, count=None):
                prefix = match.replace('*', '') if match else ''
                keys = [k.encode() for k in list(mock_data.keys()) if not match or k.startswith(prefix)]
                # For drop operation, we need to clear the matching keys
                if match and keys:
                    for k in keys:
                        mock_data.pop(k.decode(), None)
                return (0, keys)
            mock_client.scan = AsyncMock(side_effect=mock_scan)

            async def mock_scan_iter(match=None, count=None):
                for k in mock_data.keys():
                    if not match or k.startswith(match.replace('*', '')):
                        yield k.encode()
            mock_client.scan_iter = mock_scan_iter

            mock_client.bgsave = AsyncMock(return_value=True)

            # Mock pipeline with proper command tracking
            pipeline_commands = []

            class MockPipeline:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return None

                def get(self, key):
                    pipeline_commands.append(('get', key))
                    return self

                def set(self, key, value):
                    pipeline_commands.append(('set', key, value))
                    mock_data[key] = value  # Store immediately
                    return self

                def setex(self, key, ttl, value):
                    pipeline_commands.append(('setex', key, ttl, value))
                    mock_data[key] = value  # Store immediately
                    return self

                def exists(self, key):
                    pipeline_commands.append(('exists', key))
                    return self

                async def execute(self):
                    results = []
                    for cmd in pipeline_commands:
                        if cmd[0] == 'get':
                            results.append(mock_data.get(cmd[1], None))
                        elif cmd[0] in ('set', 'setex'):
                            results.append(True)
                        elif cmd[0] == 'exists':
                            results.append(1 if cmd[1] in mock_data else 0)
                    pipeline_commands.clear()
                    return results

            mock_client.pipeline = MagicMock(return_value=MockPipeline())

            mock_client.close = AsyncMock()

            # Import after patching
            from nano_graphrag._storage.kv_redis import RedisKVStorage

            storage = RedisKVStorage(
                namespace="test",
                global_config=config
            )

            # Ensure initialization
            await storage._ensure_initialized()

            yield storage

    @pytest.fixture
    def contract(self):
        """Define Redis KV capabilities."""
        return KVStorageContract(
            supports_batch_ops=True,
            supports_persistence=True,
            supports_async=True,
            supports_namespace=True,
            max_key_length=None,  # Redis supports very long keys
            max_value_size=512 * 1024 * 1024  # 512MB limit
        )