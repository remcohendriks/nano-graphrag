# NGRAF-011 — Codex Round 3 Review

Author: Codex
Date: Current branch head

## Summary
- Status: Green — Qdrant integration is production‑ready.
- Focus of round3: stability and operability after extensive debugging. Client lifecycle, embedding generation, and result formatting were tightened; health runs pass end‑to‑end with the Qdrant backend.

## Verified Round 3 Changes
- Client lifecycle: Deferred `AsyncQdrantClient` creation with `_get_client()`, early capture of `qdrant_client.models` for predictable collection creation.
- Collection handling: `_ensure_collection()` checks/creates through a retrieved client with clear logs.
- Embeddings: Upsert now batches generation for items missing embeddings (one batched call), replacing per‑item calls.
- IDs & payloads: Stable IDs via `xxhash.xxh64_intdigest`; payload includes original string `id` and coerces vectors to plain lists.
- Query results: Include `id`, `content`, and `score`, preserving payload fields (compatible with local query path).
- Instrumentation: GraphRAG insert path logs key phases to speed debugging.

## Health Evidence
- File: `tests/health/reports/latest.json` (latest entry)
  - Provider/model: OpenAI `gpt-5-mini`
  - Storage: `vector_backend=qdrant`, `graph_backend=networkx`, `kv_backend=json`, `qdrant_url=http://localhost:6333`
  - Status: passed
  - Timings (s): insert 208.02, global 25.80, local 12.90, naive 9.73, reload 7.66, total 264.61
  - Counts: nodes 83, edges 99, communities 18, chunks 14
- Interpretation: Full pipeline with Qdrant is stable; timings are reasonable for remote VDB + LLM flow.

## Conformance Checklist
- Factory/register: `qdrant` allowed and registered — OK
- Config propagation: `qdrant_url`, `qdrant_api_key`, `qdrant_collection_params` in `to_dict()` — OK
- Optional deps: `qdrant_client` in `check_optional_dependencies()` — OK
- Examples/docs: Config‑first Qdrant example corrected; health docs include Qdrant — OK
- Tests: Unit tests validate deterministic IDs and result format; health E2E passed — OK

## Non‑Blocking Suggestions
- Upsert batch size: Make configurable (e.g., `qdrant_batch_size`) or reuse `embedding_batch_num` for symmetry.
- Dependency hint: Update `ensure_dependency` messaging to recommend `pip install nano-graphrag[qdrant]` (instead of `[all]`).
- Docs polish: Update `CLAUDE.md` to mark Qdrant as Built‑in with a short config snippet.
- Optional: add a quick connection probe at init with actionable error guidance.

## Risks & Notes
- Legacy data: Collections created with prior Python `hash()` IDs won’t deduplicate under stable IDs; recommend reindex/migration if applicable.
- External dependency: Requires a reachable Qdrant service (health docs provide Docker guidance).

## Viability
- Rating: Green — ready to merge. Consider a small 011.2 ticket for the batch size setting + dependency hint + CLAUDE.md update.
