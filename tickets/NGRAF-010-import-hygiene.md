# NGRAF-010: Import Hygiene and Lazy Loading

## Summary
Move heavy dependencies to lazy imports inside functions to reduce import time and memory usage for users who don't use all features.

## Context
The codebase imports heavy libraries (dspy-ai, neo4j, hnswlib) at module level even when not used. This increases startup time and memory footprint unnecessarily. Some imports also risk circular dependencies.

## Problem
- Heavy libraries imported even when not used (dspy-ai is 100+ MB)
- Slow import times affect CLI tools and serverless functions
- Unnecessary memory usage for unused features
- Potential circular import risks at module level
- All backends loaded even when only one is used

## Technical Solution

### 1. Identify Heavy Imports
```python
# Current heavy imports at module level:
# - dspy (entity extraction)
# - neo4j (graph storage)
# - hnswlib (vector storage)
# - graspologic (community detection)
# - openai, aioboto3 (LLM providers)
```

### 2. Convert to Lazy Imports
```python
# nano_graphrag/entity_extraction/module.py

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import dspy

class TypedEntityRelationshipExtractor:
    def __init__(self):
        self._dspy: Optional['dspy'] = None
    
    @property
    def dspy(self):
        """Lazy load dspy only when needed."""
        if self._dspy is None:
            try:
                import dspy
                self._dspy = dspy
            except ImportError:
                raise ImportError(
                    "dspy-ai is required for typed entity extraction. "
                    "Install with: pip install dspy-ai"
                )
        return self._dspy
    
    def extract(self, text: str):
        """Use dspy for extraction."""
        # Now dspy is only imported when extract() is called
        dspy = self.dspy
        # ... use dspy
```

### 3. Storage Backend Lazy Loading
```python
# nano_graphrag/_storage/factory.py

from typing import Dict, Type, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .vdb_hnswlib import HNSWVectorStorage
    from .gdb_neo4j import Neo4jStorage

# IMPORTANT: Keep lazy loaders in same module to avoid circular imports
# Do NOT use package-level re-exports for lazy-loaded modules

class StorageFactory:
    _vector_backends: Dict[str, Callable] = {}
    _graph_backends: Dict[str, Callable] = {}
    
    @staticmethod
    def _get_hnswlib_class():
        """Lazy import HNSW storage."""
        from .vdb_hnswlib import HNSWVectorStorage
        return HNSWVectorStorage
    
    @staticmethod
    def _get_neo4j_class():
        """Lazy import Neo4j storage."""
        from .gdb_neo4j import Neo4jStorage
        return Neo4jStorage
    
    @classmethod
    def _register_backends(cls):
        """Register backends with lazy loaders."""
        if not cls._vector_backends:
            # Register with lazy loaders instead of direct imports
            cls.register_vector("hnswlib", cls._get_hnswlib_class)
            cls.register_vector("nano", lambda: cls._get_nano_class())
            
            cls.register_graph("networkx", cls._get_networkx_class)
            cls.register_graph("neo4j", cls._get_neo4j_class)
    
    @classmethod
    def create_vector_storage(cls, backend: str, **kwargs):
        """Create vector storage with lazy loading."""
        cls._register_backends()
        
        loader = cls._vector_backends.get(backend)
        if not loader:
            raise ValueError(f"Unknown vector backend: {backend}")
        
        # Load class only when creating instance
        storage_class = loader()
        return storage_class(**kwargs)
```

### 4. LLM Provider Lazy Loading
```python
# nano_graphrag/llm/__init__.py

from typing import TYPE_CHECKING

# Type checking imports (no runtime cost)
if TYPE_CHECKING:
    from .openai import OpenAIProvider, OpenAIEmbedding
    from .azure import AzureOpenAIProvider, AzureOpenAIEmbedding
    from .bedrock import BedrockProvider, BedrockEmbedding

# Always import base classes (lightweight)
from .base import (
    BaseLLMProvider,
    BaseEmbeddingProvider,
    CompletionParams,
    CompletionResponse,
    LLMError,
)

def get_provider(provider_type: str):
    """Lazy load provider based on type."""
    if provider_type == "openai":
        from .openai import OpenAIProvider
        return OpenAIProvider
    elif provider_type == "azure":
        from .azure import AzureOpenAIProvider
        return AzureOpenAIProvider
    elif provider_type == "bedrock":
        from .bedrock import BedrockProvider
        return BedrockProvider
    else:
        raise ValueError(f"Unknown provider: {provider_type}")
```

### 5. Community Detection Lazy Loading
```python
# nano_graphrag/_community.py (after NGRAF-006)

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import graspologic

class CommunityDetector:
    def __init__(self, algorithm: str = "leiden"):
        self.algorithm = algorithm
        self._graspologic: Optional['graspologic'] = None
    
    def detect_communities(self, graph):
        """Detect communities with lazy loading."""
        if self.algorithm == "leiden":
            if self._graspologic is None:
                try:
                    import graspologic
                    self._graspologic = graspologic
                except ImportError:
                    raise ImportError(
                        "graspologic is required for Leiden algorithm. "
                        "Install with: pip install graspologic"
                    )
            
            # Use graspologic for Leiden
            return self._graspologic.partition.leiden(graph)
        else:
            # Use built-in algorithm
            return self._detect_louvain(graph)
```

### 6. Optional Dependencies Check
```python
# nano_graphrag/_utils.py

import importlib.util
from typing import Dict

def check_optional_dependencies() -> Dict[str, bool]:
    """Check which optional dependencies are available."""
    deps = {
        "dspy": "dspy-ai",
        "neo4j": "neo4j", 
        "hnswlib": "hnswlib",
        "graspologic": "graspologic",
        "openai": "openai",
        "aioboto3": "aioboto3",
    }
    
    available = {}
    for module, package in deps.items():
        spec = importlib.util.find_spec(module)
        available[package] = spec is not None
    
    return available

def ensure_dependency(module_name: str, package_name: str, purpose: str):
    """Ensure a dependency is available or provide helpful error."""
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        raise ImportError(
            f"{package_name} is required for {purpose}.\n"
            f"Install with: pip install {package_name}\n"
            f"Or install all optional dependencies: pip install nano-graphrag[all]"
        )
```

### 7. Update Package Initialization
```python
# nano_graphrag/__init__.py

# Only import core, lightweight components
from .graphrag import GraphRAG, QueryParam

__version__ = "0.0.8.2"

# Don't import heavy components by default
# Users should import what they need:
# from nano_graphrag.llm.openai import OpenAIProvider
# from nano_graphrag.entity_extraction import TypedEntityExtractor
```

## Code Changes

### Files to Modify
- `nano_graphrag/_storage/factory.py`: Lazy backend loading
- `nano_graphrag/entity_extraction/module.py`: Lazy dspy import
- `nano_graphrag/_community.py`: Lazy graspologic import
- `nano_graphrag/llm/__init__.py`: Provider lazy loading
- `nano_graphrag/__init__.py`: Minimal default imports

### Files to Create
- `nano_graphrag/_utils.py`: Add dependency checking utilities

## Definition of Done

### Unit Tests Required
```python
# tests/test_lazy_imports.py

import pytest
import sys
from unittest.mock import patch

class TestLazyImports:
    def test_no_heavy_imports_on_init(self):
        """Test that importing nano_graphrag doesn't load heavy deps."""
        # Remove from sys.modules to test fresh import
        modules_to_check = ['dspy', 'neo4j', 'hnswlib', 'graspologic']
        for module in modules_to_check:
            sys.modules.pop(module, None)
        
        # Import nano_graphrag
        import nano_graphrag
        
        # Heavy modules should not be loaded
        assert 'dspy' not in sys.modules
        assert 'neo4j' not in sys.modules
        assert 'hnswlib' not in sys.modules
    
    def test_lazy_load_on_use(self):
        """Test that dependencies load when actually used."""
        from nano_graphrag._storage.factory import StorageFactory
        
        # Mock import to avoid actual dependency
        with patch('nano_graphrag._storage.factory.HNSWVectorStorage'):
            # Should not be imported until create is called
            assert 'hnswlib' not in sys.modules or sys.modules['hnswlib'] is None
            
            # Now create storage - should trigger import
            storage = StorageFactory.create_vector_storage("hnswlib")
            
            # Import should have been attempted
            assert storage is not None
    
    def test_helpful_error_on_missing_dep(self):
        """Test that missing dependencies give helpful errors."""
        from nano_graphrag._utils import ensure_dependency
        
        with pytest.raises(ImportError) as exc_info:
            ensure_dependency("nonexistent_module", "fake-package", "testing")
        
        error_msg = str(exc_info.value)
        assert "fake-package is required for testing" in error_msg
        assert "pip install fake-package" in error_msg
    
    def test_optional_deps_check(self):
        """Test checking optional dependencies."""
        from nano_graphrag._utils import check_optional_dependencies
        
        deps = check_optional_dependencies()
        
        # Should return dict of available deps
        assert isinstance(deps, dict)
        assert "openai" in deps
        assert isinstance(deps["openai"], bool)
```

### Performance Tests
```python
# tests/test_import_performance.py

import time
import subprocess
import sys

def test_import_time():
    """Test that import time is reasonable."""
    # Test import time in subprocess to avoid caching
    code = """
import time
start = time.time()
import nano_graphrag
end = time.time()
print(end - start)
"""
    
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True
    )
    
    import_time = float(result.stdout.strip())
    
    # Should be under 500ms without heavy deps
    assert import_time < 0.5, f"Import took {import_time:.2f}s"

def test_memory_usage():
    """Test that base import has reasonable memory footprint."""
    code = """
import tracemalloc
tracemalloc.start()
import nano_graphrag
current, peak = tracemalloc.get_traced_memory()
print(current / 1024 / 1024)  # MB
"""
    
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True
    )
    
    memory_mb = float(result.stdout.strip())
    
    # Should be under 50MB without heavy deps
    assert memory_mb < 50, f"Import used {memory_mb:.1f}MB"
```

### Acceptance Criteria
- [ ] Base import time under 500ms
- [ ] No heavy dependencies loaded on import
- [ ] Dependencies load only when features are used
- [ ] Helpful error messages for missing dependencies
- [ ] All existing functionality still works
- [ ] Tests verify lazy loading behavior
- [ ] Tests that import optional deps use pytest.skip or guard imports
- [ ] No circular imports introduced

## Feature Branch
`feature/ngraf-010-import-hygiene`

## Pull Request Must Include
- Converted lazy imports for all heavy dependencies
- Dependency checking utilities
- Performance tests for import time
- Documentation of optional dependencies
- No behavioral changes

## Benefits
- **Faster Startup**: 5-10x faster import for basic usage
- **Lower Memory**: 50-80% less memory for unused features
- **Better UX**: Users only install/load what they need
- **Serverless Friendly**: Faster cold starts
- **Clearer Dependencies**: Explicit about what requires what