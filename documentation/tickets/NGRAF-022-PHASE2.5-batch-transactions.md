# NGRAF-022 Phase 2.5: Wire Up Batch Transactions

## User Story
As a platform engineer, I need document ingestion to use the existing batch transaction pipeline so that each document hits Neo4j with a handful of deterministic `UNWIND` queries instead of hundreds of single-row MERGEs, restoring the throughput we expected when Phase 2 introduced the new extractor abstraction.

## Current State
- `GraphRAG._init_functions()` still assigns `self.entity_extraction_func = self._extract_entities_wrapper` (`nano_graphrag/graphrag.py:236`).
- `_extract_entities_wrapper` iterates the extracted entities and edges and calls `_merge_nodes_then_upsert` / `_merge_edges_then_upsert` for every key (`nano_graphrag/graphrag.py:270-302`). Each helper ends up invoking `Neo4jStorage.upsert_node` or `upsert_edge`, which wraps the batch helpers but with a singleton payload, producing one round-trip per entity/relationship (`nano_graphrag/_extraction.py:164-213`, `nano_graphrag/_storage/gdb_neo4j.py:420-520`).
- The real batch implementation (`extract_entities` in `_extraction.py:271-470`) builds a `DocumentGraphBatch`, merges all nodes/edges, and calls `execute_document_batch`, but nothing in the main ingestion flow reaches that function.
- Result: a document with ~50 entities and ~75 relationships still spawns ~125 separate transactions even though the batch infrastructure exists.

## Problem Statement
Phase 2 removed document-level parallelism to eliminate deadlocks, but we never actually switched to the batched write path. The primary bottleneck is therefore the transaction count per document, not the lack of inter-document concurrency. Until we fix this wiring issue, higher-level optimisations (chunk tuning, entity-level locks, etc.) are premature.

## Objectives
1. Rewire the ingestion flow so that documents use a `DocumentGraphBatch` and `execute_document_batch()`.
2. Ensure we retain the new `entity_extractor` abstraction while batching writes (no regression to the legacy parser).
3. Leverage the existing `NEO4J_BATCH_SIZE` configuration by threading it into the document batching path.
4. Add instrumentation to confirm the number of Neo4j transactions per document before and after the change.

## Detailed Plan

### 1. Update `_extract_entities_wrapper`
- After collecting `maybe_nodes`/`maybe_edges`, replace the per-entity `for` loops with the same logic used in `_extraction.extract_entities`:
  ```python
  from nano_graphrag._extraction import (
      DocumentGraphBatch,
      _merge_nodes_for_batch,
      _merge_edges_for_batch
  )
  batch = DocumentGraphBatch()
  all_entities_data = []

  for entity_name, nodes_data in maybe_nodes.items():
      merged_name, merged_data = await _merge_nodes_for_batch(...)
      batch.add_node(merged_name, merged_data)
      # collect data for VDB update

  for (src_id, tgt_id), edges_data in maybe_edges.items():
      await _merge_edges_for_batch(src_id, tgt_id, edges_data, ..., batch=batch)

  await knwoledge_graph_inst.execute_document_batch(batch)
  ```
- Remove the `_merge_nodes_then_upsert` / `_merge_edges_then_upsert` calls from the wrapper entirely; keep those helpers for any legacy call sites (tests still reference them).

### 2. Respect `neo4j_batch_size`
- `DocumentGraphBatch.chunk()` currently hardcodes `max_size=10`. Plumb `global_config["addon_params"].get("neo4j_batch_size", 1000)` through `_extract_entities_wrapper` into `execute_document_batch` so the chunk size follows the operator-configured value.
- If passing the size directly is messy, add a `chunk_size` attribute to `DocumentGraphBatch` or expose a setter before executing the batch.

### 3. Instrumentation & Validation
- Extend the existing `_operation_counts` or add a scoped logger entry to emit `batch.nodes`, `batch.edges`, and the number of chunks processed inside `execute_document_batch` (can be derived from `len(batch.chunk(...))`).
- Capture the transaction count before and after wiring the batch path (a simple integration test can assert `self._operation_counts['upsert_node']` stays at zero while `execute_document_batch` increments a new counter).
- Update or add an integration test that processes a fixture document and asserts Neo4j gets ≤ `ceil((nodes+edges)/neo4j_batch_size)` transactions instead of `nodes+edges` transactions.

### 4. Documentation
- Document the new behaviour and configuration hook in `docs/use_neo4j_for_graphrag.md` so operators know `NEO4J_BATCH_SIZE` now also governs document ingestion.

## Out of Scope / Follow-Up
- Inter-document parallelism and entity-level locking remain future work (Phase 3). We need fresh metrics after batching is active before deciding on additional coordination strategies.
- Optimising Neo4j session reuse inside `execute_document_batch` is optional once the main wiring is complete.

## Risks & Mitigations
- **Regression in new extractor abstraction**: Ensure `_extract_entities_wrapper` still returns `all_entities_data` for the vector DB update and preserves entity type mapping.
- **Neo4j payload limits**: Continue to respect `neo4j_batch_size` and rely on Tenacity retries to handle transient errors.
- **Legacy helper usage**: Confirm no external code paths still call `_merge_nodes_then_upsert`; keep them available until all tests pass with the new path.

## Validation Strategy
1. Unit test asserting `_extract_entities_wrapper` calls `execute_document_batch` exactly once per document.
2. Integration test comparing transaction counters before/after the change on a sample document set.
3. Manual staging run logging transaction counts and overall ingestion time.

## Opinion
The deadlock fix gave us correctness but not the throughput gains we expected, simply because the ingestion flow never started using the batch pipeline. Wiring `DocumentGraphBatch` into `_extract_entities_wrapper` is the minimal surgical change that unlocks the performance work already delivered in `_extraction.py`. Once that foundation is in place we can evaluate chunk tuning or higher-level coordination with real data rather than assumptions.

## References
- Wrapper path still issuing single upserts: `nano_graphrag/graphrag.py:238-308`
- Batch pipeline currently unused: `nano_graphrag/_extraction.py:271-470`
- Neo4j batch helpers and config: `nano_graphrag/_storage/gdb_neo4j.py:420-640`, `nano_graphrag/config.py:152-454`
