# NGRAF-022 Phase 3: Graph ↔ Vector Consistency Hardening

## Summary
Community generation now preserves embeddings via `update_payload`, which assumes every community node has a corresponding Qdrant vector. Recent batches exposed 404 failures where Neo4j contained relationship-derived placeholder nodes that never received vectors during extraction. Phase 3 ensures placeholder entities are either embedded or skipped safely so that payload preservation no longer aborts batch jobs.

## Problem Statement
- `_merge_edges_for_batch` synthesises missing nodes for relation endpoints (`nano_graphrag/_extraction.py:203`). Those nodes are written to Neo4j but never added to `all_entities_data`, so `entity_vdb.upsert` does not create a Qdrant point (`nano_graphrag/_extraction.py:303-322`).
- `_generate_community_reports` later enumerates every node ID from Neo4j and recomputes entity IDs (`nano_graphrag/graphrag.py:493-522`). When `update_payload` runs, Qdrant correctly returns 404 because the point does not exist (`nano_graphrag/_storage/vdb_qdrant.py:288-327`). The job fails even though the data discrepancy predates Phase 2.5.
- We need a deterministic way to track which Neo4j nodes are backed by vectors and prevent placeholder-only nodes from tripping the preservation path.

## Goals
1. Prevent `update_payload` from failing when encountering graph-only placeholder nodes.
2. Preserve deterministic entity IDs so that future merges do not reintroduce hash mismatches.
3. Add visibility into graph/vector divergence for operators.

## Non-Goals
- Reworking the entity extraction prompt flow.
- Replacing Qdrant or Neo4j transactional boundaries.

## Technical Plan

### 1. Tag placeholder nodes during extraction
- When `_merge_edges_for_batch` injects a missing endpoint, include a marker field (e.g. `"has_vector": False`) in the node payload prior to writing to Neo4j (`nano_graphrag/_extraction.py:203-216`).
- When real entities are merged via `_merge_nodes_for_batch`, set `"has_vector": True` so the property reflects the presence of a vector in Qdrant.
- Ensure the Neo4j write path (`Neo4jStorage._execute_batch_nodes` around `nano_graphrag/_storage/gdb_neo4j.py:566-640`) preserves this flag.

### 2. Update vector DB writes to keep the flag in sync
- After a successful `entity_vdb.upsert`, write the corresponding `has_vector=True` back to the graph for those entities (payload already in `all_entities_data`). Use batch payload update to avoid per-node round trips.
- If upsert fails, leave the flag unset so downstream logic can skip.

### 3. Filter payload-only updates
- In `_generate_community_reports`, build `updates` only for nodes with `has_vector=True`; skip or log placeholders before calling `update_payload`.
- Update `update_payload` logging to include skip counts and only raise when a point that *should* exist fails.

### 4. Instrument reconciliation metrics
- Emit counters during community generation summarising:
  - Total nodes in community schema.
  - Nodes skipped because `has_vector=False`.
  - Nodes with missing Qdrant points (should be 0 after fix).
- Add optional CLI utility or debug log to compare Neo4j IDs vs Qdrant IDs for diagnostics.

### 5. Tests
- Extend integration coverage to build a miniature graph with placeholder nodes and verify `update_payload` skips them without raising (`tests/test_qdrant_hybrid.py` or a new `tests/integration/test_vector_consistency.py`).
- Unit test `_merge_edges_for_batch` to ensure placeholder flag is set and that `_merge_nodes_for_batch` preserves `has_vector` when merging existing nodes.

## File / Line References
- `nano_graphrag/_extraction.py`
  - `_merge_edges_for_batch` (lines ~203-220): tag placeholder nodes with `has_vector=False`.
  - `_merge_nodes_for_batch` (lines ~126-170): propagate `has_vector` based on existing graph state.
  - `extract_entities` vector upsert block (lines ~463-488): batch-update graph nodes to `has_vector=True` after successful upsert.
- `nano_graphrag/_storage/gdb_neo4j.py`
  - Batch node execution (lines ~566-640) to allow `has_vector` writes.
- `nano_graphrag/graphrag.py`
  - `_generate_community_reports` payload-preservation branch (lines ~493-523): skip nodes without vectors and emit metrics.
- `nano_graphrag/_storage/vdb_qdrant.py`
  - `update_payload` (lines ~288-327): tolerate skipped nodes and improve diagnostics.
- Tests: `tests/test_qdrant_hybrid.py` and/or new integration test to assert skip behaviour.

## Risks & Mitigations
- **Risk:** Flag drift between Neo4j and Qdrant.
  - *Mitigation:* Only set `has_vector=True` after successful Qdrant upsert; log discrepancies during reconciliation.
- **Risk:** Additional graph writes increase batch time.
  - *Mitigation:* Use bulk payload updates; reuse existing Neo4j batch infrastructure.

## Acceptance Criteria
- Community generation completes without 404 errors when placeholder-only nodes exist.
- Logs show counts of nodes skipped for lacking vectors.
- Integration test reproduces prior failure scenario and passes with new logic.
- Manual verification: After ingesting a document set, Neo4j node count matches Qdrant point count for nodes flagged `has_vector=True`.
