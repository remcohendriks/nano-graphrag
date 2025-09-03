Debug reviewer ready.

# NGRAF-006 — Decompose _op.py Module (Round 2)

I reviewed the Round 2 implementation and the developer’s report (documentation/reports/NGRAF-006-round2-report.md). This pass validates the fixes from Round 1, checks for regressions, and surfaces any remaining defects from a debugging and security perspective.

## Summary
- Underscore-prefixed internal modules created and wired: `_chunking.py`, `_extraction.py`, `_community.py`, `_query.py`.
- `_op.py` remains as a compatibility shim with deprecation warning and includes a non‑breaking alias for the separator function typo.
- Round 1 criticals addressed: mutable default args and None edge handling are fixed; gleaning accumulation implemented in the side‑effect‑free extraction path; template variable mismatch corrected.
- Tests updated to match new module names; expectations adjusted for comma+tab CSV.

Overall structure and correctness improved. A few non‑blocking bugs and one important API mismatch remain.

## Critical Issues
None found that block merge for Round 2. See high‑priority items below that affect extraction quality.

## High Priority Issues

- History parameter mismatch in production extraction (conversation lost)
  - File: `nano_graphrag/_extraction.py`
  - Lines: 234–247 (calls to `use_llm_func(..., history_messages=history)`)
  - Problem: The GraphRAG wrappers use `history` (not `history_messages`) for conversation context, and the provider interface is `complete_with_cache(prompt, system_prompt, history, ...)`. Passing `history_messages` as a keyword means the history is ignored by providers, so gleaning and control prompts (“continue”, “if_loop”) don’t benefit from prior turns.
  - Impact: Lower extraction quality and inconsistent gleaning behavior compared to the intended conversational loop.
  - Fix (minimal): Rename the keyword to `history` in both gleaning calls.
    ```python
    glean_result = await use_llm_func(continue_prompt, history=history)
    if_loop_result: str = await use_llm_func(if_loop_prompt, history=history)
    ```
  - Note: The compatibility helpers in `llm/providers/openai.py` do accept `history_messages`, but GraphRAG’s configured provider path does not use them.

- Chunk ID collision semantics remain ambiguous
  - Files: `nano_graphrag/_chunking.py` (get_chunks), `nano_graphrag/graphrag.py` (upserts)
  - Problem: Chunk IDs are `md5(content)` only. Identical chunks across different documents will collide and overwrite `doc_id` on upsert.
  - Recommendation: Decide policy:
    - Dedup across docs: maintain a set/CSV of `doc_id`s when merging.
    - Keep per‑doc identity: seed hash with `doc_id` (e.g., `md5(f"{doc_id}::{content}")`).

- BaseGraphStorage contract vs usage mismatch (type safety)
  - File: `nano_graphrag/base.py` declares `get_nodes_batch(...) -> dict[...]`.
  - Usage: Call sites treat it as `list` (e.g., `_query._build_local_query_context`, `_query._find_most_related_text_unit_from_entities`).
  - Risk: Provider implementations may return dict vs list leading to subtle bugs; static typing cannot protect these paths.
  - Recommendation: Standardize the return type to a list and update annotation + implementations, or adapt usages to support dict reliably.

## Medium Priority Suggestions

- Incorrect None‑check for fetched chunks
  - File: `nano_graphrag/_query.py`
  - Lines: ~68–90 area after building `all_text_units_lookup`
  - Issue: `if any([v is None for v in all_text_units_lookup.values()]): ...` will never be True because `v` is a dict; the intent was to check `v["data"]`.
  - Fix:
    ```python
    if any(v.get("data") is None for v in all_text_units_lookup.values()):
        logger.warning("Text chunks are missing, maybe the storage is damaged")
    ```

- Performance: batch node fetch where possible
  - File: `nano_graphrag/graphrag.py` (entity embedding update loop)
  - Issue: Still fetching nodes one‑by‑one in a loop; consider batch method or limited concurrency if backend supports it.

- Logging polish
  - File: `nano_graphrag/_query.py`
  - Minor: Log message typo “entites”; consider elevating certain anomalies to `warning` with identifiers (e.g., missing node IDs) for easier triage.

## Low Priority Notes
- Internal modules underscore prefix now matches ticket — good. Keep `_op.py` alias note in docs for legacy users.
- Comments standardized to English in updated areas; a few Chinese comments remain in `_query.py` (“传入 wrapper”). Low severity.
- `get_chunks_v2` remains `async` while CPU‑bound; acceptable for symmetry with other async APIs.

## Positives
- Mutable default dicts eliminated in `_community._pack_single_community_describe` — prevents state leakage.
- None edge‑handling fixed in `summarize_community` — avoids TypeError.
- Prompt template variable corrected to `input_text` for community summaries.
- Separator function typo fixed with a safe alias in `_op.py`.
- Gleaning accumulation added to `extract_entities_from_chunks` — better coverage of responses.
- Tests updated to reflect new module names and CSV delimiter; good coverage of key paths.

## Concrete Repro Steps

1) Conversational history not applied during extraction gleaning
   - Setup: Configure GraphRAG normally (provider path through `llm_provider.complete_with_cache`).
   - Exercise: Run `extract_entities(...)` with `entity_extract_max_gleaning > 0`.
   - Observe: Provider receives no `history` (keyword mismatch), so gleaning prompts lack prior context.
   - Fix: Use `history=` keyword as described above.

2) Chunk collision overwrite
   - Insert two docs that share identical paragraphs.
   - Observe: Same chunk content produces same ID; later upsert overwrites `doc_id` in KV/vector store.
   - Fix: Include `doc_id` in hash, or aggregate `doc_id`s when deduping.

3) Missing chunk warning never triggers
   - Mock `text_chunks_db.get_by_id` to return `None` for one ID.
   - Observe: Condition `v is None` is never True; no warning emitted.
   - Fix: Check `v.get("data") is None` instead.

## Conclusion

Round 2 substantially improves stability and aligns tightly with the ticket. The remaining items are straightforward to fix without broad refactors. I recommend merging after addressing the `history` keyword mismatch in extraction and planning a small follow‑up to resolve chunk ID policy and the `get_nodes_batch` type contract.

