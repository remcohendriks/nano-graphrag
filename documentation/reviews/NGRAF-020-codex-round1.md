# NGRAF-020 — Round 1 Review (expert-codex)

## Scope & Diff Summary

- Change category: New Feature (hybrid sparse+dense retrieval with Qdrant)
- Branch: feature/ngraf-020-sparse-dense-hybrid-search
- Commits: d151d18 (feature); baseline from 4957809
- Files changed:
  - M `nano_graphrag/_storage/vdb_qdrant.py` (hybrid collection, hybrid/dense query paths, formatting)
  - A `nano_graphrag/_storage/sparse_embed.py` (SPLADE-based sparse encoding helper)
  - M `requirements.txt` (add transformers, torch)
  - M `docker-compose-api.yml` (enable hybrid env vars)
  - A `tests/test_sparse_embed.py`, `tests/test_qdrant_hybrid.py`
  - A `documentation/reports/NGRAF-020-implementation-round1.md`

## Critical/High Findings

- CODEX-020-001: requirements.txt adds heavy deps unconditionally | High
  - Location: `requirements.txt`
  - Evidence: `transformers>=4.36.0`, `torch>=2.0.0` added as core requirements.
  - Impact: Pulls 1–2GB of wheels and ~1.5GB runtime footprint even when hybrid is disabled; increases cold-start and image size for all users. Many deployments won’t need sparse.
  - Recommendation: Move to optional extra (e.g., `nano-graphrag[hybrid]`) or gate behind environment-based install; document minimal and hybrid footprints. In Docker images, provide a separate “-hybrid” flavor.

- CODEX-020-002: Multi-process model duplication risk | High
  - Location: `nano_graphrag/_storage/sparse_embed.py`
  - Evidence: In-process cache (`_model_cache`) only; uvicorn/gunicorn with multiple workers will load SPLADE once per process (~1.5GB each).
  - Impact: OOM/over-commit risk, especially in containerized production; surprise memory spikes on scale-out.
  - Recommendation: Call out single-worker constraint or document recommended process model (threads) for hybrid; alternatively, support a service/daemonized encoder or an external sparse service in future.

- CODEX-020-003: Configuration split (env-only) | Medium–High
  - Location: `vdb_qdrant.py` and `sparse_embed.py`
  - Evidence: Hybrid toggle and params read via `os.getenv` only; not integrated into `StorageConfig` (despite docker-compose and the ticket doc listing config fields).
  - Impact: Programmatic configuration via `GraphRAGConfig` is not possible; surprising to users who expect config-driven behavior. Harder to test/inject in code.
  - Recommendation: Accept env for quick opt-in, but also read from `global_config` (addon_params or storage section) if present. This mirrors existing patterns and improves testability.

## Medium Findings

- CODEX-020-004: Sparse encoding correctness and performance assumptions | Medium
  - Location: `sparse_embed.py`
  - Evidence: Custom SPLADE-like pipeline with `AutoModelForMaskedLM`, `max_pool` over logits, then `log1p(ReLU)`. Not a faithful reproduction of SPLADE scoring; may be “good enough” but could affect retrieval consistency across models.
  - Impact: Potential mismatch vs. known SPLADE behavior; harder to compare against reference implementations; risk of unexpected sparsity patterns.
  - Recommendation: Note in docs this is a pragmatic sparse encoder; consider swapping to a maintained SPLADE inference wrapper or quantization to reduce memory/latency. Log sparsity stats (non-zero per doc) to monitor anomalies.

- CODEX-020-005: Qdrant version dependency not enforced | Medium
  - Location: `vdb_qdrant.py`
  - Evidence: Uses `Prefetch` + `FusionQuery(RRF)`; requires newer Qdrant server and client.
  - Impact: Runtime errors on older Qdrant installs; unclear failure mode if server < 1.10.
  - Recommendation: Document minimum Qdrant version and add a startup check/log for client/server versions; fail fast with a clear message if hybrid enabled but unsupported.

- CODEX-020-006: Missing sparse index tuning options | Medium
  - Location: `vdb_qdrant.py` collection creation
  - Evidence: Uses `SparseVectorParams()` with defaults; ticket mentions on-disk index and thresholds, but code doesn’t expose them.
  - Impact: Large collections may suffer performance/memory overhead without index tuning.
  - Recommendation: Plumb optional `SPARSE_INDEX_ON_DISK`, `SPARSE_FULL_SCAN_THRESHOLD` (or similar) to match ticket docs; stick to sensible defaults.

## Low Findings

- CODEX-020-007: Logging levels and noise | Low
  - Location: `sparse_embed.py`, `vdb_qdrant.py`
  - Evidence: Info logs on model load are fine, but hybrid fallback warnings could spam under intermittent failures.
  - Impact: Log noise in production.
  - Recommendation: Rate-limit or aggregate warnings; ensure debug logs provide enough detail to diagnose sparse vs dense paths.

- CODEX-020-008: Test realism | Low
  - Location: `tests/test_sparse_embed.py`, `tests/test_qdrant_hybrid.py`
  - Evidence: Heavily mocked; good unit coverage, but no end-to-end against a real Qdrant (gated by `RUN_QDRANT_TESTS`).
  - Impact: Interface drift risk as Qdrant evolves.
  - Recommendation: Keep an optional CI job that runs real Qdrant integration tests periodically (nightly) to catch API changes.

## Positive Observations

- CODEX-GOOD-020-001: Robust fallbacks
  - Hybrid failures gracefully fall back to dense; named-vector fallback is handled.
- CODEX-GOOD-020-002: Sensible isolation
  - Changes confined to Qdrant storage; no cross-cutting impact on other backends.
- CODEX-GOOD-020-003: Clean query refactor
  - Split into `_query_hybrid`, `_query_dense`, and `_format_results` improves readability and maintenance.
- CODEX-GOOD-020-004: Singleton cache + timeout
  - Sparse encoder uses an async lock, caching, batching, timeouts, and empty-embedding fallback — good operational hygiene.
- CODEX-GOOD-020-005: Documentation + tests
  - Implementation report is thorough; tests cover key paths (collection creation, upsert, hybrid query, fallback).

## Conclusion

The hybrid search feature is well-structured and addresses the exact-match retrieval gap. Main risks are deployability (heavy dependencies and per-process memory footprint) and configuration consistency. With minor adjustments — making sparse deps optional, documenting Qdrant version/support, aligning config reads with `StorageConfig`, and exposing basic sparse index knobs — the feature is production-ready and safe to roll out behind an env/config flag.

*** End of Round 1 Review ***
