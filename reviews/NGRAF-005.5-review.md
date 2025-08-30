# NGRAF-005.5 Implementation Review (E2E Health Check)

## Executive Summary
- The developer made strong progress: a manual E2E runner exists, core pipeline assertions are in place, and several real issues were surfaced and partially fixed (entity extraction format, gleaning semantics, clustering robustness, GPT‑5 param mapping).
- However, the current state deviates in several places from the original implementation and the ticket’s “full book” requirement. The health check runner truncates input to 10k chars, artifact checks don’t match actual storage filenames, and there’s a live bug in local query (NoneType from text‑chunk retrieval).
- Risk is manageable, but we should stabilize now: finish the local‑query fix, restore full‑book default, correct artifact assertions, remove debug prints, and explicitly wire LM Studio base_url to avoid accidental calls to OpenAI or embedding endpoint mismatches. Target a predictable <10 min manual run on workstation.

## What Changed (git diff overview)
Files modified since HEAD:
- `nano_graphrag/_op.py`
  - Added extensive debug prints.
  - Local query path: more resilient handling for missing `source_id` on nodes; builds one‑hop text units; but still sorts with `key=lambda x: x["data"]["content"]` without guarding None (root cause of current failure).
  - Entity extraction: now always does an initial extraction pass; gleaning passes are optional; switched parsing from JSON to the delimiter/tuple format actually used by our `entity_extraction` prompt; additional debug logs.
- `nano_graphrag/_storage/gdb_networkx.py`
  - Community schema: tolerate missing `source_id`; fallback to `id`.
  - Map uppercased IDs back to original IDs when writing clusters.
  - Early exits and warnings on empty graph; added debug logging.
- `nano_graphrag/graphrag.py`
  - Wrapped `llm_provider.complete_with_cache` behind `best_model_func`/`cheap_model_func` wrapper so `hashing_kv` works (aligns with the rest of the pipeline).
  - Wrapped embedding provider to return `np.ndarray` and exposed as an `EmbeddingFunc` with attributes.
  - Filtered empty descriptions when upserting entity embeddings; fallback to `name (type)`.
- `nano_graphrag/llm/providers/openai.py`
  - GPT‑5 specific handling: map `max_tokens`→`max_completion_tokens`, set `reasoning_effort=minimal`, default `max_completion_tokens=2000` if omitted, and guard `None` content.
- `nano_graphrag/config.py`
  - Allow `ENTITY_MAX_GLEANING=0` (previously required >=1).
- `tests/health/run_health_check.py` (new)
  - Manual runner that loads `.env` files, uses a temp working dir, truncates input to first 10k chars for speed, checks graph node/edge counts via GraphML parse, exercises global/local/naive queries, and verifies a reload query.
- `tests/health/config_openai.env`, `tests/health/config_lmstudio.env` (new)
  - Tuned parameters for speed; LM Studio mode sets `OPENAI_BASE_URL`.

Notable adds/changes with potential risk:
- Switched extraction parser to delimiter format; this aligns with our prompt but is a substantive behavior change versus JSON parsing.
- OpenAI provider GPT‑5 behavior assumes the client supports `reasoning_effort` and `max_completion_tokens` naming; generally OK, but we should guard non‑GPT‑5 models.
- Added `future>=1.0.0` dependency (unused at the moment).

## Health Check Runner vs Requirements
- Full book requirement: CURRENTLY NOT MET. The runner truncates to the first ~10k chars for speed. We should restore full‑book by default and optionally allow a `--fast` flag for 10k.
- Artifact checks: CURRENTLY INCORRECT. It checks for `full_docs`, `text_chunks`, `community_reports` as paths, but our KV files are `kv_store_full_docs.json`, `kv_store_text_chunks.json`, `kv_store_community_reports.json`. GraphML check is fine.
- Persistence/checking reload: Uses a temporary working dir then tests reload within the same run; good for functional check, but it defeats cross‑run cache validation. For a dev health check, prefer a fixed path (e.g., `./.health/dickens`) with a `--fresh` option when needed.
- Reporting: No JSON report is written to a reports directory; everything is stdout only. Original plan had simple counters persisted. Recommend adding a small `tests/health/reports/latest.json` with timings and counts.

## Current Blocking Issue (Local Query)
- Error: `TypeError: 'NoneType' object is not subscriptable` at `_op.py:821` (`key=lambda x: x["data"]["content"]`).
- Root cause: Some text chunk lookups return `None` (KV miss) and aren’t filtered before token‑budget truncation.
- Proposed fix (minimal):
  - Guard before accessing content: `key=lambda x: x["data"]["content"] if x and x.get("data") else ""`.
  - Also filter out any entries with `v is None or v.get("data") is None` when building `all_text_units`.
- Secondary cause to verify: ensure that all `source_id` chunk IDs inserted during `ainsert` actually match those looked up in `text_chunks_db.get_by_id`. If some graph nodes lack `source_id`, the one‑hop propagation shouldn’t add empty chunk IDs.

## On Potential Drift from Original Implementation
- Wrapping `best_model_func`/`cheap_model_func` and embedding to normalize function signatures is a pragmatic fix; it’s consistent with how the rest of the code uses `hashing_kv` and `EmbeddingFunc`. Acceptable.
- Parsing the entity extraction output as delimiter tuples matches our prompts and removes JSON fragility; this is aligned with the project’s intent.
- Allowing `max_gleaning=0` helps runtime for the health check; default remains 1 so behavior stays intact for other runs.
- GPT‑5 client adjustments are reasonable but couple us to OpenAI client behavior. If issues arise on non‑GPT‑5 models, we should isolate this logic behind model checks (already done) and avoid adding default tokens unconditionally when the caller supplies explicit params.
- Debug prints in core (`print`) should be converted to logger.debug and removed before we call this “done”.

## Recommendations (Stabilization Plan)
1. Fix local query NoneType crash
   - Apply the guard in `_op.py` at the token‑budget truncation and filter Nones earlier.
   - Re‑run health check in both modes.
2. Restore full‑book as default
   - In `run_health_check.py`, remove the 10k truncation by default; add `--fast` to enable truncation when desired.
3. Correct artifact assertions
   - Check for `kv_store_full_docs.json`, `kv_store_text_chunks.json`, `kv_store_community_reports.json`, plus `graph_chunk_entity_relation.graphml`.
4. Persist simple counters
   - Write `tests/health/reports/latest.json` (and timestamped copies) with: nodes, edges, communities, timings for insert + each query, and lengths.
5. Make working dir persistent
   - Default working dir to `./.health/dickens` for cross‑run reuse; add `--fresh` flag to clear it. Keep a `--tmp` option for completely isolated runs.
6. LM Studio base_url robustness
   - The provider currently ignores `config` for base_url. Either:
     - Confirm AsyncOpenAI respects `OPENAI_BASE_URL` env (likely), or
     - Add `base_url` to `LLMConfig` and pass it into `OpenAIProvider` at construction so it’s explicit. Consider a separate base URL for embeddings or keep embeddings on OpenAI in LM Studio mode.
7. Remove debug prints
   - Replace `print` with `logger.debug` and prune noisy logs now that the pipeline is understood.
8. Keep scope tight
   - Avoid more behavior changes while we stabilize. The delimited entity parser and gleaning change are good; hold there and validate end‑to‑end with the full book.

## Status Call
- Insert/Global/Naive: Passing per report; timings are within the target when using truncated input.
- Local: Single blocking bug remains; likely a small guard fix + ensuring consistent chunk IDs.
- Health Check runner: Functionally close, but must revert to full book, correct artifact checks, and persist simple counters. LM Studio base_url should be made explicit to avoid accidental OpenAI calls or embedding endpoint mismatches.

If helpful, I can apply the minimal `_op.py` guard and adjust the runner to default to full book with a `--fast` flag, plus add JSON report output and correct artifact checks.

## Latest Issue Analysis and Guidance (Local Query Crash)

### Root Cause
- The local query expects each graph node’s `source_id` to be a set of text chunk IDs (e.g., `chunk-…`) so it can fetch the corresponding text chunks from `kv_store_text_chunks.json`.
- The current insertion path uses `extract_entities_from_chunks(...)` and then writes graph nodes with `source_id=doc_id` (not chunk IDs). That breaks the local query’s assumption and results in KV misses for text chunks, producing `None` data and the crash at `_op.py:821`.

### What Changed to Trigger This
- A new “simplified” extraction function (`extract_entities_from_chunks`) was introduced to parse delimiter-formatted LLM output (a good improvement), but it does not track chunk provenance.
- In `graphrag.py`, nodes now get `source_id=doc_id` instead of a joined set of chunk IDs.
- The local query path (`_find_most_related_text_unit_from_entities`) still assumes chunk-level `source_id` and calls `text_chunks_db.get_by_id(c_id)`, which fails when given doc IDs.

### Why a Guard Alone Isn’t Enough
- Adding `key=lambda x: x["data"]["content"] if x and x.get("data") else ""` prevents the immediate crash but leaves the pipeline with little/no context because chunk lookups still miss. This would mask the underlying contract violation instead of fixing it.

### Two Viable Fix Paths
- Option A (minimal change; recommended now):
  - In `graphrag.ainsert`, after chunking and upserting text chunks, build a chunk map `{chunk_id: chunk}` and call the original `extract_entities(...)` (not `extract_entities_from_chunks(...)`).
  - That path already propagates chunk-level `source_id` to nodes/edges via `_handle_single_*` and `_merge_*` helpers. Local query will work again with no further structural changes.
  - Keep the new LLM/embedding wrappers; `extract_entities(...)` uses `global_config["best_model_func"]`, which your config already provides.
- Option B (keep the new function; more work):
  - Extend `extract_entities_from_chunks` to compute `chunk_id = compute_mdhash_id(chunk["content"], prefix="chunk-")` and accumulate per-entity/per-relationship chunk IDs during parsing.
  - Return this mapping and set node `source_id` to the joined set of chunk IDs. This preserves the cleaner API but requires code changes and a small interface tweak.

### Concrete Steps (Short Order)
- Fix data semantics:
  - Replace `extract_entities_from_chunks(...)` with `extract_entities(...)` in `graphrag.ainsert`; pass the chunk map and `self._global_config()`.
  - Ensure chunk IDs used for lookup equal those used during upsert (hash of chunk content with `chunk-` prefix).
- Add a small robustness guard:
  - In `_find_most_related_text_unit_from_entities`, filter out entries with `v is None or v.get("data") is None` before sorting/truncation; adjust the warning that checks for missing data accordingly.
- Validate end-to-end:
  - Rerun the health check in OpenAI and LM Studio modes; confirm nodes/edges/communities > 0 and local query > 200 chars without “No context”.
- Clean up:
  - Replace `print` debug lines with `logger.debug` or remove.
  - Default health runner to full book; provide a `--fast` flag for 10k truncation during rapid local iteration.

### Additional Hardening
- Add a quick sanity cross-check in the health runner: count how many `source_id` tokens reference missing chunk IDs. Non‑zero indicates data drift.
- If LM Studio is used for LLM and OpenAI for embeddings, document this explicitly. Avoid leaking `OPENAI_BASE_URL` to embeddings unless you intend to use a local embeddings endpoint.

### Bottom Line
- The failure stems from a semantic mismatch introduced during refactor: graph nodes lost their chunk-level provenance. Restore chunk‑level `source_id` (Option A now), keep a small guard for resilience, clean up logs, and validate with the full book. This stabilizes local query without undoing the other beneficial improvements.
