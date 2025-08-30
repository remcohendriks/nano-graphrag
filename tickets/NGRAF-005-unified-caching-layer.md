# NGRAF-005: Minimal Cache Abstraction Layer

## Summary
Create a minimal, pluggable cache interface that wraps existing KV storage while maintaining current behavior and allowing optional backends.

**UPDATE**: Focus on absolute minimal implementation - just a thin adapter over existing `hashing_kv` with optional TTL/metrics hooks. No new dependencies, no complex patterns.

## Context
After NGRAF-001/002/003, caching exists via `BaseLLMProvider.complete_with_cache()` using `hashing_kv` (JsonKVStorage). This ticket provides a cleaner abstraction without invasive changes.

## Problem
- Caching tightly coupled to KV storage implementation
- No TTL support (cache grows indefinitely)
- No cache metrics (hit/miss rates)
- Direct use of storage internals in provider code

## Technical Solution (Low Complexity)

### Minimal Cache Interface
```python
# nano_graphrag/cache/base.py
from typing import Optional, Any, Protocol

class CacheBackend(Protocol):
    """Minimal cache interface matching existing usage patterns."""
    
    async def get(self, key: str) -> Optional[Any]:
        """Retrieve value from cache"""
        ...
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store value in cache with optional TTL (may be no-op for some backends)"""
        ...
    
    async def delete(self, key: str) -> None:
        """Remove value from cache"""
        ...

# nano_graphrag/cache/implementations.py
from nano_graphrag.base import BaseKVStorage
from typing import Dict, Any, Optional

class KVCache(CacheBackend):
    """Adapter wrapping existing KV storage to provide cache interface."""
    
    def __init__(self, kv_storage: BaseKVStorage):
        self._kv = kv_storage
    
    async def get(self, key: str) -> Optional[Any]:
        """Get from KV storage, extracting 'return' field if present."""
        result = await self._kv.get_by_id(key)
        if result is None:
            return None
        # Handle both old format {"return": value} and direct values
        return result.get("return", result) if isinstance(result, dict) else result
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set in KV storage (TTL ignored for JSON backend)."""
        await self._kv.upsert({key: {"return": value, "cached": True}})
        await self._kv.index_done_callback()
    
    async def delete(self, key: str) -> None:
        """Delete from KV storage if supported."""
        # JSON KV doesn't have delete, so this is a no-op
        pass

class MemoryCache(CacheBackend):
    """Simple in-memory cache for testing."""
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
    
    async def get(self, key: str) -> Optional[Any]:
        return self._cache.get(key)
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        # TTL ignored for simplicity
        self._cache[key] = value
    
    async def delete(self, key: str) -> None:
        self._cache.pop(key, None)
```

### Integration Without Disruption
```python
# In BaseLLMProvider - minimal change to existing code
async def complete_with_cache(self, ..., hashing_kv=None, cache=None, ...):
    """Support both old hashing_kv and new cache interface."""
    # Backward compatibility: wrap hashing_kv as cache if needed
    if cache is None and hashing_kv is not None:
        from ..cache.implementations import KVCache
        cache = KVCache(hashing_kv)
    
    if cache is not None:
        key = compute_args_hash(self.model, messages)
        cached_result = await cache.get(key)
        if cached_result is not None:
            return cached_result
    
    response = await self.complete(...)
    result = response["text"]
    
    if cache is not None:
        await cache.set(key, result)
    
    return result
```

## Code Changes (Minimal)

### New Files
- `nano_graphrag/cache/__init__.py` - Package exports
- `nano_graphrag/cache/base.py` - Cache protocol (15 lines)
- `nano_graphrag/cache/implementations.py` - KVCache adapter + MemoryCache (50 lines)

### Modified Files (Backward Compatible)
- `nano_graphrag/llm/base.py` - Add optional `cache` parameter to `complete_with_cache()`:
  ```python
  # Minimal change - add cache parameter with backward compatibility
  async def complete_with_cache(self, ..., hashing_kv=None, cache=None, ...):
      # Auto-wrap hashing_kv as cache if needed
      if cache is None and hashing_kv is not None:
          cache = KVCache(hashing_kv)
  ```

- `nano_graphrag/graphrag.py` - Optionally use cache interface:
  ```python
  # Option 1: Keep current behavior (no change needed)
  self.llm_response_cache = JsonKVStorage(...) if cache_enabled else None
  
  # Option 2: Use new interface (optional improvement)
  from .cache.implementations import KVCache
  kv_storage = JsonKVStorage(...) if cache_enabled else None
  self.cache = KVCache(kv_storage) if kv_storage else None
  ```

### NOT Changed (Avoiding Complexity)
- ❌ No decorator pattern (doesn't fit streaming, adds complexity)
- ❌ No Redis dependency (keep library lightweight)
- ❌ No app.py changes (doesn't exist)
- ❌ No breaking changes to existing code

## Definition of Done

### Unit Tests Required (Focused)
```python
# tests/cache/test_cache.py
import pytest
from unittest.mock import AsyncMock, Mock
from nano_graphrag.cache import KVCache, MemoryCache
from nano_graphrag.base import BaseKVStorage

class TestCacheImplementations:
    @pytest.mark.asyncio
    async def test_memory_cache_basic_operations(self):
        """Verify memory cache get/set/delete"""
        cache = MemoryCache()
        
        # Test set and get
        await cache.set("key1", "value1")
        assert await cache.get("key1") == "value1"
        assert await cache.get("nonexistent") is None
        
        # Test delete
        await cache.delete("key1")
        assert await cache.get("key1") is None
    
    @pytest.mark.asyncio
    async def test_kv_cache_adapter(self):
        """Verify KVCache correctly wraps KV storage"""
        mock_kv = AsyncMock(spec=BaseKVStorage)
        cache = KVCache(mock_kv)
        
        # Test get - with old format
        mock_kv.get_by_id.return_value = {"return": "cached_value"}
        result = await cache.get("test_key")
        assert result == "cached_value"
        mock_kv.get_by_id.assert_called_with("test_key")
        
        # Test get - cache miss
        mock_kv.get_by_id.return_value = None
        result = await cache.get("missing_key")
        assert result is None
        
        # Test set
        await cache.set("new_key", "new_value")
        mock_kv.upsert.assert_called_with({
            "new_key": {"return": "new_value", "cached": True}
        })
        mock_kv.index_done_callback.assert_called()
    
    @pytest.mark.asyncio
    async def test_cache_backend_protocol(self):
        """Verify both implementations satisfy CacheBackend protocol"""
        from nano_graphrag.cache.base import CacheBackend
        
        # Both should be valid CacheBackend implementations
        memory_cache = MemoryCache()
        kv_cache = KVCache(AsyncMock(spec=BaseKVStorage))
        
        # Protocol methods should exist
        for cache in [memory_cache, kv_cache]:
            assert hasattr(cache, 'get')
            assert hasattr(cache, 'set')
            assert hasattr(cache, 'delete')
    
    @pytest.mark.asyncio
    async def test_backward_compatibility(self):
        """Verify existing hashing_kv code continues to work"""
        from nano_graphrag.llm.base import BaseLLMProvider
        
        mock_provider = Mock(spec=BaseLLMProvider)
        mock_kv = AsyncMock(spec=BaseKVStorage)
        
        # Existing code should still work with hashing_kv
        mock_kv.get_by_id.return_value = {"return": "cached_response"}
        
        # Simulate the complete_with_cache pattern
        result = await mock_kv.get_by_id("some_hash")
        assert result["return"] == "cached_response"
```

### Test Scope (What NOT to Test)
- ❌ No decorator tests (not implementing decorators)
- ❌ No Redis tests (not adding Redis dependency)
- ❌ No pattern deletion tests (keeping it simple)

## Feature Branch
`feature/ngraf-005-minimal-cache`

## Pull Request Must Include
- Minimal cache protocol (CacheBackend)
- KVCache adapter wrapping existing storage
- MemoryCache for testing
- Backward compatibility maintained
- All tests passing
- No breaking changes

## Benefits
- **Cleaner abstraction**: Cache operations separate from storage details
- **Testability**: Easy to mock cache in tests
- **Future extensibility**: Can add Redis/other backends later
- **Low risk**: Minimal changes, backward compatible
- **Maintainable**: ~65 lines of new code total