# NGRAF-022 – Round 1 Review (Debug/Security)

## Summary
Batch infrastructure is in place, but the Neo4j Cypher emitted in `_execute_batch_nodes` is syntactically invalid and will make every document batch fail as soon as APOC code runs.

## Critical Findings
- **CDX-001** – `nano_graphrag/_storage/gdb_neo4j.py:566-583` | Critical | The generated Cypher sets `n.source_id = apoc.coll.toSet(...)[0]`. Cypher does not support list indexing with `[0]`, so the query will throw `Invalid input '['` (or similar) the moment it executes. Because `execute_document_batch` always runs this query, every document transaction will error out, undoing the whole batch. | Replace the `[0]` indexing with a supported expression (e.g., `apoc.text.join(apoc.coll.toSet(...), '{GRAPH_FIELD_SEP}')`) so we store the deduplicated IDs as a string (or persist the array if that’s intended). Add a regression test that runs the Cypher against a real/mocked Neo4j connection to catch syntax errors.

## Positive Notes
- `DocumentGraphBatch` accumulator decouples extraction from persistence, giving us a clean hook for future optimisations.
- NetworkX storage now implements the same `execute_document_batch` contract, keeping backends consistent.

## Recommendation
Fix CDX-001 and re-run the batch tests against a real Neo4j instance (or an integration test) to ensure the query executes as expected. Once the Cypher issue is addressed, the rest of the batch plumbing looks solid.
