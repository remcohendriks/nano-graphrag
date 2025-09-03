# NGRAF-007: Config Normalization

## Summary
Clean up `GraphRAGConfig.to_dict()` by moving legacy compatibility fields to a dedicated method, maintaining backward compatibility while improving config clarity.

**UPDATE**: Focus on clear separation between active config (`to_dict()`) and legacy shims (`to_legacy_dict()`). The expert correctly identified this distinction is crucial for maintainability.

**EXPERT CONSENSUS**: All three assessments confirm this ticket is HIGHLY VIABLE and should be prioritized. Key discovery: node2vec parameters are actively used by NetworkX storage and need proper relocation, not removal.

## Context
After NGRAF-002 config simplification, `GraphRAGConfig.to_dict()` contains 70+ lines mixing actual configuration with legacy compatibility fields. This makes it hard to understand what configuration actually matters versus what's there for backward compatibility. The current implementation makes it unclear which fields the system actually uses.

## Problem
- `to_dict()` method conflates real config with compatibility shims (47+ lines mixing concerns)
- Hard to tell which fields are actually used vs legacy
- Node embedding parameters incorrectly assumed unused (actually used by NetworkX storage)
- Confusing for maintainers and users
- Multiple call sites (3 in graphrag.py) depend on mixed configuration

## Technical Solution

### Separate Legacy Compatibility
```python
# nano_graphrag/config.py

@dataclass
class GraphRAGConfig:
    """Main GraphRAG configuration."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    entity_extraction: EntityExtractionConfig = field(default_factory=EntityExtractionConfig)
    graph_clustering: GraphClusteringConfig = field(default_factory=GraphClusteringConfig)
    query: QueryConfig = field(default_factory=QueryConfig)
    
    def to_dict(self) -> dict:
        """Convert config to dictionary with only active configuration."""
        config_dict = {
            # Storage
            'working_dir': self.storage.working_dir,
            
            # Chunking
            'chunk_token_size': self.chunking.size,
            'chunk_overlap_token_size': self.chunking.overlap,
            'tokenizer_type': self.chunking.tokenizer,
            
            # Entity extraction
            'entity_extract_max_gleaning': self.entity_extraction.max_gleaning,
            'entity_summary_to_max_tokens': self.entity_extraction.summary_max_tokens,
            
            # Graph clustering
            'graph_cluster_algorithm': self.graph_clustering.algorithm,
            'max_graph_cluster_size': self.graph_clustering.max_cluster_size,
            'graph_cluster_seed': self.graph_clustering.seed,
            
            # Embedding
            'embedding_batch_num': self.embedding.batch_size,
            'embedding_func_max_async': self.embedding.max_concurrent,
            
            # Query
            'enable_local': self.query.enable_local,
            'enable_naive_rag': self.query.enable_naive_rag,
            'query_better_than_threshold': self.query.similarity_threshold,
            
            # LLM
            'best_model_max_token_size': self.llm.max_tokens,
            'best_model_max_async': self.llm.max_concurrent,
            'enable_llm_cache': self.llm.cache_enabled,
        }
        
        # Add storage backend specific config if needed
        # IMPORTANT: Keep HNSW kwargs mapping intact - required by storage creation
        if self.storage.vector_backend == "hnswlib":
            config_dict['vector_db_storage_cls_kwargs'] = {
                'ef_construction': self.storage.hnsw_ef_construction,
                'ef_search': self.storage.hnsw_ef_search,
                'M': self.storage.hnsw_m,
                'max_elements': self.storage.hnsw_max_elements,
            }
        
        return config_dict
    
    def to_legacy_dict(self) -> dict:
        """Convert to legacy dictionary format for backward compatibility.
        
        This method includes all legacy fields needed by older code paths.
        New code should use to_dict() or access config attributes directly.
        """
        # Start with active config
        config_dict = self.to_dict()
        
        # Add legacy/compatibility fields
        legacy_additions = {
            # Duplicate model config for "cheap" model (legacy assumed different models)
            'cheap_model_max_token_size': self.llm.max_tokens,
            'cheap_model_max_async': self.llm.max_concurrent,
            
            # Tokenizer model names (legacy required both even if only one used)
            'tiktoken_model_name': self.chunking.tokenizer_model if self.chunking.tokenizer == "tiktoken" else "gpt-4o",
            'huggingface_model_name': self.chunking.tokenizer_model if self.chunking.tokenizer == "huggingface" else "bert-base-uncased",
            
            # Node embedding config (ACTUALLY USED by NetworkX storage - needs proper relocation)
            'node_embedding_algorithm': 'node2vec',
            'node2vec_params': {
                'dimensions': self.embedding.dimension,
                'num_walks': 10,
                'walk_length': 40,
                'window_size': 2,
                'iterations': 3,
                'random_seed': 3,
            },
            
            # Legacy flags
            'always_create_working_dir': True,
            'addon_params': {},
        }
        
        config_dict.update(legacy_additions)
        return config_dict
```

### Update GraphRAG Constructor
```python
# nano_graphrag/graphrag.py

class GraphRAG:
    def __init__(
        self,
        config: Optional[GraphRAGConfig] = None,
        best_model_func: Optional[callable] = None,
        cheap_model_func: Optional[callable] = None,
        embedding_func: Optional[callable] = None,
        # ... other params
    ):
        # Use clean config internally
        self.config = config or GraphRAGConfig()
        
        # For legacy code expecting the full dict
        self.global_config = self.config.to_legacy_dict()
        
        # Clean internal usage
        self._llm_cache_enabled = self.config.llm.cache_enabled
        self._chunk_size = self.config.chunking.size
        # etc.
```

### Add Node2Vec Configuration
```python
# nano_graphrag/config.py

@dataclass
class Node2VecConfig:
    """Node2Vec parameters for graph embeddings."""
    dimensions: int = 128
    num_walks: int = 10
    walk_length: int = 40
    window_size: int = 2
    iterations: int = 3
    random_seed: int = 3

@dataclass
class StorageConfig:
    """Storage configuration."""
    # ... existing fields ...
    node2vec: Node2VecConfig = field(default_factory=Node2VecConfig)
```

### Add Config Validation Helper
```python
# nano_graphrag/config.py

def validate_config(config: GraphRAGConfig) -> List[str]:
    """Validate configuration and return list of warnings."""
    warnings = []
    
    # Check for common misconfigurations
    if config.chunking.size < config.chunking.overlap:
        warnings.append("Chunk overlap larger than chunk size")
    
    if config.storage.vector_backend == "hnswlib" and config.storage.hnsw_ef_search > 500:
        warnings.append("Very high ef_search may impact performance")
    
    if config.llm.max_concurrent > 100:
        warnings.append("Very high max_concurrent may hit rate limits")
    
    return warnings
```

## Code Changes

### Files to Modify
- `nano_graphrag/config.py`:
  - Add `Node2VecConfig` dataclass
  - Split `to_dict()` into clean and legacy versions
  - Add `validate_config()` helper
  - Add docstrings explaining the split

- `nano_graphrag/graphrag.py`:
  - Update `_global_config()` to use `to_legacy_dict()`
  - Keep `to_dict()` for storage factory
  - Add config validation on init

- `nano_graphrag/_storage/gdb_networkx.py`:
  - Update to use proper Node2VecConfig instead of global_config
  
### Migration Path
1. Phase 1: Create separation with both methods (backward compatible)
2. Phase 2: Audit all 14 global_config references and migrate to direct config access
3. Phase 3: Move node2vec params to proper StorageConfig location
4. Phase 4: Mark `to_legacy_dict()` as deprecated in v0.2.0
5. Phase 5: Remove in v0.3.0

## Definition of Done

### Unit Tests Required
```python
# tests/test_config.py (update existing)

def test_config_to_dict_clean():
    """Test that to_dict() only includes active configuration."""
    config = GraphRAGConfig()
    result = config.to_dict()
    
    # Should NOT include legacy fields
    assert 'node_embedding_algorithm' not in result
    assert 'node2vec_params' not in result
    assert 'addon_params' not in result
    assert 'always_create_working_dir' not in result
    
    # Should include active fields
    assert 'chunk_token_size' in result
    assert 'working_dir' in result

def test_config_to_legacy_dict():
    """Test that to_legacy_dict() includes compatibility fields."""
    config = GraphRAGConfig()
    result = config.to_legacy_dict()
    
    # Should include legacy fields
    assert 'node_embedding_algorithm' in result
    assert result['node_embedding_algorithm'] == 'node2vec'
    assert 'node2vec_params' in result
    assert 'cheap_model_max_token_size' in result
    
    # Should also include active fields
    assert 'chunk_token_size' in result

def test_config_validation():
    """Test configuration validation."""
    config = GraphRAGConfig()
    config.chunking.size = 100
    config.chunking.overlap = 200  # Invalid: overlap > size
    
    warnings = validate_config(config)
    assert len(warnings) > 0
    assert "overlap larger than chunk size" in warnings[0]

def test_backward_compatibility():
    """Test that legacy code still works."""
    config = GraphRAGConfig()
    legacy_dict = config.to_legacy_dict()
    
    # Simulate legacy code expectations
    assert legacy_dict['cheap_model_max_token_size'] == legacy_dict['best_model_max_token_size']
    assert 'tiktoken_model_name' in legacy_dict
    assert 'huggingface_model_name' in legacy_dict
```

### Acceptance Criteria
- [ ] `to_dict()` returns only active configuration (~20 lines)
- [ ] `to_legacy_dict()` maintains full backward compatibility (~47 lines)
- [ ] Node2vec params properly relocated to StorageConfig, not just marked legacy
- [ ] Audit confirms all 14 global_config usage points
- [ ] Config validation helper identifies common issues
- [ ] All existing tests pass
- [ ] Documentation updated to clarify config methods
- [ ] Migration guide for config access patterns
- [ ] No behavioral changes in GraphRAG
- [ ] Storage Factory correctly reads HNSW params from clean dict

## Feature Branch
`feature/ngraf-007-config-normalization`

## Pull Request Must Include
- Separated config methods
- Config validation helper
- Updated tests
- Clear documentation of active vs legacy fields
- All existing tests passing

## Implementation Priority

### HIGH PRIORITY (Expert Consensus)
This ticket should be implemented soon because:
1. **Active Usage Discovery**: Node2vec parameters are actually used, not legacy
2. **Clarity Crisis**: 47+ lines mixing active and legacy config causes ongoing confusion
3. **Tech Debt Accumulation**: Each new feature adds to config complexity
4. **Post-NGRAF-006 Synergy**: Complements module decomposition perfectly

### Risk Assessment
- **Low Risk**: Backward compatibility fully maintained
- **Medium Complexity**: Need to audit 14 global_config references
- **High Value**: Significant maintainability improvement

## Benefits
- **Clarity**: Clear separation between active config and compatibility
- **Maintainability**: Easy to see what can be removed in future versions
- **Documentation**: Self-documenting what's actually used
- **Migration Path**: Clean path to remove legacy fields
- **Validation**: Proactive detection of misconfigurations
- **Reduced Confusion**: Developers can easily identify active vs legacy fields