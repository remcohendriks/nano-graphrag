# NGRAF-016: Redis KV Backend Implementation

## Epic
Storage Layer Enhancement

## Priority
HIGH

## Story Points
8

## Component
Storage/KV Backend

## Reporter
System Architect

## Assignee
Claude Code

## Sprint
Storage Optimization Q1 2025

## Labels
`storage`, `redis`, `kv-backend`, `performance`, `production`, `api-service`

## Summary
Implement Redis as a production-ready Key-Value storage backend to replace JSON file storage for scalable API deployments. This enables shared state across multiple workers, efficient caching, and horizontal scaling for FastAPI-based services.

## Background

### Current State
The current KV backend uses JSON file storage (`JsonKVStorage`) which has critical limitations:
- **In-Memory Loading**: Entire JSON loaded into RAM on startup
- **No Concurrent Access**: Each worker has separate memory space
- **No ACID Guarantees**: Risk of data loss on crash
- **Poor Performance**: Large documents cause slow JSON parsing
- **Cache Duplication**: Each API worker maintains separate LLM cache (expensive!)

### Business Impact
- **Cost**: Duplicate LLM calls across workers due to cache fragmentation
- **Scalability**: Cannot horizontally scale API workers effectively
- **Performance**: Slow response times with large document sets
- **Reliability**: Data loss risk in production environments

## User Story
**AS A** nano-graphrag API service operator  
**I WANT** Redis-based KV storage  
**SO THAT** I can horizontally scale my API service with shared state and efficient caching

## Acceptance Criteria

### Functional Requirements
1. ✅ Implement `RedisKVStorage` class inheriting from `BaseKVStorage`
2. ✅ Support all four KV namespaces:
   - `full_docs` - Document storage
   - `text_chunks` - Chunk storage  
   - `community_reports` - Community summaries
   - `llm_response_cache` - LLM response caching
3. ✅ Maintain backward compatibility with existing JSON backend
4. ✅ Support both sync and async Redis operations
5. ✅ Implement configurable TTL per namespace
6. ✅ Handle Redis connection pooling efficiently
7. ✅ Support Redis Cluster for production scaling
8. ✅ Implement proper error handling and fallback

### Non-Functional Requirements
1. ✅ Sub-millisecond read latency for cached items
2. ✅ Support for 10,000+ concurrent connections
3. ✅ Memory-efficient storage using compression where appropriate
4. ✅ Zero data loss during Redis restarts (persistence enabled)
5. ✅ Monitoring-ready with metrics exposure

### Configuration Requirements
1. ✅ Environment variable support:
   ```bash
   STORAGE_KV_BACKEND=redis
   REDIS_URL=redis://localhost:6379
   REDIS_PASSWORD=optional_password
   REDIS_MAX_CONNECTIONS=50
   REDIS_CONNECTION_TIMEOUT=5.0
   REDIS_SOCKET_TIMEOUT=5.0
   REDIS_RETRY_ON_TIMEOUT=true
   REDIS_HEALTH_CHECK_INTERVAL=30
   ```

2. ✅ Per-namespace TTL configuration:
   ```bash
   REDIS_TTL_LLM_CACHE=43200  # 12 hours
   REDIS_TTL_COMMUNITY_REPORTS=86400  # 24 hours
   REDIS_TTL_CHUNKS=0  # No expiry
   REDIS_TTL_DOCS=0  # No expiry
   ```

## Technical Design

### Architecture
```
┌─────────────────────────────────────────┐
│         FastAPI Application             │
│  ┌──────────────────────────────────┐  │
│  │     Worker 1    │    Worker 2     │  │
│  │   GraphRAG      │    GraphRAG     │  │
│  └────────┬────────┴────────┬────────┘  │
│           │                 │           │
│           └────────┬────────┘           │
│                    ▼                    │
│         ┌──────────────────┐           │
│         │ RedisKVStorage   │           │
│         └────────┬─────────┘           │
└──────────────────┼─────────────────────┘
                   │
                   ▼
         ┌──────────────────┐
         │   Redis Server   │
         │  - Persistence   │
         │  - Replication   │
         │  - Clustering    │
         └──────────────────┘
```

### Implementation Structure
```python
nano_graphrag/
├── _storage/
│   ├── __init__.py
│   ├── kv_json.py          # Existing
│   └── kv_redis.py         # New implementation
├── config.py               # Add Redis configuration
└── _utils.py               # Add Redis connection utilities
```

### Core Implementation

```python
# nano_graphrag/_storage/kv_redis.py
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import json
import pickle
import asyncio
import redis.asyncio as aioredis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
from redis.exceptions import RedisError, ConnectionError

from ..base import BaseKVStorage
from .._utils import logger

@dataclass
class RedisKVStorage(BaseKVStorage):
    """Redis-based Key-Value storage with production features."""
    
    _redis_client: Optional[aioredis.Redis] = field(init=False, default=None)
    _connection_pool: Optional[aioredis.ConnectionPool] = field(init=False, default=None)
    _ttl_config: Dict[str, int] = field(init=False, default_factory=dict)
    
    async def __post_init__(self):
        """Initialize Redis connection with production settings."""
        # Get Redis configuration
        redis_url = self.global_config.get("redis_url", "redis://localhost:6379")
        redis_password = self.global_config.get("redis_password", None)
        max_connections = self.global_config.get("redis_max_connections", 50)
        socket_timeout = self.global_config.get("redis_socket_timeout", 5.0)
        
        # Configure retry policy
        retry = Retry(
            ExponentialBackoff(),
            retries=3,
            supported_errors=(ConnectionError, TimeoutError)
        )
        
        # Create connection pool
        self._connection_pool = aioredis.ConnectionPool.from_url(
            redis_url,
            password=redis_password,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            decode_responses=False,  # Handle bytes for flexibility
            retry=retry,
            health_check_interval=30
        )
        
        # Create Redis client
        self._redis_client = aioredis.Redis(
            connection_pool=self._connection_pool,
            auto_close_connection_pool=False
        )
        
        # Configure TTL per namespace
        self._setup_ttl_config()
        
        # Create namespace prefix
        self._prefix = f"nano_graphrag:{self.namespace}:"
        
        # Log initialization
        logger.info(f"Initialized Redis KV storage for namespace: {self.namespace}")
        
        # Verify connection
        await self._verify_connection()
    
    def _setup_ttl_config(self):
        """Configure TTL settings per namespace."""
        import os
        
        # Default TTLs (in seconds)
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
    
    async def _verify_connection(self):
        """Verify Redis connection is working."""
        try:
            await self._redis_client.ping()
            logger.debug(f"Redis connection verified for namespace: {self.namespace}")
        except RedisError as e:
            logger.error(f"Redis connection failed: {e}")
            raise
    
    def _get_key(self, id: str) -> str:
        """Generate Redis key with namespace prefix."""
        return f"{self._prefix}{id}"
    
    def _serialize(self, data: Any) -> bytes:
        """Serialize data for Redis storage."""
        if isinstance(data, (dict, list)):
            return json.dumps(data).encode('utf-8')
        return pickle.dumps(data)
    
    def _deserialize(self, data: bytes) -> Any:
        """Deserialize data from Redis."""
        if data is None:
            return None
        try:
            # Try JSON first
            return json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Fall back to pickle
            return pickle.loads(data)
    
    async def all_keys(self) -> List[str]:
        """Get all keys in namespace."""
        pattern = f"{self._prefix}*"
        keys = []
        async for key in self._redis_client.scan_iter(match=pattern, count=1000):
            # Remove prefix to get original key
            keys.append(key.decode('utf-8').replace(self._prefix, '', 1))
        return keys
    
    async def get_by_id(self, id: str) -> Optional[Any]:
        """Get single item by ID."""
        try:
            data = await self._redis_client.get(self._get_key(id))
            return self._deserialize(data)
        except RedisError as e:
            logger.error(f"Redis get error for {id}: {e}")
            return None
    
    async def get_by_ids(self, ids: List[str], fields: Optional[List[str]] = None) -> List[Optional[Any]]:
        """Get multiple items by IDs with optional field filtering."""
        if not ids:
            return []
        
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
        
        # Use pipeline to check existence
        async with self._redis_client.pipeline() as pipe:
            for key in data:
                pipe.exists(self._get_key(key))
            results = await pipe.execute()
        
        # Return keys that don't exist (result is 0)
        return {key for key, exists in zip(data, results) if not exists}
    
    async def delete_by_ids(self, ids: List[str]) -> None:
        """Delete multiple items by IDs."""
        if not ids:
            return
        
        keys = [self._get_key(id) for id in ids]
        deleted = await self._redis_client.delete(*keys)
        logger.debug(f"Deleted {deleted} items from Redis namespace: {self.namespace}")
    
    async def index_start_callback(self) -> None:
        """Called when indexing starts."""
        # Verify connection is still alive
        await self._verify_connection()
        
        # Optional: Clear namespace if rebuilding
        if self.global_config.get("clear_on_start", False):
            await self._clear_namespace()
    
    async def index_done_callback(self) -> None:
        """Called when indexing completes."""
        # Force persistence to disk
        try:
            await self._redis_client.bgsave()
            logger.info(f"Redis data persisted for namespace: {self.namespace}")
        except RedisError as e:
            logger.warning(f"Could not force Redis persistence: {e}")
    
    async def _clear_namespace(self) -> None:
        """Clear all keys in namespace."""
        pattern = f"{self._prefix}*"
        cursor = 0
        while True:
            cursor, keys = await self._redis_client.scan(
                cursor, match=pattern, count=1000
            )
            if keys:
                await self._redis_client.delete(*keys)
            if cursor == 0:
                break
        logger.info(f"Cleared Redis namespace: {self.namespace}")
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis_client:
            await self._redis_client.close()
        if self._connection_pool:
            await self._connection_pool.disconnect()
        logger.info(f"Closed Redis connection for namespace: {self.namespace}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        pattern = f"{self._prefix}*"
        
        # Count keys
        key_count = 0
        memory_usage = 0
        
        async for key in self._redis_client.scan_iter(match=pattern, count=1000):
            key_count += 1
            # Sample memory usage (expensive for large datasets)
            if key_count <= 100:
                usage = await self._redis_client.memory_usage(key)
                memory_usage += usage if usage else 0
        
        # Get Redis info
        info = await self._redis_client.info("memory")
        
        return {
            "namespace": self.namespace,
            "key_count": key_count,
            "sample_memory_usage": memory_usage,
            "total_redis_memory": info.get("used_memory_human", "unknown"),
            "ttl_seconds": self._ttl_config.get(self.namespace, 0)
        }
```

### Configuration Updates

```python
# nano_graphrag/config.py additions
@dataclass
class StorageConfig:
    # ... existing fields ...
    
    # Redis configuration
    redis_url: str = "redis://localhost:6379"
    redis_password: Optional[str] = None
    redis_max_connections: int = 50
    redis_connection_timeout: float = 5.0
    redis_socket_timeout: float = 5.0
    redis_retry_on_timeout: bool = True
    redis_health_check_interval: int = 30
    
    @classmethod
    def from_env(cls):
        # ... existing code ...
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_password = os.getenv("REDIS_PASSWORD")
        # ... etc
```

### Factory Registration

```python
# nano_graphrag/_storage/__init__.py
def _register_backends():
    # ... existing registrations ...
    
    # Register Redis backend
    StorageFactory.register_kv_backend(
        "redis",
        lambda **kwargs: RedisKVStorage(**kwargs)
    )
```

## Testing Strategy

### Unit Tests
```python
# tests/storage/test_kv_redis.py
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import redis.asyncio as aioredis

@pytest.mark.asyncio
async def test_redis_initialization():
    """Test Redis storage initialization."""
    config = {
        "redis_url": "redis://localhost:6379",
        "redis_max_connections": 10
    }
    
    with patch('nano_graphrag._storage.kv_redis.aioredis.Redis') as mock_redis:
        storage = RedisKVStorage(namespace="test", global_config=config)
        await storage.__post_init__()
        assert storage._prefix == "nano_graphrag:test:"

@pytest.mark.asyncio
async def test_redis_upsert_with_ttl():
    """Test upsert with TTL configuration."""
    # Test implementation

@pytest.mark.asyncio
async def test_redis_batch_operations():
    """Test batch get/set operations."""
    # Test implementation

@pytest.mark.asyncio
async def test_redis_connection_failure():
    """Test graceful handling of connection failures."""
    # Test implementation
```

### Integration Tests
```python
# tests/integration/test_redis_integration.py
@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_with_graphrag():
    """Test Redis backend with full GraphRAG flow."""
    config = GraphRAGConfig(
        storage={"kv_backend": "redis"}
    )
    
    rag = GraphRAG(config)
    await rag.ainsert("Test document")
    
    # Verify data in Redis
    # Test query operations
```

### Health Check Configuration
```bash
# tests/health/config_redis.env
STORAGE_KV_BACKEND=redis
STORAGE_GRAPH_BACKEND=neo4j
STORAGE_VECTOR_BACKEND=qdrant

REDIS_URL=redis://localhost:6379
REDIS_MAX_CONNECTIONS=50
REDIS_TTL_LLM_CACHE=3600
REDIS_TTL_COMMUNITY_REPORTS=7200
```

## Deployment Guide

### Docker Compose
```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

  api:
    build: .
    environment:
      STORAGE_KV_BACKEND: redis
      REDIS_URL: redis://redis:6379
    depends_on:
      redis:
        condition: service_healthy

volumes:
  redis_data:
```

### Production Considerations

1. **High Availability**
   - Redis Sentinel for automatic failover
   - Redis Cluster for sharding
   - Read replicas for scaling

2. **Persistence**
   - AOF (Append Only File) for durability
   - RDB snapshots for backups
   - Both enabled for maximum safety

3. **Memory Management**
   - Set maxmemory policy (allkeys-lru recommended)
   - Monitor memory usage
   - Use compression for large values

4. **Security**
   - Enable password authentication
   - Use TLS for encrypted connections
   - Network isolation with VPC

## Monitoring & Metrics

### Key Metrics to Track
- Cache hit/miss ratio
- Memory usage per namespace
- Operation latency (p50, p95, p99)
- Connection pool utilization
- Eviction rate

### Prometheus Metrics
```python
redis_operations_total{namespace="llm_response_cache", operation="get"}
redis_operation_duration_seconds{namespace="text_chunks", operation="upsert"}
redis_memory_usage_bytes{namespace="community_reports"}
redis_connection_pool_size{status="active"}
```

## Migration Strategy

### From JSON to Redis
1. Implement RedisKVStorage
2. Add feature flag: `KV_BACKEND_MIGRATION=true`
3. Dual-write period (write to both JSON and Redis)
4. Verify data consistency
5. Switch reads to Redis
6. Remove JSON backend usage

### Rollback Plan
1. Keep JSON files as backup
2. Feature flag to switch back
3. Monitor error rates
4. One-command rollback: `STORAGE_KV_BACKEND=json`

## Definition of Done

### Code Complete
- [ ] RedisKVStorage implemented with all BaseKVStorage methods
- [ ] Async operations fully supported
- [ ] TTL configuration per namespace
- [ ] Connection pooling and retry logic
- [ ] Error handling and logging

### Testing
- [ ] Unit tests with >90% coverage
- [ ] Integration tests with GraphRAG
- [ ] Load tests showing <1ms latency
- [ ] Failure scenario tests
- [ ] Health check passing

### Documentation
- [ ] API documentation in docstrings
- [ ] Configuration guide in README
- [ ] Migration guide created
- [ ] Monitoring guide provided

### Production Ready
- [ ] Docker compose configuration
- [ ] Kubernetes manifests (optional)
- [ ] Prometheus metrics exposed
- [ ] Performance benchmarks documented
- [ ] Security review completed

## Performance Targets

| Metric | Target | Rationale |
|--------|--------|-----------|
| Read Latency (p50) | <1ms | Sub-millisecond for cache hits |
| Read Latency (p99) | <10ms | Even tail latency should be fast |
| Write Latency (p50) | <2ms | Fast inserts for real-time |
| Throughput | >10,000 ops/sec | Handle high concurrent load |
| Memory Overhead | <20% | Efficient serialization |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Redis downtime | Service unavailable | Implement fallback to JSON |
| Memory exhaustion | Data loss | Set maxmemory with LRU eviction |
| Network latency | Slow responses | Connection pooling, local Redis |
| Data corruption | Inconsistent state | Atomic operations, transactions |

## Dependencies

### Required Packages
```python
# requirements.txt additions
redis[hiredis]>=5.0.0  # Async Redis client with C parser
```

### Optional Packages
```python
# For monitoring
prometheus-client>=0.19.0
# For compression
lz4>=4.3.0
```

## Success Metrics

1. **Performance**: 10x faster cache lookups vs JSON
2. **Cost**: 50% reduction in LLM API calls due to shared cache
3. **Scalability**: Support 10+ API workers with shared state
4. **Reliability**: Zero data loss during deployments

## Follow-up Tickets

1. **NGRAF-017**: Redis Cluster support for sharding
2. **NGRAF-018**: Redis Streams for event sourcing
3. **NGRAF-019**: Cache warming strategies
4. **NGRAF-020**: Redis-backed rate limiting

## References

- [Redis Best Practices](https://redis.io/docs/manual/patterns/)
- [Redis Persistence](https://redis.io/docs/manual/persistence/)
- [Async Redis Python](https://redis-py.readthedocs.io/en/stable/asyncio.html)
- [Production Redis Checklist](https://redis.io/docs/manual/admin/)

---

**Ticket Status**: READY FOR IMPLEMENTATION  
**Estimated Completion**: 2 sprints  
**Review Required**: Architecture, Security, Performance