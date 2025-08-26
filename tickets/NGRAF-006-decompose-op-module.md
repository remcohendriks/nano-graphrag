# NGRAF-006: Decompose _op.py Module

## Summary
Split the monolithic `_op.py` file into focused modules for chunking, extraction, community reports, and queries to improve maintainability and testability.

## Context
The `_op.py` file is currently 1000+ lines mixing multiple concerns. This violates single responsibility principle and makes the code hard to navigate, test, and maintain. After NGRAF-001/002/003, we have clean provider and storage abstractions, but the core operations remain entangled.

## Problem
- Single file handles chunking, entity extraction, community detection, and query operations
- Difficult to find specific functionality
- Hard to test individual components
- Functions rely on global_config dict patterns
- Mixed abstraction levels in same file

## Technical Solution

### Module Structure
```
nano_graphrag/
├── _op.py (deprecated, imports from new modules for compatibility)
├── _chunking.py (text chunking operations)
├── _extraction.py (entity and relationship extraction)
├── _community.py (community detection and report generation)
└── _query.py (local, global, and naive query operations)
```

### 1. _chunking.py
```python
# Move from _op.py
from typing import List, Tuple, Optional
from .base import TextChunkSchema
from ._utils import TokenizerWrapper

async def chunk_text_by_token_size(
    text: str,
    tokenizer: TokenizerWrapper,
    chunk_size: int = 1200,
    overlap_size: int = 100
) -> List[TextChunkSchema]:
    """Chunk text into token-sized segments with overlap."""
    # Existing chunking logic from _op.py
    pass

async def chunk_documents(
    docs: dict,
    tokenizer: TokenizerWrapper,
    chunk_size: int = 1200,
    overlap_size: int = 100
) -> List[TextChunkSchema]:
    """Chunk multiple documents."""
    # Existing batch chunking logic
    pass
```

### 2. _extraction.py
```python
# Move from _op.py
from typing import List, Tuple, Dict, Any
from .base import TextChunkSchema

async def extract_entities_and_relationships(
    chunks: List[TextChunkSchema],
    llm_func: callable,
    prompt_template: str = None,
    max_gleaning: int = 1
) -> Tuple[List[Dict], List[Dict]]:
    """Extract entities and relationships from text chunks."""
    # Existing extraction logic from _op.py
    pass

async def deduplicate_entities(
    entities: List[Dict],
    llm_func: callable = None
) -> List[Dict]:
    """Deduplicate and merge similar entities."""
    # Existing deduplication logic
    pass
```

### 3. _community.py
```python
# Move from _op.py
from typing import List, Dict, Optional
from .base import CommunitySchema, BaseGraphStorage

async def detect_communities(
    graph: BaseGraphStorage,
    algorithm: str = "leiden",
    max_size: int = 10
) -> List[CommunitySchema]:
    """Detect communities in the graph."""
    # Existing community detection logic
    pass

async def generate_community_report(
    community: CommunitySchema,
    llm_func: callable,
    prompt_template: str = None
) -> str:
    """Generate summary report for a community."""
    # Existing report generation logic
    pass
```

### 4. _query.py
```python
# Move from _op.py
from typing import List, Dict, Any
from .base import QueryParam

async def local_query(
    query: str,
    graph_storage: BaseGraphStorage,
    vector_storage: BaseVectorStorage,
    llm_func: callable,
    param: QueryParam
) -> str:
    """Execute local graph query."""
    # Existing local query logic
    pass

async def global_query(
    query: str,
    community_reports: List[str],
    llm_func: callable,
    param: QueryParam
) -> str:
    """Execute global query across communities."""
    # Existing global query logic
    pass

async def naive_query(
    query: str,
    vector_storage: BaseVectorStorage,
    llm_func: callable,
    param: QueryParam
) -> str:
    """Execute naive RAG query."""
    # Existing naive query logic
    pass
```

### 5. Update _op.py for Backward Compatibility
```python
# _op.py - Maintains imports for backward compatibility
"""
DEPRECATED: This module is preserved for backward compatibility.
Please import from the specific modules instead:
- _chunking: Text chunking operations
- _extraction: Entity and relationship extraction
- _community: Community detection and reports
- _query: Query operations
"""

import warnings

# Import all functions from new modules
from ._chunking import (
    chunk_text_by_token_size,
    chunk_documents,
    chunking_by_token_size  # Keep original names
)
from ._extraction import (
    extract_entities_and_relationships,
    deduplicate_entities
)
from ._community import (
    detect_communities,
    generate_community_report
)
from ._query import (
    local_query,
    global_query,
    naive_query
)

# Show deprecation warning
warnings.warn(
    "Importing from _op.py is deprecated. "
    "Please import from specific modules: _chunking, _extraction, _community, _query",
    DeprecationWarning,
    stacklevel=2
)
```

## Implementation Guidelines

### Phase 1: Extract Without Changes
1. Copy functions to new modules exactly as-is
2. **CRITICAL: Preserve global_config usage patterns** - do not change function signatures
3. Update imports in new modules
4. Add backward compatibility imports to _op.py
5. Verify all existing tests pass

### Phase 2: Clean Up (Separate PR - NOT part of this ticket)
1. Replace global_config dict with explicit parameters
2. Add type hints throughout
3. Remove unused functions
4. Standardize error handling

**Important**: This ticket ONLY covers Phase 1. Preserve all global_config-based call shapes to avoid breaking query/report flows.

## Code Changes

### Files to Create
- `nano_graphrag/_chunking.py` (~200 lines)
- `nano_graphrag/_extraction.py` (~300 lines)
- `nano_graphrag/_community.py` (~250 lines)
- `nano_graphrag/_query.py` (~250 lines)

### Files to Modify
- `nano_graphrag/_op.py` - Add deprecation warning and re-exports
- `nano_graphrag/graphrag.py` - Update imports to use new modules directly

## Definition of Done

### Unit Tests Required
```python
# tests/test_chunking.py
import pytest
from nano_graphrag._chunking import chunk_text_by_token_size
from nano_graphrag._utils import TokenizerWrapper

class TestChunking:
    @pytest.mark.asyncio
    async def test_chunk_text_basic(self):
        """Test basic text chunking."""
        tokenizer = TokenizerWrapper(encoding_name="gpt-4o")
        text = "This is a test. " * 100
        
        chunks = await chunk_text_by_token_size(
            text, tokenizer, chunk_size=50, overlap_size=10
        )
        
        assert len(chunks) > 1
        assert all(c.token_count <= 50 for c in chunks)
    
    @pytest.mark.asyncio
    async def test_chunk_overlap(self):
        """Test chunk overlap is maintained."""
        # Test overlap logic
        pass

# tests/test_extraction.py
import pytest
from unittest.mock import AsyncMock
from nano_graphrag._extraction import extract_entities_and_relationships

class TestExtraction:
    @pytest.mark.asyncio
    async def test_entity_extraction(self):
        """Test entity extraction from chunks."""
        mock_llm = AsyncMock(return_value="entity1<SEP>entity2")
        chunks = [{"content": "test text"}]
        
        entities, relations = await extract_entities_and_relationships(
            chunks, mock_llm
        )
        
        assert len(entities) > 0
        mock_llm.assert_called()

# tests/test_community.py
# tests/test_query.py
```

### Acceptance Criteria
- [ ] All functions moved to appropriate modules
- [ ] Backward compatibility maintained via _op.py
- [ ] All existing tests pass without modification
- [ ] New module-specific tests added
- [ ] No behavioral changes
- [ ] Deprecation warning shown when importing from _op.py
- [ ] Documentation updated to reference new modules

## Feature Branch
`feature/ngraf-006-decompose-op`

## Pull Request Must Include
- Four new focused modules
- Updated _op.py with deprecation warning
- Module-specific unit tests
- Zero behavioral changes
- All existing tests passing

## Benefits
- **Single Responsibility**: Each module has one clear purpose
- **Testability**: Easier to test individual components
- **Maintainability**: Easier to find and modify specific functionality
- **Scalability**: New features can be added to appropriate modules
- **Performance**: Can import only needed functionality