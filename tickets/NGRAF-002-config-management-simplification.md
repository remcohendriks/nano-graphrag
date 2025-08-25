# NGRAF-002: Simplify Configuration Management

## Summary
Replace the 30+ parameter GraphRAG dataclass with a clean configuration system using typed dataclasses and environment variables.

## Problem
- GraphRAG.__init__ has 30+ parameters making it unreadable
- Mix of concerns: LLM config, storage config, algorithm params in one class
- Difficult to understand defaults and override specific settings
- No validation of configuration values

## Technical Solution

```python
# nano_graphrag/config.py
from dataclasses import dataclass
from typing import Optional, Type
import os

@dataclass
class LLMConfig:
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    max_tokens: int = 32768
    max_concurrent: int = 16
    cache_enabled: bool = True
    
    @classmethod
    def from_env(cls) -> 'LLMConfig':
        return cls(
            provider=os.getenv("LLM_PROVIDER", "openai"),
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "32768")),
            max_concurrent=int(os.getenv("LLM_MAX_CONCURRENT", "16"))
        )

@dataclass
class StorageConfig:
    vector_backend: str = "hnswlib"
    graph_backend: str = "networkx"
    working_dir: str = "./workdir"
    
    # HNSW specific
    hnsw_max_elements: int = 1000000
    hnsw_ef_search: int = 200
    hnsw_M: int = 50

@dataclass
class GraphRAGConfig:
    llm: LLMConfig = None
    storage: StorageConfig = None
    chunk_size: int = 1200
    chunk_overlap: int = 100
    
    def __post_init__(self):
        self.llm = self.llm or LLMConfig.from_env()
        self.storage = self.storage or StorageConfig()
```

## Code Changes

### New Files
- `nano_graphrag/config.py` - Configuration dataclasses with validation

### Modified Files
- `nano_graphrag/graphrag.py` - Simplify to accept config object:
  ```python
  # Before: 30+ parameters
  def __init__(self, working_dir, enable_local, enable_naive_rag, chunk_func, ...)
  
  # After: Single config
  def __init__(self, config: Optional[GraphRAGConfig] = None):
      self.config = config or GraphRAGConfig()
  ```

- `app.py:86-119` - Use config object:
  ```python
  config = GraphRAGConfig(
      llm=LLMConfig(provider="deepseek", model="deepseek-chat"),
      storage=StorageConfig(vector_backend="hnswlib")
  )
  graph_func = GraphRAG(config)
  ```

## Definition of Done

### Unit Tests Required
```python
# tests/test_config.py
import pytest
from unittest.mock import patch
from nano_graphrag.config import LLMConfig, StorageConfig, GraphRAGConfig

class TestConfiguration:
    def test_llm_config_defaults(self):
        """Verify LLMConfig has sensible defaults"""
        config = LLMConfig()
        assert config.provider == "openai"
        assert config.model == "gpt-4o-mini"
        assert config.max_tokens == 32768
        assert isinstance(config.max_concurrent, int)
    
    def test_config_from_environment(self):
        """Verify config reads from environment variables"""
        with patch.dict(os.environ, {
            'LLM_PROVIDER': 'deepseek',
            'LLM_MODEL': 'deepseek-chat',
            'LLM_MAX_TOKENS': '65536'
        }):
            config = LLMConfig.from_env()
            assert config.provider == 'deepseek'
            assert config.model == 'deepseek-chat'
            assert config.max_tokens == 65536
    
    def test_storage_config_validation(self):
        """Verify storage config validates backend choices"""
        config = StorageConfig(vector_backend="invalid")
        with pytest.raises(ValueError, match="Unknown vector backend"):
            config.validate()
    
    def test_nested_config_initialization(self):
        """Verify GraphRAGConfig properly initializes nested configs"""
        config = GraphRAGConfig()
        assert config.llm is not None
        assert config.storage is not None
        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.storage, StorageConfig)
    
    def test_config_immutability(self):
        """Verify configs are frozen after creation"""
        config = LLMConfig()
        with pytest.raises(AttributeError):
            config.provider = "azure"
```

### Additional Test Coverage
- Test config serialization to/from JSON
- Test invalid value handling
- Test config merge/override behavior
- Test backwards compatibility wrapper

## Feature Branch
`feature/ngraf-002-config-simplification`

## Pull Request Must Include
- Proper typing for all config fields
- Validation of critical parameters
- Environment variable support
- Backwards compatibility shim for old initialization
- All tests passing with >90% coverage