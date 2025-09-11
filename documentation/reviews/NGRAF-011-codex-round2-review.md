# NGRAF-011 — Codex Round 2 Review

Author: Codex
Date: Current branch head

## Summary
- Status: Green — ready to merge; prior blockers fixed.
- Verified fixes:
  - Deterministic IDs via `xxhash.xxh64_intdigest`.
  - Qdrant config (`qdrant_url`, `qdrant_api_key`, `qdrant_collection_params`) now propagates through `GraphRAGConfig.to_dict()`.
  - Embedding/vector coercion to plain lists in upsert and query paths.
  - Example corrected (config placement under `StorageConfig`; `QueryParam` usage).
  - Optional dependency check includes `qdrant_client`.
  - Unit tests assert ID determinism and query result format; health docs added for E2E.

## Remaining Suggestions (Non‑blocking)
- Embedding batching: During upsert, compute embeddings in batches using `global_config["embedding_batch_num"]` for parity with HNSW.
- Configurable upsert batch size: Expose a setting (e.g., `qdrant_batch_size`) or reuse `embedding_batch_num`.
- Dependency hint: Adjust `ensure_dependency` message to suggest `pip install nano-graphrag[qdrant]` (instead of `[all]`).
- Factory/GraphRAG smoke tests: Add a factory path test for `"qdrant"` and a GraphRAG init smoke to lock in the integration.

## Verification Notes
- Config propagation present in `nano_graphrag/config.py` (Qdrant fields appended when backend is `qdrant`).
- Storage `nano_graphrag/_storage/vdb_qdrant.py`:
  - Deterministic ID, list conversion, batched Qdrant upserts, and compatible search formatting.
- Example `examples/storage_qdrant_config.py` now uses the config‑first API and correct `QueryParam`.
- Tests in `tests/storage/test_qdrant_storage.py` validate ID determinism and result shape; `tests/health` documents E2E.

## Viability
- Rating: Green. Merge is safe; batching/config polish can follow as a small enhancement.
