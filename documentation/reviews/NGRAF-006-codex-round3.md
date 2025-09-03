Debug reviewer ready.

# NGRAF-006 — Decompose _op.py Module (Round 3)

This round re-reviews the code after the developer’s Round 3 changes and validates the fixes claimed in documentation/reports/NGRAF-006-round3-report.md.

## Summary
- All Round 2 high‑priority items are implemented correctly: conversation history now flows to gleaning, chunk IDs avoid cross‑document collisions, and the incorrect None‑check in query code is fixed.
- Base graph storage type contracts were aligned to actual usage, reducing risk of subtle bugs.
- Minor logging/comment polish landed as described.
- I see no production‑blocking issues remaining. Merge looks good.

## Critical Issues
- None found. Previous criticals are fixed.

## High Priority Issues
- None remaining from Round 2. The notable items were addressed:
  - History keyword corrected to `history` in `_extraction.extract_entities` gleaning loop.
  - Chunk ID policy updated to per‑document identity in both `_chunking.get_chunks` and `graphrag.GraphRAG.ainsert` paths.
  - Incorrect None‑check in `_query._find_most_related_text_unit_from_entities` now checks `v.get("data") is None`.
  - Base graph storage `get_nodes_batch` contract now returns a list matching call sites; backends updated accordingly.

## Medium Priority Suggestions
- Type hint nit: `BaseGraphStorage.node_degrees_batch` return type is declared as `List[str]` in `base.py`, but the implementation and usages are numeric degrees. Consider changing to `List[int]` to match behavior and improve static checking.
- Performance: Where backends support it, consider batch node fetches in `graphrag._generate_community_reports` instead of looping one‑by‑one. This is not a blocker.

## Low Priority Notes
- Good job keeping the legacy alias `chunking_by_seperators` in `_op.py` while moving canonical usage to `chunking_by_separators`.
- Comments standardized to English in updated modules; consistent logging copy.

## Positive Observations
- Backward compatibility layer remains clean and explicit with deprecation messaging.
- Clear modular separation improves readability and testability.
- History propagation fix materially improves extraction quality during gleaning.
- Chunk ID collision fix prevents subtle data integrity issues across documents.
- Storage interface alignment reduces the chance of runtime surprises across backends.

## Verification Notes
- Verified `history` keyword usage in `_extraction.py` gleaning loop.
- Verified chunk hashing includes `doc_id` in `_chunking.get_chunks` and in all `GraphRAG.ainsert` chunk ID paths.
- Verified corrected None‑check and improved log message in `_query.py`.
- Verified `BaseGraphStorage.get_nodes_batch` now returns a list and backends (`_storage/gdb_neo4j.py`, `_storage/gdb_networkx.py`) conform.

## Recommendation
Approved to merge. The remaining items are minor polish and can be handled in a follow‑up (type hint for `node_degrees_batch`; optional batching perf tweak).

