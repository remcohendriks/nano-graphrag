# NGRAF-022 – Round 2 Review (Debug/Security)

## Summary
The syntax issue from round 1 is resolved, but the new batch Cypher now double-applies the merge logic: aggregated node/edge data is combined locally _and_ mutated again inside Neo4j, producing duplicate descriptions, source IDs, and inflated weights.

## Critical Findings
- **CDX-002** – `nano_graphrag/_storage/gdb_neo4j.py:568-586` | Critical | `_execute_batch_nodes` already receives node payloads whose `description`/`source_id` fields were merged in `_merge_nodes_for_batch`. The query then does `SET n.description = apoc.text.join([n.description, node.data.description], …)` and recomputes the source-set via APOC, so anything that already contained the existing values gets re-appended, yielding duplicates (e.g. `descA | descB` → `descA | descB | descA | descB`). Impact: persistent data corruption every time an entity is touched post-batch rollout. _Fix_: mirror the old behaviour—simply `SET n += node.data` (or assign individual fields straight from the prepared payload) so the pre-merged values replace the existing ones.

- **CDX-003** – `nano_graphrag/_storage/gdb_neo4j.py:588-617` | Critical | Edge weights/descriptions/source IDs are also pre-aggregated in `_merge_edges_for_batch`. The new Cypher sets `r.weight = COALESCE(r.weight, 0) + edge.weight`, which adds the existing weight again, and re-joins descriptions/source IDs, leading to duplicates. Behaviour diverges from the previous implementation (`SET r += edge_data`). Impact: weights and metadata balloon on every document ingest. _Fix_: assign the prepared values verbatim (`SET r.weight = edge.weight`, `SET r.description = edge.description`, etc.) to keep semantics identical to the legacy path.

## Positive Notes
- APOC call now uses `apoc.text.join(...)` rather than the invalid `[0]` indexing.
- Retry wrapper around `execute_document_batch` provides resilience against transient DB errors.

## Recommendation
Rework `_execute_batch_nodes/_execute_batch_edges` to apply the already-merged payload directly, ensuring the stored state matches the legacy upsert. After that, rerun the batch tests (and ideally a real Neo4j integration check) before merging.
