# NGRAF-020-2 – Round 6 Code Review

## High Findings
- [PO-001]: nano_graphrag/graphrag.py:523-554 | High | Product owner reports the `sparse` embedding vector disappears during community-generated re-upserts, while `sparse_name` persists. Diagnosis shows the fallback path rebuilds entities with `"content": description`, unlike the initial insert (`"content": "{name} {description}"`), so the SPLADE service receives name-less text and emits empty `sparse` vectors. | Align the fallback upsert payload with the initial ingestion (include entity name in `content`) to maintain SPLADE signal, then re-run hybrid search tests to confirm both sparse channels survive.

## Notes
- Finding raised directly by product owner; resolve before sign-off.
