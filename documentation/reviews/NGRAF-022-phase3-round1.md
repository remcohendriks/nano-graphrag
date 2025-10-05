# Review: NGRAF-022 Phase 3 Round 1

## Findings (blocking)

1. `has_vector` is forced to `True` before Qdrant upsert
   - File: `nano_graphrag/_extraction.py:166`
   - Issue: `_merge_nodes_for_batch` now returns `has_vector = existing_has_vector or True`, which always resolves to `True` for every merged entity. Graph nodes are written with `has_vector=True` even before the Qdrant write succeeds. If `entity_vdb.upsert()` fails, the graph retains `has_vector=True` while the vector is missing, and the following community run will hit the same 404 the flag was meant to prevent. The flag can no longer differentiate placeholders from indexed entities.
   - Fix: Leave the flag `False` until the post-upsert sync runs; e.g. `has_vector = existing_has_vector` and only upgrade to `True` after the successful Qdrant batch (or when merging with an existing `True` node).

2. `batch_update_node_field` never matches the intended nodes
   - File: `nano_graphrag/_extraction.py:487-489`
   - Issue: The update call is fed `entity_ids = list(data_for_vdb.keys())`, i.e. the hashed `ent-…` values. Neo4j nodes are keyed by the original entity name (e.g. `SECRETARY OF TREASURY`), so the `MATCH (n:{namespace} {id: node_id})` clause in `batch_update_node_field` matches zero rows. The flag never flips to `True` as intended, leaving real entities indistinguishable from placeholders.
   - Fix: Pass the actual graph node IDs. e.g. keep a parallel list of `dp["entity_name"]` and update those, or store the computed `entity_id` on the node before the Neo4j batch executes and reuse it later.

## Findings (non-blocking)

3. New integration test calls `_merge_edges_for_batch` with the wrong argument order
   - File: `tests/storage/integration/test_vector_consistency.py:64`
   - Detail: The helper signature is `(..., graph_storage, global_config, tokenizer, batch)`, but the test passes `batch` in the `graph_storage` slot. The test will raise if the skip markers are removed. Swap the arguments so the test exercises the intended path.

## Suggested next steps
- Rework the `has_vector` lifecycle so it remains `False` until a successful Qdrant write, and ensure the Neo4j sync targets the correct node IDs.
- After fixing the flag flow, rerun the new tests and confirm the community pass metrics reflect the expected skip counts.
