Debug reviewer ready.

# NGRAF-006 — Decompose _op.py Module

This review covers all changes on the current branch versus `main`, evaluates compliance with ticket NGRAF-006, and highlights defects, risks, and improvement opportunities from a debugging and security perspective.

## Scope Adherence
- Module decomposition completed: `_op.py` now re-exports from dedicated modules: `chunking.py`, `extraction.py`, `community.py`, `query.py`.
- Backward compatibility preserved via `_op.py` re-exports and a deprecation warning.
- Divergence from ticket naming: spec proposed private modules (`_chunking.py`, etc.). Implementation used public names. Functional impact is low but update docs/references accordingly.
- “Extract without changes”: Core logic of the original functions appears preserved. New helper APIs were added (e.g., `get_chunks_v2`, `extract_entities_from_chunks`, `summarize_community`) which is acceptable if kept non-breaking.

## Summary of Changes Reviewed
- New modules: `nano_graphrag/chunking.py`, `nano_graphrag/extraction.py`, `nano_graphrag/community.py`, `nano_graphrag/query.py`.
- Compatibility layer: `nano_graphrag/_op.py` now only imports and warns.
- Orchestrator update: `nano_graphrag/graphrag.py` imports from new modules.
- Tests added: `tests/test_chunking.py`, `tests/test_extraction.py`, `tests/test_community.py`, `tests/test_query.py`.
- Documentation reorganized; experts guides added and tickets moved under `documentation/tickets/`.

## Critical Issues (must fix before merge)

- community.py: Mutable default arguments leak state
  - File: `nano_graphrag/community.py`, lines 73–75
  - Issue: `already_reports: dict[str, CommunitySchema] = {}` and `global_config: dict = {}` are mutable defaults. This can lead to cross-call state leakage and non-deterministic behavior.
  - Risk: Hard-to-reproduce bugs, surprising accumulation between calls.
  - Fix:
    ```python
    async def _pack_single_community_describe(...,
        already_reports: dict[str, CommunitySchema] | None = None,
        global_config: dict | None = None,
    ) -> str:
        already_reports = already_reports or {}
        global_config = global_config or {}
    ```

- community.py: Possible None handling bug when fetching edges
  - File: `nano_graphrag/community.py`, lines 333–340
  - Issue: `edges = await graph.get_node_edges(node_id)` may return `None`; subsequently `edges_data.extend(edges)` will raise `TypeError`.
  - Repro: Mock `get_node_edges` to return `None`; call `summarize_community`. Expected crash.
  - Fix:
    ```python
    edges = await graph.get_node_edges(node_id)
    if edges:
        edges_data.extend(edges)
    ```

## High Priority Issues (should fix soon)

- extraction.py: Gleaning implementation in `extract_entities_from_chunks` overwrites instead of accumulates
  - File: `nano_graphrag/extraction.py`, lines ~376–388
  - Issue: Additional gleaning passes set `input_text` to the prior response and overwrite `response` instead of appending or maintaining conversation history. This loses earlier extractions.
  - Test reflects this unexpected behavior: `tests/test_extraction.py::test_extract_with_gleaning` asserts the “last response wins”. That test outcome is a smell rather than a requirement.
  - Recommendation: Align gleaning with the production path in `extract_entities` by maintaining history and concatenating gleaned results.
    - Minimal change: append to `response` instead of reassigning; parse at the end.
    - Better: reuse the conversational pattern with `pack_user_ass_to_openai_messages` and `entiti_continue_extraction` like in `extract_entities`.

- graphrag.py: Potential performance bottleneck fetching nodes individually
  - File: `nano_graphrag/graphrag.py`, lines ~286–318
  - Issue: `get_node` is called in a loop instead of using a batch fetch. On large graphs this could be slow.
  - Mitigation: If the graph backend exposes `get_nodes_batch`, prefer it; otherwise consider chunked concurrent fetches with rate-limiting.

- Chunk ID collisions across documents (pre-existing behavior, worth revisiting)
  - Files: `nano_graphrag/chunking.py` lines 82–86 and usages in `graphrag.py`
  - Issue: Chunk IDs are `md5(content)` only. Identical chunks across different docs collide, overriding `doc_id` on upsert.
  - Recommendation: If deduplication is not intentional, include `doc_id` in the hash seed. If dedup is intentional, ensure the merged record safely preserves all `doc_id`s.

## Medium Priority Suggestions (improvements)

- Naming consistency: `chunking_by_seperators` typo
  - File: `nano_graphrag/chunking.py` line 40; also re-exported in `_op.py` and used in tests.
  - Suggestion: Add a non-breaking alias `chunking_by_separators = chunking_by_seperators` and migrate references over time.

- Robustness: `summarize_community` JSON parsing
  - File: `nano_graphrag/community.py`, lines 361–373
  - Suggestion: Catch and log `JSONDecodeError` specifically; include more context in logs.

- Logging and observability
  - Several key paths log at `debug`. Consider promoting critical data-path anomalies (e.g., missing nodes/chunks) to `warning` consistently, and include identifiers to aid triage.

- Type clarity and return types
  - The project uses `TypedDict` for `TextChunkSchema`. Where feasible, annotate function returns explicitly (e.g., `get_chunks` returns `dict[str, TextChunkSchema]`) to improve static analysis.

## Low Priority Notes (nice to have)

- Ticket vs. implementation module names differ (`_chunking.py` vs `chunking.py`). No functional harm, but align docs or rename if private intent matters.
- `get_chunks_v2` is `async` while purely CPU-bound. Either remove `async` or leave as-is for API consistency.
- Some inline comments are in Chinese; consider standardizing to English for broader collaboration if that’s your team’s norm.

## Positive Observations

- Backward compatibility: `_op.py` re-exports and deprecation warning are cleanly implemented.
- Separation of concerns: Logical grouping across `chunking`, `extraction`, `community`, `query` is clear and maintains the original flow.
- Rate limiting and caching: `GraphRAG` wraps providers with concurrency limits and hashing KV; good resource control.
- Tests: New module-level tests improve coverage and provide mocks for LLM/graph interactions.
- Tokenizer abstraction: `TokenizerWrapper.decode_batch` addition simplifies and accelerates decoding.

## Concrete Reproductions

1) None edges crash in `summarize_community`
   - Setup: Mock `graph.get_node_edges` to return `None` for any node.
   - Call: `await summarize_community(["node1"], graph, mock_llm)`
   - Expected: `TypeError: 'NoneType' object is not iterable` at `edges_data.extend(edges)`.
   - Fix: Guard `if edges:` before extending.

2) Gleaning overwrite in `extract_entities_from_chunks`
   - Current test already demonstrates last-pass overwrite.
   - Risk: Entity loss if gleaning produces complementary outputs.
   - Fix: Accumulate results or maintain conversation history like `extract_entities`.

3) Potential chunk ID collisions across documents
   - Insert two docs with identical paragraphs; chunking produces identical chunk content.
   - Later upserts overwrite earlier chunk’s `doc_id`.
   - Decide intent: dedup (then aggregate `doc_id`s) vs. per-doc identity (then hash content + doc_id).

## Suggested Fix Snippets

- Mutable default arguments
  ```python
  # nano_graphrag/community.py
  async def _pack_single_community_describe(...,
      already_reports: dict[str, CommunitySchema] | None = None,
      global_config: dict | None = None,
  ) -> str:
      already_reports = already_reports or {}
      global_config = global_config or {}
  ```

- Safer edges accumulation
  ```python
  # nano_graphrag/community.py
  edges = await graph.get_node_edges(node_id)
  if edges:
      edges_data.extend(edges)
  ```

- Accumulative gleaning (pattern)
  ```python
  # nano_graphrag/extraction.py in extract_entities_from_chunks
  response = await model_func(entity_extract_prompt.format(**context))
  for _ in range(max_gleaning):
      extra = await model_func(PROMPTS["entiti_continue_extraction"].format(**context))
      response = f"{response}\n{extra}"
  # parse combined response
  ```

## Security & Reliability Considerations

- Concurrency: LLM and embedding calls are rate-limited, which reduces the risk of provider throttling and improves stability.
- Input handling: Many code paths trust LLM output formats. Parsing is defensive but consider bounding per-call outputs and validating critical fields.
- Storage consistency: Review deduplication semantics for chunks to avoid silent data loss across documents.

## Conclusion

Overall, the decomposition aligns with the ticket’s intent and keeps behavior stable. Address the critical issues (mutable defaults, `None` edge handling) before merge, and consider the high-priority adjustments (gleaning accumulation, chunk ID semantics) soon after. The new structure is a solid foundation for further cleanups (type hints, explicit params) in Phase 2.

