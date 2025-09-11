# NGRAF-011 — Qdrant First‑Class Integration (Round 1 Review)

Author: Codex
Date: Current branch head

## Summary
- Status: Partially compliant with NGRAF‑011; not yet merge‑ready.
- Highlights:
  - Qdrant backend implemented: `nano_graphrag/_storage/vdb_qdrant.py` using `AsyncQdrantClient`.
  - Factory integration present: `ALLOWED_VECTOR` includes `qdrant`; registration added in `_register_backends()`.
  - StorageConfig extended for Qdrant; extras entry added in `setup.py`; readme updated; example + tests added.
- Blockers:
  - Qdrant config values are not propagated to storages (missing in `GraphRAGConfig.to_dict()`), so defaults are always used.
  - Non‑deterministic point IDs via Python `hash()`; this causes duplicates across runs/processes.
  - Example uses the new API incorrectly (wrong config placement; wrong `aquery` signature).
- Majors:
  - Upsert computes embeddings per item, no batching; vectors not coerced to lists.

## Scope Verification vs Ticket
- Factory
  - Pass: `StorageFactory.ALLOWED_VECTOR` includes `"qdrant"`; `_register_backends()` registers the loader.
  - Missing: Factory test asserting `create_vector_storage("qdrant", ...)` yields `QdrantVectorStorage`.
- Config
  - Pass: `StorageConfig` adds `qdrant_url`, `qdrant_api_key`, `qdrant_collection_params` (and wired in `from_env`).
  - Blocker: `GraphRAGConfig.to_dict()` omits these, so storages don’t receive user settings.
- Storage Implementation
  - Pass: Optional dep gating via `ensure_dependency("qdrant_client", ...)`.
  - Issues: Unstable IDs; per‑item embedding; missing `.tolist()` conversions; no batching via `embedding_batch_num`.
- Examples/Docs
  - Added `examples/storage_qdrant_config.py` and readme extras/components table entries.
  - Issues: Example sets `working_dir` on `GraphRAGConfig` instead of `StorageConfig`; calls `aquery(query, mode="local")` instead of `param=QueryParam(mode="local")`.
  - `CLAUDE.md` still claims Qdrant is “via examples” (now outdated).
- Tests
  - Good mocked unit tests for vdb_qdrant.
  - Missing factory path and GraphRAG smoke tests for the qdrant code path.

## Detailed Findings
1) Config propagation (Blocker)
- File: `nano_graphrag/config.py`
- Problem: `GraphRAGConfig.to_dict()` does not include `qdrant_url`, `qdrant_api_key`, `qdrant_collection_params`.
- Effect: `QdrantVectorStorage` always uses defaults (e.g., `http://localhost:6333`).
- Fix: Add these fields into `to_dict()` so `_init_storage()` passes them to storages.

2) Non‑deterministic vector IDs (Blocker)
- File: `nano_graphrag/_storage/vdb_qdrant.py`
- Code: `point_id = abs(hash(content_key)) % (10 ** 15)`
- Problem: Python `hash()` is salted per process; IDs change across runs.
- Effect: Duplicate points and index bloat.
- Fix: Use stable hashing (e.g., `xxhash.xxh32_intdigest(key.encode())`) or md5/sha1.

3) Missing batching + list coercion (Major)
- File: `nano_graphrag/_storage/vdb_qdrant.py`
- Problem: Upsert computes an embedding per item; vectors not coerced with `.tolist()`.
- Effect: Poor performance; potential type mismatches.
- Fix: Batch embeddings using `embedding_batch_num` from config; convert vectors for both upsert and query.

4) Example correctness (Major)
- File: `examples/storage_qdrant_config.py`
- Problems:
  - `working_dir` must be `StorageConfig(working_dir=...)`.
  - `aquery` requires `param=QueryParam(mode="local")`.
- Effect: Example fails at runtime; confuses users.
- Fix: Move `working_dir`; pass `QueryParam`.

5) Optional dependency enumeration (Minor)
- File: `nano_graphrag/_utils.py`
- Problem: `check_optional_dependencies()` omits Qdrant.
- Fix: Add `"qdrant_client": "qdrant-client"` mapping.

6) Docs drift (Minor)
- Files: `CLAUDE.md`, `readme.md`
- Problem: Qdrant listed as “via examples” in `CLAUDE.md`; fix to Built‑in; correct example code.

7) Test coverage gaps (Minor)
- Add: Factory test for `qdrant`; GraphRAG smoke ensuring `entities_vdb` is Qdrant when configured.

## Security & Reliability
- No API keys logged; OK. Avoid including auth in logs if URLs embed tokens.
- Unstable IDs risk storage bloat; must fix before merging.

## Performance
- Per‑item embeddings are a bottleneck; batch to align with other vector stores.
- Consider documenting recommended Qdrant collection params (e.g., HNSW settings) via `qdrant_collection_params`.

## Backward Compatibility
- No breaking API changes; consistent with NGRAF‑006…010 factory/config patterns.
- Ensure result payloads include fields (`entity_name`, `entity_type`) used by `_query.py` when relevant.

## Viability
- Rating: Yellow — close to ready once blockers are addressed.

## Recommended Fix List (Priority)
1) Propagate Qdrant config in `GraphRAGConfig.to_dict()`.
2) Replace `hash()` with a stable hash for point IDs.
3) Batch embeddings and `.tolist()` vectors for upsert/query.
4) Fix `examples/storage_qdrant_config.py` (config + `QueryParam`).
5) Add `qdrant_client` to `_utils.check_optional_dependencies()`; optionally update `ensure_dependency()` message to suggest `pip install nano-graphrag[qdrant]`.
6) Add factory + GraphRAG smoke tests for the qdrant path.

## What’s Good
- Clean factory registration and packaging extras.
- Solid mocked unit tests asserting format and async behavior.
- Readme extras and components table updated.

I’m happy to re‑review a round2 addressing the above.
