# NGRAF-018 — Round 1 Review (expert-codex)

## Scope & Diff Summary

- Change category: New Feature (configurable entity types; typed relationships)
- Diff source: Working tree vs HEAD (multiple uncommitted changes present)
- Changed core files:
  - M `nano_graphrag/_extraction.py`
  - M `nano_graphrag/_storage/gdb_neo4j.py`
  - M `nano_graphrag/config.py`
  - M `nano_graphrag/graphrag.py`
- New tests:
  - A `tests/test_custom_entity_config.py`
  - A `tests/test_entity_config_usage.py`
  - A `tests/test_relation_types.py`
  - A `tests/test_custom_entity_integration.py`
- New docs:
  - A `documentation/tickets/NGRAF-018-custom-entity-types-configuration.md`
  - A `documentation/reports/NGRAF-018-round1-implementation.md`

`git diff --stat` (working tree): 4 files changed, 72 insertions(+), 5 deletions(-) across core code; plus 4 new tests, 2 docs.

## Summary Assessment

- Entity types are now configurable via `EntityExtractionConfig` and used by the extractor factory. Good.
- Relation type mapping utilities were added, but typed relations are not integrated in the active GraphRAG extraction path; they only apply in the legacy `_extraction.extract_entities` function. This misses the ticket goal for the default path. See Critical findings.
- One new integration test calls non-existent methods on the graph interface and will fail.

## Critical Issues (must fix)

- CODEX-001: nano_graphrag/graphrag.py:233–314 | High | Typed relations not applied in active extraction path | Map relation types before upserting edges in `_extract_entities_wrapper` or in `_merge_edges_then_upsert`.
  - Evidence: `_extract_entities_wrapper` gathers `result.edges` and forwards `edge_data` to `_merge_edges_then_upsert` without adding `relation_type`. Mapping exists only in `_extraction.extract_entities()` (lines ~381–387), which is not used by the wrapper.
  - Impact: `relation_type` never reaches storage for the primary (new) extractor path; Neo4j property stays unset, breaking the “typed relationships” acceptance criterion.
  - Recommendation: Inject relation mapping in wrapper prior to merge:
    - Load patterns via `get_relation_patterns()` and set `edge_data["relation_type"] = map_relation_type(edge_data.get("description", ""), patterns)` for each edge.
    - Alternatively, make `_merge_edges_then_upsert` compute `relation_type` if missing to centralize behavior.

- CODEX-002: tests/test_custom_entity_integration.py | High | Uses non-existent graph API (`nodes()`, `edges()`) | Replace with existing storage API calls.
  - Evidence: `BaseGraphStorage` and `NetworkXStorage` do not define `nodes()` or `edges()` methods.
  - Impact: Test will fail immediately; contradicts the implementation report’s “tests pass”.
  - Recommendation: Use available methods, e.g. fetch nodes via `get_node`/`get_nodes_batch` and edges via `get_node_edges` or storage-internal inspection. For simple verification, assert that `await graph.get_edge(src, tgt)` returns a dict with `relation_type`.

## High Priority

- CODEX-003: nano_graphrag/_extraction.py: entity types in legacy extractor | Medium | Still uses `PROMPTS["DEFAULT_ENTITY_TYPES"]` | Align with config.
  - Evidence: In `extract_entities()` and `extract_entities_from_chunks()`, `context_base` builds entity types from `PROMPTS["DEFAULT_ENTITY_TYPES"]`.
  - Impact: If callers use these legacy functions directly, configured entity types are ignored.
  - Recommendation: Accept `entity_types` via `global_config` (or function arg) and fall back to prompts if not provided.

- CODEX-004: tests lack assertion for persisted relation_type | Medium | No end-to-end test validates stored `relation_type` | Add verification.
  - Evidence: New tests validate config and mapping functions but never assert that edges contain the expected `relation_type` after insert.
  - Impact: Regressions in persistence would go unnoticed.
  - Recommendation: After `ainsert`, assert that `await graph.get_edge(src, tgt)` includes `relation_type == expected` (NetworkX backend suffices for CI).

## Medium Priority

- CODEX-005: nano_graphrag/config.py: Entity types normalization | Medium | `ENTITY_TYPES` not trimmed/uppercased | Normalize inputs.
  - Evidence: `EntityExtractionConfig.from_env()` splits CSV but doesn’t strip whitespace or normalize case.
  - Impact: Prompt quality and dedup may degrade (e.g., "drug" vs "DRUG").
  - Recommendation: Apply `[t.strip().upper() for t in entity_types]` and drop empties.

- CODEX-006: nano_graphrag/_extraction.py: Pattern false positives | Medium | Substring matching may misclassify | Use word boundaries or regex.
  - Evidence: `map_relation_type` checks `if pattern in desc_lower`; e.g., `uses` matches `houses`.
  - Impact: Incorrect `relation_type` classification in some texts.
  - Recommendation: Support regex patterns and compile with sensible defaults (e.g., `\bpattern\b`) while keeping substring fallback.

## Low Priority

- CODEX-007: nano_graphrag/_extraction.py: duplicate `import time` | Low | Redundant import at top and inside function | Remove inner import.

- CODEX-008: nano_graphrag/_storage/gdb_neo4j.py: redundant property set | Low | `r += edge.edge_data` sets `relation_type` then re-sets sanitized value | Remove `relation_type` from `edge_data_copy` before `SET r += edge.edge_data` or skip the later dedicated `SET`.

## Positive Observations

- CODEX-GOOD-001: Config plumbing | Clean propagation of `entity_types` through `GraphRAG._init_extractor` into the extractor factory.
- CODEX-GOOD-002: Neo4j safety | Sanitization via `_sanitize_label` and weight coercion with robust fallback.
- CODEX-GOOD-003: Defaults & fallbacks | Sensible default entity types and relation patterns; graceful JSON parse fallback with warning.
- CODEX-GOOD-004: Test coverage direction | Added unit tests for `from_env` and relation mapping, improving confidence.

## Reproduction Snippets

- Missing typed relations in active path (after implementing fix this should pass):
```python
import os, json, asyncio
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig

async def main():
    os.environ["ENTITY_TYPES"] = "PERSON,ORGANIZATION,EXECUTIVE_ORDER,STATUTE"
    os.environ["RELATION_PATTERNS"] = json.dumps({"supersedes": "SUPERSEDES"})
    rag = GraphRAG(GraphRAGConfig.from_env())
    text = "Executive Order 14028 supersedes Executive Order 13800."
    try:
        await rag.ainsert(text)
    except Exception:
        pass  # community reporting may require a real LLM
    # Verify: expect relation_type set on the edge once CODEX-001 is fixed
    g = rag.chunk_entity_relation_graph
    assert await g.get_edge("EXECUTIVE ORDER 14028", "EXECUTIVE ORDER 13800")
```

- Fix guidance for CODEX-001 (conceptual):
```python
# in GraphRAG._extract_entities_wrapper, before merging edges
from nano_graphrag._extraction import get_relation_patterns, map_relation_type
patterns = get_relation_patterns()
for (src, tgt), edge_list in maybe_edges.items():
    for e in edge_list:
        if "relation_type" not in e:
            e["relation_type"] = map_relation_type(e.get("description", ""), patterns)
```

## Closing Notes

Good step toward domain configurability. The main gap is applying relation typing in the default extraction path and aligning tests to the storage API. Addressing CODEX-001 and the test API issues should satisfy the ticket’s DoD. I can implement the wrapper mapping and update the integration test if you want me to proceed in this round.

