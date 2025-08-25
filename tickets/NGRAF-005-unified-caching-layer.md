# NGRAF-005: Unified Caching Layer

## Summary
Create a single, pluggable caching abstraction to replace scattered caching logic across LLM calls, embeddings, and Redis.

## Problem
- Caching logic duplicated in each LLM provider function
- Redis caching in `app.py` separate from LLM response cache
- Hash computation repeated (`compute_args_hash`) in multiple places
- No consistent cache invalidation strategy

## Technical Solution

```python
# nano_graphrag/cache/base.py
from typing import Optional, Any, Protocol
from abc import abstractmethod

class CacheBackend(Protocol):
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Retrieve value from cache"""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store value in cache with optional TTL"""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove value from cache"""
        pass

# nano_graphrag/cache/implementations.py
class MemoryCache(CacheBackend):
    def __init__(self):
        self._cache: Dict[str, Any] = {}
    
    async def get(self, key: str) -> Optional[Any]:
        return self._cache.get(key)

class RedisCache(CacheBackend):
    def __init__(self, url: str = "redis://localhost:6379"):
        self.client = redis.from_url(url)
    
    async def get(self, key: str) -> Optional[Any]:
        value = await self.client.get(key)
        return json.loads(value) if value else None

# nano_graphrag/cache/decorator.py
def cached(cache: CacheBackend, ttl: Optional[int] = None):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Generate cache key from function and arguments
            cache_key = f"{func.__name__}:{hash(args)}:{hash(frozenset(kwargs.items()))}"
            
            # Try cache first
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Compute and cache result
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result, ttl)
            return result
        return wrapper
    return decorator
```

## Code Changes

### New Files
- `nano_graphrag/cache/base.py` - Cache protocol definition
- `nano_graphrag/cache/implementations.py` - Memory, Redis, JSON cache backends
- `nano_graphrag/cache/decorator.py` - Caching decorator for functions

### Modified Files
- `nano_graphrag/_llm.py` - Replace manual caching with decorator:
  ```python
  # Before
  if hashing_kv is not None:
      args_hash = compute_args_hash(model, messages)
      if_cache_return = await hashing_kv.get_by_id(args_hash)
      if if_cache_return is not None:
          return if_cache_return["return"]
  
  # After
  @cached(cache=self.cache, ttl=3600)
  async def complete(self, prompt: str, **kwargs) -> str:
      # Direct implementation without caching logic
      response = await self.client.chat.completions.create(...)
      return response.choices[0].message.content
  ```

- `app.py` - Use unified cache:
  ```python
  # Before: Separate Redis logic
  cached_response = await redis_client.get(cache_key)
  
  # After: Unified cache
  cache = RedisCache() if REDIS_ENABLED else MemoryCache()
  graphrag = NanoGraphRAG(config, cache=cache)
  ```

## Definition of Done

### Unit Tests Required
```python
# tests/cache/test_cache.py
import pytest
from unittest.mock import AsyncMock, Mock
from nano_graphrag.cache import MemoryCache, RedisCache, cached

class TestCaching:
    @pytest.mark.asyncio
    async def test_memory_cache_basic_operations(self):
        """Verify memory cache get/set/delete"""
        cache = MemoryCache()
        
        await cache.set("key", "value")
        assert await cache.get("key") == "value"
        
        await cache.delete("key")
        assert await cache.get("key") is None
    
    @pytest.mark.asyncio
    async def test_redis_cache_with_ttl(self):
        """Verify Redis cache respects TTL"""
        with patch('redis.asyncio.from_url') as mock_redis:
            mock_client = AsyncMock()
            mock_redis.return_value = mock_client
            
            cache = RedisCache()
            await cache.set("key", "value", ttl=60)
            
            mock_client.set.assert_called_with("key", '"value"', ex=60)
    
    @pytest.mark.asyncio
    async def test_cache_decorator(self):
        """Verify decorator caches function results"""
        cache = MemoryCache()
        call_count = 0
        
        @cached(cache=cache)
        async def expensive_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2
        
        result1 = await expensive_function(5)
        result2 = await expensive_function(5)
        
        assert result1 == 10
        assert result2 == 10
        assert call_count == 1  # Function called only once
    
    @pytest.mark.asyncio
    async def test_cache_key_generation(self):
        """Verify cache keys are unique per function/args"""
        cache = MemoryCache()
        
        @cached(cache=cache)
        async def func1(x): return x
        
        @cached(cache=cache)
        async def func2(x): return x * 2
        
        await func1(5)
        await func2(5)
        
        # Different functions with same args should have different keys
        assert len(cache._cache) == 2
    
    @pytest.mark.asyncio
    async def test_cache_invalidation(self):
        """Verify cache can be invalidated"""
        cache = MemoryCache()
        
        @cached(cache=cache)
        async def get_data():
            return "original"
        
        result1 = await get_data()
        await cache.delete_pattern("get_data:*")
        
        # After invalidation, should recompute
        get_data.__wrapped__ = AsyncMock(return_value="updated")
        result2 = await get_data()
        
        assert result1 == "original"
        assert result2 == "updated"
```

### Additional Test Coverage
- Test cache backends are interchangeable
- Test concurrent cache access
- Test cache serialization of complex objects
- Test cache performance improvements

## Feature Branch
`feature/ngraf-005-unified-caching`

## Pull Request Must Include
- Single cache abstraction for all caching needs
- Pluggable cache backends (Memory, Redis, JSON)
- Cache decorator for clean function decoration
- Proper typing for cache operations
- All tests passing with >90% coverage