# NGRAF-009: TypedDict Schemas for Core Data Structures

## Summary
Define TypedDict schemas for nodes, edges, chunks, and communities to improve type safety, IDE support, and code clarity.

## Context
The codebase currently uses mixed approaches - some TypedDicts in base.py, but many functions use plain dicts with unclear structure. This makes it hard to understand data shapes, leads to KeyError risks, and provides poor IDE support.

## Problem
- Inconsistent data structure definitions (dict vs TypedDict)
- No clear contract for node, edge, and chunk structures
- String-based type checking (e.g., `"gpt-5" in model_name`)
- Poor IDE autocomplete and type checking
- Easy to introduce bugs with typos in dict keys

## Technical Solution

**IMPORTANT**: This ticket focuses on defining TypedDicts and annotating signatures. NO runtime behavior changes. Current code uses tuples and dicts in specific shapes (e.g., `upsert_nodes_batch(list[tuple])`). We will annotate and validate but NOT change these runtime shapes yet.

### 1. Define Core Schemas
```python
# nano_graphrag/schemas.py

from typing import TypedDict, Optional, List, Dict, Any, Literal
from datetime import datetime
import numpy as np

class NodeSchema(TypedDict):
    """Graph node representation."""
    id: str
    entity_name: str
    entity_type: Optional[str]
    description: Optional[str]
    source_chunks: List[str]  # chunk IDs
    metadata: Dict[str, Any]

class EdgeSchema(TypedDict):
    """Graph edge representation."""
    source: str  # node ID
    target: str  # node ID
    relationship: str
    description: Optional[str]
    weight: float
    source_chunks: List[str]  # chunk IDs
    metadata: Dict[str, Any]

class ChunkSchema(TypedDict):
    """Text chunk representation."""
    id: str
    content: str
    token_count: int
    document_id: str
    chunk_index: int
    metadata: Dict[str, Any]

class EntityExtractionResult(TypedDict):
    """Result from entity extraction."""
    entities: List[NodeSchema]
    relationships: List[EdgeSchema]
    chunk_id: str

class CommunityReport(TypedDict):
    """Community analysis report."""
    community_id: str
    title: str
    summary: str
    findings: List[str]
    entities: List[str]  # entity names
    relationships: List[str]  # relationship descriptions
    rank: float
    metadata: Dict[str, Any]

class QueryContext(TypedDict):
    """Context for query execution."""
    query: str
    entities: List[NodeSchema]
    relationships: List[EdgeSchema]
    communities: List[CommunityReport]
    chunks: List[ChunkSchema]

class LLMMessage(TypedDict):
    """Standard LLM message format."""
    role: Literal["system", "user", "assistant"]
    content: str

class EmbeddingResult(TypedDict):
    """Embedding operation result."""
    texts: List[str]
    embeddings: np.ndarray
    model: str
    dimensions: int
```

### 2. Update Function Signatures
```python
# nano_graphrag/_extraction.py (after NGRAF-006)

from typing import List, Tuple
from .schemas import ChunkSchema, NodeSchema, EdgeSchema, EntityExtractionResult

async def extract_entities_and_relationships(
    chunks: List[ChunkSchema],
    llm_func: callable,
    prompt_template: Optional[str] = None,
    max_gleaning: int = 1
) -> List[EntityExtractionResult]:
    """Extract entities and relationships with typed results."""
    results: List[EntityExtractionResult] = []
    
    for chunk in chunks:
        # Process chunk with proper typing
        entities: List[NodeSchema] = []
        relationships: List[EdgeSchema] = []
        
        # Extraction logic...
        
        results.append(EntityExtractionResult(
            entities=entities,
            relationships=relationships,
            chunk_id=chunk["id"]
        ))
    
    return results

async def deduplicate_entities(
    entities: List[NodeSchema],
    similarity_threshold: float = 0.9
) -> List[NodeSchema]:
    """Deduplicate entities with typed input/output."""
    # Deduplication logic with proper typing
    pass
```

### 3. Provider Parameter Validation
```python
# nano_graphrag/llm/base.py

from typing import Union, get_args
from ..schemas import LLMMessage

# Define provider types as Literal
OpenAIModels = Literal["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]
AnthropicModels = Literal["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"]

def validate_model_name(
    model: str, 
    provider: Literal["openai", "anthropic", "azure", "bedrock"]
) -> bool:
    """Validate model name against known models for provider."""
    model_maps = {
        "openai": get_args(OpenAIModels),
        "anthropic": get_args(AnthropicModels),
        # etc.
    }
    
    valid_models = model_maps.get(provider, [])
    return model in valid_models

class BaseLLMProvider(ABC):
    def _build_messages(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[LLMMessage]] = None
    ) -> List[LLMMessage]:
        """Build message list with typed structure."""
        messages: List[LLMMessage] = []
        
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))
        
        if history:
            messages.extend(history)
            
        messages.append(LLMMessage(role="user", content=prompt))
        
        return messages
```

### 4. Storage Return Types (Phase 2 - NOT in this ticket)
```python
# NOTE: Storage protocol updates deferred until after NGRAF-006
# This ticket only adds schemas.py and type annotations to functions
# DO NOT change storage interfaces in this ticket

# Future (separate PR):
# nano_graphrag/base.py (update existing)

from typing import Protocol, List, Optional
from .schemas import NodeSchema, EdgeSchema, ChunkSchema

class BaseGraphStorage(Protocol):
    """Graph storage with typed returns."""
    
    async def upsert_nodes(self, nodes: List[NodeSchema]) -> None:
        """Insert or update nodes."""
        ...
    
    async def get_node(self, node_id: str) -> Optional[NodeSchema]:
        """Get node by ID with typed return."""
        ...
    
    async def get_nodes(
        self, 
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[NodeSchema]:
        """Get nodes with optional filtering."""
        ...
    
    async def upsert_edges(self, edges: List[EdgeSchema]) -> None:
        """Insert or update edges."""
        ...
    
    async def get_edges(
        self,
        source: Optional[str] = None,
        target: Optional[str] = None
    ) -> List[EdgeSchema]:
        """Get edges with typed return."""
        ...

class BaseKVStorage(Protocol):
    """KV storage with typed chunk operations."""
    
    async def upsert_chunks(self, chunks: List[ChunkSchema]) -> None:
        """Store text chunks."""
        ...
    
    async def get_chunks(
        self,
        chunk_ids: Optional[List[str]] = None
    ) -> List[ChunkSchema]:
        """Retrieve chunks by IDs."""
        ...
```

### 5. Runtime Validation Helpers
```python
# nano_graphrag/schemas.py

from typing import TypeGuard

def is_valid_node(data: Dict[str, Any]) -> TypeGuard[NodeSchema]:
    """Runtime validation for node structure."""
    required_keys = {"id", "entity_name"}
    return required_keys.issubset(data.keys())

def is_valid_edge(data: Dict[str, Any]) -> TypeGuard[EdgeSchema]:
    """Runtime validation for edge structure."""
    required_keys = {"source", "target", "relationship"}
    return required_keys.issubset(data.keys())

def validate_chunk(chunk: Dict[str, Any]) -> ChunkSchema:
    """Validate and coerce to ChunkSchema."""
    if not isinstance(chunk.get("token_count"), int):
        raise ValueError(f"Invalid token_count in chunk {chunk.get('id')}")
    
    return ChunkSchema(
        id=chunk["id"],
        content=chunk["content"],
        token_count=chunk["token_count"],
        document_id=chunk.get("document_id", ""),
        chunk_index=chunk.get("chunk_index", 0),
        metadata=chunk.get("metadata", {})
    )
```

## Code Changes

### Files to Create
- `nano_graphrag/schemas.py` (~200 lines)

### Files to Modify
- `nano_graphrag/base.py`: Update Protocol definitions with typed returns
- `nano_graphrag/_extraction.py` (after NGRAF-006): Use typed schemas
- `nano_graphrag/llm/base.py`: Use LLMMessage type
- Storage implementations: Return proper typed structures

## Definition of Done

### Unit Tests Required
```python
# tests/test_schemas.py

import pytest
from nano_graphrag.schemas import (
    NodeSchema, EdgeSchema, ChunkSchema,
    is_valid_node, is_valid_edge, validate_chunk
)

class TestSchemas:
    def test_node_schema_creation(self):
        """Test creating valid NodeSchema."""
        node: NodeSchema = {
            "id": "node1",
            "entity_name": "Test Entity",
            "entity_type": "Person",
            "description": "A test entity",
            "source_chunks": ["chunk1", "chunk2"],
            "metadata": {"key": "value"}
        }
        
        assert node["id"] == "node1"
        assert node["entity_name"] == "Test Entity"
    
    def test_node_validation(self):
        """Test node validation."""
        valid_node = {"id": "1", "entity_name": "Test"}
        invalid_node = {"id": "1"}  # Missing entity_name
        
        assert is_valid_node(valid_node)
        assert not is_valid_node(invalid_node)
    
    def test_chunk_validation(self):
        """Test chunk validation and coercion."""
        valid_chunk = {
            "id": "chunk1",
            "content": "Test content",
            "token_count": 10
        }
        
        result = validate_chunk(valid_chunk)
        assert result["id"] == "chunk1"
        assert result["document_id"] == ""  # Default value
        assert result["chunk_index"] == 0  # Default value
        
        invalid_chunk = {
            "id": "chunk1",
            "content": "Test",
            "token_count": "not_an_int"
        }
        
        with pytest.raises(ValueError):
            validate_chunk(invalid_chunk)
    
    def test_edge_schema(self):
        """Test EdgeSchema structure."""
        edge: EdgeSchema = {
            "source": "node1",
            "target": "node2",
            "relationship": "KNOWS",
            "description": "They know each other",
            "weight": 0.9,
            "source_chunks": ["chunk1"],
            "metadata": {}
        }
        
        assert edge["source"] == "node1"
        assert edge["weight"] == 0.9
```

### Acceptance Criteria
- [ ] All core data structures have TypedDict definitions
- [ ] Storage protocols use typed returns
- [ ] Extraction functions use typed schemas
- [ ] Runtime validation helpers available
- [ ] Tests verify schema structure and validation
- [ ] No behavioral changes
- [ ] IDE autocomplete works for typed structures

## Feature Branch
`feature/ngraf-009-typed-schemas`

## Pull Request Must Include
- Complete schema definitions
- Updated function signatures
- Runtime validation helpers
- Comprehensive tests
- Updated type hints throughout

## Benefits
- **Type Safety**: Catch structure errors at development time
- **IDE Support**: Full autocomplete for data structures
- **Documentation**: Self-documenting data shapes
- **Refactoring**: Easier to change structure with type checking
- **Bug Prevention**: No more KeyError from typos
- **Clarity**: Clear contracts for data flow