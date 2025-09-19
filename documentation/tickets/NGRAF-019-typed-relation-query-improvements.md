# NGRAF-019: Leverage Typed Relationships and Entity Types in Query Context

## Summary
Enhance query quality by surfacing typed relationships and improving entity type utilization in the query pipeline. This ticket implements three high-value improvements that require minimal code changes but provide immediate benefits to answer quality. **Critical**: Ensure directional relationships are preserved to maintain semantic correctness.

## Background
Following the implementation of NGRAF-018 (configurable entity types and typed relationships), we discovered that while typed relationships are correctly stored in the graph, they are not actively utilized during query execution. Expert review identified several "quick wins" that would leverage this stored metadata to improve query results without requiring architectural changes.

Current state:
- `relation_type` is stored but not included in query context
- Entity types guide extraction but aren't optimized for retrieval
- Community reports use generic relationship descriptions

## User Story
**As a** nano-graphrag user with domain-specific content
**I want** the system to leverage typed relationships and entity types during queries
**So that** I get more accurate and contextually relevant answers

## Acceptance Criteria

### AC1: Typed Relations in Query Context
- [ ] The relationships CSV passed to the LLM includes a `relation_type` column
- [ ] The column appears between `description` and `weight` columns
- [ ] **Edge direction is preserved as source→target from extraction (never sorted)**
- [ ] Local and global query prompt templates updated to explain relation_type column and its semantics
- [ ] All existing tests continue to pass
- [ ] Backward compatibility is maintained (missing relation_type defaults to "RELATED")

### AC2: Enhanced Community Reports
- [ ] Community report generation includes relation types in relationship descriptions
- [ ] Format: "Entity A [RELATION_TYPE] Entity B — description (weight: X)" for clarity
- [ ] **Direction is preserved in text (e.g., "A SUPERSEDES B" never becomes "B SUPERSEDES A")**
- [ ] Reports maintain readability while adding semantic precision
- [ ] Relation types are only included when available (graceful fallback)
 - [ ] Truncation prioritizes retaining relation_type and direction; shorten description first if needed

### AC3: Type-Enriched Entity Embeddings
- [ ] Entity descriptions are prefixed with bracketed type before embedding
- [ ] Format: "[ENTITY_TYPE] original description"
- [ ] Vector search correctly retrieves type-specific entities
- [ ] **Re-embedding recommended for existing deployments to realize benefits**
- [ ] Migration guide provided for transitioning existing embeddings
- [ ] Feature can be enabled/disabled via configuration

### AC4: Directionality Preservation (CRITICAL)
- [ ] Edge tuples are NEVER sorted when relation_type is present
- [ ] Source→target order from extraction is maintained throughout the pipeline
- [ ] Test verifies "A SUPERSEDES B" never inverts to "B SUPERSEDES A"
- [ ] Documentation clearly states how direction is handled for each storage backend

## Backend Direction Strategy

- NetworkX: Keep current graph representation, but persist extraction direction in edge attributes and use those attributes when building query contexts and reports. Never infer direction from sorted node IDs.
- Neo4j: Maintain extraction direction in relationships (MERGE (s)-[r:RELATED]->(t)). GDS projections may remain undirected for clustering only; query contexts and reports must use stored direction.
- Tests: Cover both backends to ensure no direction inversion occurs in emitted contexts.

## Technical Design

### Component 1: Add relation_type to Relationships CSV with Direction Preservation

**Location**: `nano_graphrag/_query.py`

**Current Implementation**:
```python
# _build_local_query_context function
relations_section_list = [
    ["id", "source", "target", "description", "weight", "rank"]
]
for i, e in enumerate(use_relations):
    relations_section_list.append([
        i,
        e["src_tgt"][0],  # Source preserved
        e["src_tgt"][1],  # Target preserved
        e["description"],
        e["weight"],
        e["rank"],
    ])
```

**Proposed Change**:
- Add `relation_type` column to the CSV header
- Extract `relation_type` from edge data (default to "RELATED" if missing)
- Insert relation_type between description and weight columns
- **CRITICAL**: Preserve source→target order (never use sorted tuples)
- Update local_rag_response prompt to explain the new column

**Implementation Notes**:
- The edge data should already contain `relation_type` from NGRAF-018
- Ensure backward compatibility by checking for field existence
- **Direction preservation**: Check all code paths to ensure edge tuples are never sorted when relation_type is present; rely on stored source/target attributes, not sorted pairs
- Update prompt template in `nano_graphrag/prompt.py` to include guidance on using relation_type

### Component 2: Surface Typed Relations in Community Reports with Directionality

**Location**: `nano_graphrag/_community.py`

**Current Implementation**:
Community reports summarize relationships generically without type information.

**Proposed Changes**:
1. Modify `_pack_single_community_context` to include relation types
2. Update the prompt template to guide the LLM to use relation types
3. Format relationship descriptions to be more semantically precise
4. **Preserve directionality in relationship text**

**Implementation Approach**:
- When building community context, check for `relation_type` in edges
- Format as: "Entity A [RELATION_TYPE] Entity B — description (weight: X)"
- Ensure the summarization prompt template acknowledges relation types
- **CRITICAL**: Never swap source/target positions
- Example: "Executive Order 14028 [SUPERSEDES] Executive Order 13800 — replaces previous framework (weight: 1.0)"

**Considerations**:
- Maintain readability with both type and description
- Gracefully handle edges without relation_type
- Preserve semantic direction (A→B never becomes B→A)
- Test with various community sizes to ensure scalability

### Component 3: Type-Prefix Entity Descriptions for Embeddings

**Location**: Multiple files
- `nano_graphrag/graphrag.py` (during entity vector DB update)
- `nano_graphrag/_extraction.py` (during entity processing)

**Current Implementation**:
```python
# In _extract_entities_wrapper
data_for_vdb = {
    compute_mdhash_id(dp["entity_name"], prefix="ent-"): {
        "content": dp["entity_name"] + dp["description"],
        "entity_name": dp["entity_name"],
    }
    for dp in all_entities_data
}
```

**Proposed Change**:
```python
# Prefix entity type to description before embedding
data_for_vdb = {
    compute_mdhash_id(dp["entity_name"], prefix="ent-"): {
        "content": dp["entity_name"] + f"[{dp.get('entity_type', 'UNKNOWN')}] " + dp["description"],
        "entity_name": dp["entity_name"],
    }
    for dp in all_entities_data
}
```

**Implementation Details**:
- Add type prefix in square brackets before description
- Use consistent format across all entity processing
- Ensure entity_type is available (use "UNKNOWN" as fallback)
- Test vector similarity with and without prefixes

**Migration Considerations**:
- Existing embeddings without type prefixes will still work but won't benefit from type-awareness
- **Re-embedding is recommended to realize full benefits**
- Provide configuration flag to enable/disable type prefixes
- Document migration path:
  1. Enable type prefixes in config
  2. Clear entity vector DB
  3. Re-insert documents to generate type-aware embeddings
- No schema changes required

## Testing Strategy

### Test File: `tests/test_typed_query_improvements.py`

```python
"""Tests for NGRAF-019 typed relationship query improvements."""

import pytest
import json
import numpy as np
from unittest.mock import AsyncMock, patch
from nano_graphrag import GraphRAG, QueryParam
from nano_graphrag.config import GraphRAGConfig, StorageConfig, EntityExtractionConfig
from nano_graphrag._query import _build_local_query_context
from nano_graphrag._community import _pack_single_community_context
from tests.utils import create_mock_llm_provider, create_mock_embedding_provider


class TestDirectionalityPreservation:
    """Test that directional relationships are never inverted."""

    @pytest.mark.asyncio
    async def test_directional_relations_preserved(self, tmp_path):
        """Verify A SUPERSEDES B never becomes B SUPERSEDES A."""
        # Create edges with clear directional semantics
        edges = [
            ("EO_14028", "EO_13800", {
                "description": "supersedes",
                "relation_type": "SUPERSEDES",
                "weight": 1.0
            }),
            ("STATUTE_2021", "REGULATION_2020", {
                "description": "revokes",
                "relation_type": "REVOKES",
                "weight": 0.8
            })
        ]

        # Ensure NO sorting happens
        for src, tgt, data in edges:
            # Verify tuple is never sorted
            assert (src, tgt) != tuple(sorted([src, tgt])) or src < tgt
            # If we see sorted tuples in output, test should fail

    @pytest.mark.asyncio
    async def test_sorted_tuples_detection(self, tmp_path):
        """Detect if code incorrectly sorts edge tuples."""
        # This test should FAIL if someone adds tuple(sorted(...))
        # anywhere in the relation processing pipeline


class TestTypedRelationsInQuery:
    """Test typed relationships in query context."""

    @pytest.mark.asyncio
    async def test_relation_type_in_csv(self, tmp_path):
        """Verify relation_type column appears in relationships CSV."""
        # Setup mock edge data with relation_type
        mock_edges = [
            {
                "src_tgt": ("EO_14028", "EO_13800"),
                "description": "supersedes",
                "relation_type": "SUPERSEDES",
                "weight": 1.0,
                "rank": 5
            },
            {
                "src_tgt": ("EO_14028", "STATUTE_2021"),
                "description": "implements",
                "relation_type": "IMPLEMENTS",
                "weight": 0.9,
                "rank": 3
            }
        ]

        # Mock the context building
        with patch('nano_graphrag._query._find_most_related_edges_from_entities') as mock_find_edges:
            mock_find_edges.return_value = mock_edges

            # Build context and verify CSV structure
            # ... implementation details

    @pytest.mark.asyncio
    async def test_relation_type_fallback(self, tmp_path):
        """Verify missing relation_type defaults to RELATED."""
        # Test edge without relation_type field
        # Verify it gets "RELATED" in CSV output

    @pytest.mark.asyncio
    async def test_backward_compatibility(self, tmp_path):
        """Verify queries still work with edges lacking relation_type."""
        # Create graph with old-style edges
        # Execute query
        # Verify no errors and reasonable output


class TestEnhancedCommunityReports:
    """Test typed relations in community reports."""

    @pytest.mark.asyncio
    async def test_community_report_with_typed_relations(self, tmp_path):
        """Verify community reports include relation types."""
        # Create mock community with typed edges
        # Generate report
        # Verify relation types appear in output

    @pytest.mark.asyncio
    async def test_community_report_formatting(self, tmp_path):
        """Verify relation types are formatted readably."""
        # Test various relation types
        # Verify formatting is consistent and clear


class TestTypeEnrichedEmbeddings:
    """Test entity type prefixes in embeddings."""

    @pytest.mark.asyncio
    async def test_entity_type_prefix_in_embeddings(self, tmp_path):
        """Verify entity types are prefixed to descriptions."""
        llm_provider = create_mock_llm_provider()
        embedding_provider = create_mock_embedding_provider()

        with patch.dict('os.environ', {
            'ENTITY_TYPES': 'EXECUTIVE_ORDER,STATUTE,REGULATION'
        }):
            config = GraphRAGConfig(
                storage=StorageConfig(working_dir=str(tmp_path)),
                entity_extraction=EntityExtractionConfig.from_env()
            )

            # Mock entity data with types
            mock_entities = [
                {
                    "entity_name": "EO_14028",
                    "entity_type": "EXECUTIVE_ORDER",
                    "description": "Cybersecurity improvement order"
                },
                {
                    "entity_name": "STATUTE_2021",
                    "entity_type": "STATUTE",
                    "description": "Federal cybersecurity legislation"
                }
            ]

            # Patch providers
            with patch('nano_graphrag.llm.providers.get_llm_provider', return_value=llm_provider), \
                 patch('nano_graphrag.llm.providers.get_embedding_provider', return_value=embedding_provider):

                rag = GraphRAG(config)

                # Mock the entity extraction
                rag.entity_extractor.extract = AsyncMock(return_value=mock_entities)

                # Capture what gets sent to embedding
                embedded_content = []

                async def capture_embed(texts):
                    embedded_content.extend(texts)
                    return {"embeddings": np.random.rand(len(texts), 1536)}

                embedding_provider.embed.side_effect = capture_embed

                # Process entities (this would happen during insert)
                # ... implementation

                # Verify prefixes were added
                for content in embedded_content:
                    if "EO_14028" in content:
                        assert "[EXECUTIVE_ORDER]" in content
                    if "STATUTE_2021" in content:
                        assert "[STATUTE]" in content

    @pytest.mark.asyncio
    async def test_type_prefix_improves_retrieval(self, tmp_path):
        """Verify type prefixes improve vector search accuracy."""
        # Compare retrieval with and without type prefixes
        # Query: "executive orders about cybersecurity"
        # Should retrieve EO entities better with prefix


class TestEndToEndQueryImprovement:
    """Test complete query flow with typed improvements."""

    @pytest.mark.asyncio
    async def test_local_query_with_typed_relations(self, tmp_path):
        """Test local query includes typed relationships in context."""
        llm_provider = create_mock_llm_provider([
            json.dumps({"points": [{"description": "Test", "score": 1}]}),
            "Executive Order 14028 SUPERSEDES Executive Order 13800."
        ])
        embedding_provider = create_mock_embedding_provider()

        with patch.dict('os.environ', {
            'ENTITY_TYPES': 'EXECUTIVE_ORDER,STATUTE',
            'RELATION_PATTERNS': json.dumps({"supersedes": "SUPERSEDES"})
        }):
            config = GraphRAGConfig(
                storage=StorageConfig(working_dir=str(tmp_path)),
                entity_extraction=EntityExtractionConfig.from_env()
            )

            with patch('nano_graphrag.llm.providers.get_llm_provider', return_value=llm_provider), \
                 patch('nano_graphrag.llm.providers.get_embedding_provider', return_value=embedding_provider):

                rag = GraphRAG(config)

                # Mock extraction result with typed relations
                mock_result = type('Result', (), {
                    'nodes': {
                        "EO_14028": {
                            "entity_name": "EO_14028",
                            "entity_type": "EXECUTIVE_ORDER",
                            "description": "Cybersecurity order",
                            "source_id": "chunk1"
                        },
                        "EO_13800": {
                            "entity_name": "EO_13800",
                            "entity_type": "EXECUTIVE_ORDER",
                            "description": "Previous order",
                            "source_id": "chunk1"
                        }
                    },
                    'edges': [
                        ("EO_14028", "EO_13800", {
                            "description": "supersedes",
                            "weight": 1.0,
                            "source_id": "chunk1",
                            "relation_type": "SUPERSEDES"  # Should appear in context
                        })
                    ]
                })()

                rag.entity_extractor.extract = AsyncMock(return_value=mock_result)

                # Insert and query
                await rag.ainsert("EO 14028 supersedes EO 13800")
                result = await rag.aquery("What supersedes what?", param=QueryParam(mode="local"))

                # Verify response mentions the typed relationship
                assert "SUPERSEDES" in result or "supersedes" in result.lower()
```

## Definition of Done

- [ ] All three components implemented
- [ ] Test file `tests/test_typed_query_improvements.py` created with all test cases
- [ ] All tests passing including existing test suite
- [ ] Backward compatibility verified through tests
- [ ] No performance regression observed
- [ ] Code review completed
 - [ ] Prompt templates updated (local and global) and brief docs added for CSV schema and directionality handling
 - [ ] Basic metrics added to track relation_type presence in contexts and token size impact

## Token Budget & Truncation

- When truncating relationships or report lines due to token limits, always retain relation_type and direction; shorten descriptions first.
- Monitor average token contribution of the relationships section pre/post change to avoid regressions.

## Dependencies

- Requires NGRAF-018 to be merged (typed relationships infrastructure)
- No external dependencies
- No breaking changes to existing APIs

## Risks and Mitigations

### Risk 1: Directional Relationship Inversion (CRITICAL)
- **Risk**: Sorting edge tuples could invert semantic meaning (e.g., "A SUPERSEDES B" → "B SUPERSEDES A")
- **Mitigation**:
  - Never use `tuple(sorted(...))` when relation_type is present
  - Add explicit tests for directionality preservation
  - Document direction handling for each storage backend
  - Code review must check for any edge tuple sorting

### Risk 2: Token Budget Overflow
- **Risk**: Additional columns and prefixes increase prompt size beyond token limits
- **Mitigation**:
  - Monitor token usage in truncation routines
  - Prioritize relation_type over description if space constrained
  - Test with maximum-size contexts

### Risk 3: Performance Impact
- **Risk**: Adding type prefixes might affect embedding quality
- **Mitigation**:
  - Test extensively with mocked providers
  - Provide configuration flag to disable if needed
  - Measure retrieval quality before/after

### Risk 4: Backward Compatibility
- **Risk**: Existing deployments might break with new CSV format
- **Mitigation**:
  - Ensure graceful fallbacks tested in backward compatibility tests
  - Default "RELATED" for missing relation_type
  - Test with pre-existing graphs

### Risk 5: LLM Confusion
- **Risk**: Additional columns/prefixes might confuse smaller models
- **Mitigation**:
  - Update prompts to explain new columns
  - Test with mock responses simulating various model behaviors
  - Provide clear column descriptions in prompt

## Future Enhancements (Out of Scope)

These are noted for future consideration but NOT part of this ticket:
- Dynamic relation type weighting based on query intent
- Relation type filtering in edge traversal
- Query-time relation type boosting
- Domain-specific relation type configurations
- **Directionally-aware edge selection** (using relation direction for traversal)
- Converting to directed graph storage where appropriate

## Implementation Order

1. **First**: Add relation_type to relationships CSV (simplest, immediate value)
2. **Second**: Enhance community reports (builds on first change)
3. **Third**: Type-prefix entity descriptions (independent but more complex)

## Notes for Implementation

- Keep changes minimal and focused
- Preserve all existing functionality
- Avoid over-engineering - these are "quick wins"
- Focus on readability and maintainability
- All tests use mocked providers following existing patterns in `tests/test_rag.py`
- No requirement for real LLM API keys

## Success Metrics

### Qualitative Metrics
- Improved answer accuracy for relationship-focused queries
- Better entity disambiguation in type-specific queries
- Enhanced community report clarity
- No degradation in general query performance
- All tests passing with mocked providers

### Quantitative Metrics (Optional Tracking)
- Fraction of edges with non-default relation_type in query contexts
- Token usage change per query (before/after adding relation_type column)
- Retrieval improvements for queries containing relation verbs (e.g., "supersedes", "implements")
- Count of directional relationships preserved correctly

### Simple Logging for Validation
```python
# Log these counters for monitoring
logger.info(f"Edges with typed relations: {typed_count}/{total_count}")
logger.info(f"Token increase from relation_type: {new_tokens - old_tokens}")
logger.info(f"Directional relations preserved: {preserved}/{total_directional}")
```

## References

- NGRAF-018: Custom Entity Types and Typed Relationships
- Expert Review: Codex Round 3 Analysis
- Original Discussion: Query-time benefits of typed relationships
- Test patterns: `tests/test_rag.py` and `tests/utils.py` for mocking approaches
