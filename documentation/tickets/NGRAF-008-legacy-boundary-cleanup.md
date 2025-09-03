# NGRAF-008: Legacy Boundary Cleanup

## Summary
Clean up legacy exports and global variables in `_llm.py` by adding deprecation warnings and creating a clear migration path.

## Context
After NGRAF-001 (LLM provider abstraction), the old function-based LLM interface was preserved in `_llm.py` for backward compatibility. This creates confusion about which patterns are recommended vs deprecated.

## Problem
- Mixed old function-based and new provider-based patterns
- Global client instances that are never cleaned up
- No clear deprecation timeline
- Confusing for new contributors which approach to use
- Legacy functions don't benefit from provider improvements

## Technical Solution

### 1. Add Deprecation Warnings to Legacy Functions
```python
# nano_graphrag/_llm.py

import warnings
from functools import wraps
from typing import Callable

def deprecated_llm_function(replacement: str) -> Callable:
    """Decorator to mark LLM functions as deprecated."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            warnings.warn(
                f"{func.__name__} is deprecated and will be removed in v0.2.0. "
                f"Use {replacement} instead.",
                DeprecationWarning,
                stacklevel=2
            )
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Apply to legacy functions
@deprecated_llm_function("OpenAIProvider.complete()")
async def gpt_4o_complete(*args, **kwargs):
    """
    DEPRECATED: Use OpenAIProvider.complete() instead.
    This function will be removed in v0.2.0.
    """
    from .llm.providers import gpt_4o_complete as _gpt_4o_complete
    return await _gpt_4o_complete(*args, **kwargs)

@deprecated_llm_function("OpenAIProvider.complete()")
async def gpt_4o_mini_complete(*args, **kwargs):
    """
    DEPRECATED: Use OpenAIProvider.complete() instead.
    This function will be removed in v0.2.0.
    """
    from .llm.providers import gpt_4o_mini_complete as _gpt_4o_mini_complete
    return await _gpt_4o_mini_complete(*args, **kwargs)

@deprecated_llm_function("OpenAIEmbedding.embed()")
async def openai_embedding(*args, **kwargs):
    """
    DEPRECATED: Use OpenAIEmbedding.embed() instead.
    This function will be removed in v0.2.0.
    """
    from .llm.providers import openai_embedding as _openai_embedding
    return await _openai_embedding(*args, **kwargs)
```

### 2. Clean Up Global Client Instances
```python
# nano_graphrag/_llm.py

# Mark globals as deprecated
def get_openai_async_client_instance():
    """
    DEPRECATED: Use OpenAIProvider instead.
    This function will be removed in v0.2.0.
    
    Migration example:
        # Old way
        client = get_openai_async_client_instance()
        
        # New way
        from nano_graphrag.llm.openai import OpenAIProvider
        provider = OpenAIProvider(model="gpt-4o")
    """
    warnings.warn(
        "get_openai_async_client_instance() is deprecated. "
        "Use OpenAIProvider directly.",
        DeprecationWarning,
        stacklevel=2
    )
    
    from openai import AsyncOpenAI
    global global_openai_async_client
    if global_openai_async_client is None:
        global_openai_async_client = AsyncOpenAI()
    return global_openai_async_client
```

### 3. Create Migration Guide
```python
# nano_graphrag/_llm.py

"""
Migration Guide for Legacy LLM Functions
========================================

The function-based LLM interface is deprecated in favor of the provider-based interface.

Old way (deprecated):
    from nano_graphrag._llm import gpt_4o_complete, openai_embedding
    
    response = await gpt_4o_complete(
        prompt="Hello",
        system_prompt="You are helpful"
    )
    
    embeddings = await openai_embedding(["text1", "text2"])

New way (recommended):
    from nano_graphrag.llm.openai import OpenAIProvider, OpenAIEmbedding
    
    # Create provider instances
    llm = OpenAIProvider(model="gpt-4o")
    embedder = OpenAIEmbedding()
    
    # Use provider methods
    response = await llm.complete(
        prompt="Hello",
        system_prompt="You are helpful"
    )
    
    embeddings = await embedder.embed(["text1", "text2"])

Benefits of the new approach:
- Type safety with provider classes
- Consistent error handling
- Better configuration management
- Connection pooling and retry logic
- Easier testing with mock providers

Deprecation Timeline:
- v0.1.x: Deprecation warnings added (current)
- v0.2.0: Legacy functions removed
- Migration period: 3-6 months
"""
```

### 4. Create Legacy Compatibility Module
```python
# nano_graphrag/llm/legacy.py

"""
Legacy LLM function compatibility layer.
This module provides backward compatibility for the old function-based interface.
All functions here are deprecated and will be removed in v0.2.0.
"""

import warnings
from typing import List, Optional, Dict, Any
from ..llm.openai import OpenAIProvider, OpenAIEmbedding
from ..llm.azure import AzureOpenAIProvider, AzureOpenAIEmbedding
from ..llm.bedrock import BedrockProvider, BedrockEmbedding

# Show module-level deprecation warning
warnings.warn(
    "The nano_graphrag.llm.legacy module is deprecated. "
    "Please migrate to the provider-based interface.",
    DeprecationWarning,
    stacklevel=2
)

# Factory functions for backward compatibility
def create_openai_complete_function(model: str = "gpt-4o"):
    """Create a legacy-compatible completion function."""
    provider = OpenAIProvider(model=model)
    
    async def complete_func(prompt: str, system_prompt: Optional[str] = None, **kwargs):
        response = await provider.complete(prompt, system_prompt, **kwargs)
        return response["text"]
    
    return complete_func

def create_openai_embedding_function():
    """Create a legacy-compatible embedding function."""
    embedder = OpenAIEmbedding()
    
    async def embedding_func(texts: List[str], **kwargs):
        response = await embedder.embed(texts, **kwargs)
        return response["embeddings"]
    
    return embedding_func
```

### 5. Update __init__.py Exports
```python
# nano_graphrag/llm/__init__.py

# New provider-based exports (recommended)
from .base import (
    BaseLLMProvider,
    BaseEmbeddingProvider,
    CompletionParams,
    CompletionResponse,
    EmbeddingResponse,
    LLMError,
)
from .openai import OpenAIProvider, OpenAIEmbedding
from .azure import AzureOpenAIProvider, AzureOpenAIEmbedding
from .bedrock import BedrockProvider, BedrockEmbedding

# Legacy exports (deprecated, will be removed in v0.2.0)
import warnings

def __getattr__(name):
    """Lazy load deprecated functions with warnings."""
    deprecated_functions = {
        'gpt_4o_complete': 'OpenAIProvider',
        'gpt_4o_mini_complete': 'OpenAIProvider', 
        'openai_embedding': 'OpenAIEmbedding',
        'azure_gpt_4o_complete': 'AzureOpenAIProvider',
        'azure_gpt_4o_mini_complete': 'AzureOpenAIProvider',
        'azure_openai_embedding': 'AzureOpenAIEmbedding',
    }
    
    if name in deprecated_functions:
        warnings.warn(
            f"Importing {name} from nano_graphrag.llm is deprecated. "
            f"Use {deprecated_functions[name]} instead.",
            DeprecationWarning,
            stacklevel=2
        )
        from .legacy import name as legacy_func
        return legacy_func
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

## Code Changes

### Files to Modify
- `nano_graphrag/_llm.py`: Add deprecation warnings to all functions
- `nano_graphrag/llm/__init__.py`: Update exports with deprecation handling

### Files to Create  
- `nano_graphrag/llm/legacy.py`: Compatibility layer for migration period
- `docs/migration_guide.md`: Detailed migration instructions

## Definition of Done

### Unit Tests Required
```python
# tests/test_legacy_deprecation.py

import pytest
import warnings
from nano_graphrag._llm import gpt_4o_complete, get_openai_async_client_instance

class TestLegacyDeprecation:
    @pytest.mark.asyncio
    async def test_deprecated_function_warns(self):
        """Test that deprecated functions show warnings."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # Mock the actual call to avoid needing API key
            from unittest.mock import patch
            with patch('nano_graphrag.llm.providers.gpt_4o_complete') as mock:
                mock.return_value = "test"
                await gpt_4o_complete("test")
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()
            assert "v0.2.0" in str(w[0].message)
    
    def test_global_client_deprecated(self):
        """Test that global client functions show deprecation."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # Don't actually create client, just check warning
            with pytest.raises(Exception):
                # Will fail due to missing API key, but warning should appear
                get_openai_async_client_instance()
            
            assert len(w) > 0
            assert any(issubclass(warning.category, DeprecationWarning) for warning in w)
    
    def test_legacy_import_warns(self):
        """Test that importing from legacy module shows warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            from nano_graphrag.llm import legacy
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "legacy module is deprecated" in str(w[0].message)
```

### Acceptance Criteria
- [ ] All legacy functions show deprecation warnings
- [ ] Warnings include migration path and removal version (actionable: what to import instead)
- [ ] Migration guide documentation created
- [ ] Legacy functions still work (backward compatibility maintained)
- [ ] Tests verify deprecation warnings appear
- [ ] Existing tests that call legacy functions updated to expect/suppress warnings
- [ ] No breaking changes for existing users

## Feature Branch
`feature/ngraf-008-legacy-cleanup`

## Pull Request Must Include
- Deprecation decorators and warnings
- Migration guide documentation
- Legacy compatibility module
- Tests for deprecation warnings
- Updated docstrings with deprecation notices

## Benefits
- **Clear Migration Path**: Users know exactly how to update their code
- **Gradual Transition**: No immediate breaking changes
- **Cleaner Codebase**: Clear separation of recommended vs deprecated
- **Better Documentation**: Migration guide helps users modernize
- **Maintainability**: Can remove legacy code in planned release