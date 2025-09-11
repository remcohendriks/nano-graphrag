# Expert Review Lens — Codex (Round 1)

This document outlines the evaluation approach I used to review NGRAF‑011 (Qdrant first‑class integration) and similar storage/provider tickets in this repo. It serves as a repeatable checklist and rationale for recommendations.

## Review Focus
- Config correctness: Storage settings live in `GraphRAGConfig/StorageConfig`; values must propagate into storages via `to_dict()` and factory calls.
- Factory integration: Backends are registered lazily, constrained by `ALLOWED_*` sets, and instantiated via `StorageFactory.create_*` methods.
- Optional deps and lazy imports: Heavy deps should be gated by `ensure_dependency()` and not imported at module import time.
- API shape consistency: Vector storage upsert/query payloads must match how `_query.py` consumes results (e.g., `entity_name` in payload for entity graph lookups).
- Deterministic identifiers: Use stable hashing (e.g., `xxhash`) for vector IDs to avoid duplicate inserts across runs.
- Performance: Batch embeddings using `embedding_batch_num`; avoid per‑item embedding calls.
- Tests: Prefer hermetic unit tests with mocks (skip integration if dependency/server not present). Confirm factory + config code paths are exercised.
- Docs: Examples should use the new config‑first API; `readme.md`/`CLAUDE.md` must align with supported components.

## Quick Checklist
- Config
  - StorageConfig adds backend parameters and `from_env()` wiring
  - GraphRAGConfig.to_dict includes backend‑specific values
- Factory
  - `ALLOWED_VECTOR/GRAPH/KV` updated
  - `_register_backends()` registers loader lazily
- Storage impl
  - Uses `ensure_dependency()` for optional deps
  - Deterministic IDs (xxhash/md5), no Python `hash()`
  - Batching embeddings (uses `embedding_batch_num`)
  - Returns result payload incl. fields `_query.py` expects
- Tests
  - Unit tests mock client and validate formatting/IDs/batching
  - Integration tests are optional/skip‑first
- Docs/Examples
  - Example uses `GraphRAGConfig(StorageConfig(...))` (no legacy kwargs)
  - `readme.md` components + install extras updated
  - `CLAUDE.md` reflects first‑class support

## Typical Failure Modes Caught
- Config values not passed to storage (missing in `to_dict()`)
- Non‑deterministic vector IDs (Python `hash()`)
- Per‑item embedding calls (no batching)
- Example code calling `GraphRAG.aquery(..., mode="local")` instead of `param=QueryParam(mode="local")`
- Optional dependency not listed in `check_optional_dependencies()`
- Docs drift (readme/CLAUDE out of sync with code)

Adhering to these checks keeps new backends consistent with the codebase’s patterns introduced by NGRAF‑006…010 and reduces surprises for users and CI.
