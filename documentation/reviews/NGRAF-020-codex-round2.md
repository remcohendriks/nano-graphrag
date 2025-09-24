# NGRAF-020 — Round 2 Review (expert-codex)

## Scope & Changes Reviewed

- Feature branch: `feature/ngraf-020-sparse-dense-hybrid-search`
- Round 2 report: documentation/reports/NGRAF-020-implementation-round2.md
- Focus: Address Round 1 issues (deps, config, memory, Qdrant version, tests)

## Resolved From Round 1

- CODEX-020-001 (heavy deps unconditional): Addressed
  - Optionalize transformers/torch via setup extras; requirements comment notes optionality.
- CODEX-020-003 (env-only config): Addressed
  - Introduces HybridSearchConfig; usage examples show config-first with env as override.
- CODEX-020-002 (per-process model duplication): Partially mitigated
  - LRU cache within process; added GPU device control. Still one model per worker process (documented; acceptable for now).
- CODEX-020-005 (Qdrant version dependency): Addressed
  - Adds explicit version warning when < 1.10.
- CODEX-020-006 (sparse index knobs): Addressed in design/README
  - Report mentions on-disk/thresholds; verify vdb_qdrant exposes them in collection params for large deployments.

## High Priority Notes

- CODEX-020-R2-001: Confirm config plumbed through runtime path | High
  - The report describes HybridSearchConfig and config-based provider, but the current diffs still show env reads in `vdb_qdrant.py`/`sparse_embed.py` in Round 1 code. Ensure the actual branch code now sources toggles/params from `GraphRAGConfig` (global_config/addon_params) with env as fallback.
  - Impact: Without this, programmatic control remains inconsistent; tests/docs may pass but integration won’t honor config flags.
  - Recommendation: Verify that `QdrantVectorStorage` reads hybrid settings from storage/global_config first, then env. Add a quick assertion in tests that config object alone (no env) enables hybrid.

- CODEX-020-R2-002: Multi-worker guidance | High
  - Even with LRU, each worker loads its own model. Document recommended process model (single worker + threads) or memory budgets per worker; add a guardrail log warning when `enabled=True` and workers>1.

## Medium Priority Notes

- CODEX-020-R2-003: Sparse encoder fidelity & observability | Medium
  - The custom SPLADE-like logic is pragmatic. Add a brief note in README that it’s an approximation and log sparsity stats (mean non-zeros per doc) at DEBUG to detect regressions.

- CODEX-020-R2-004: Fusion parameters surfaced | Medium
  - Report mentions configurable RRF-k; verify this is truly plumbed to the Qdrant fusion call and defaults are sensible.

- CODEX-020-R2-005: Real Qdrant E2E in CI (optional) | Medium
  - Keep an opt-in job to run integration against a real Qdrant (nightly) to catch API/behavior changes.

## Low Priority

- CODEX-020-R2-006: Logging hygiene | Low
  - Hybrid fallback warnings can spam under intermittent sparse failures. Consider rate limiting or aggregation, and ensure logs indicate which path (dense vs hybrid) was executed.

## Positive Observations

- CODEX-GOOD-020-R2-001: Configuration alignment
  - HybridSearchConfig brings this feature in line with project patterns, while still honoring env for legacy usage.
- CODEX-GOOD-020-R2-002: Deployability improvements
  - Optional deps reduce surprise installs; GPU/device selection is a plus.
- CODEX-GOOD-020-R2-003: Memory control
  - LRU cache prevents unbounded model growth; timeouts and fallbacks are robust.
- CODEX-GOOD-020-R2-004: Test coverage & docs
  - Clear examples and tests; warnings for Qdrant version reduce support load.

## Conclusion

Round 2 addresses the substantive risks from Round 1 and moves hybrid search toward production readiness with proper config, optional deps, and better memory controls. The remaining focus should be verifying that config is truly wired through runtime (not just env), clarifying multi-worker guidance, and lightly instrumenting sparsity/fusion behavior for observability. With these checks, the feature is ready for staged rollout.

*** End of Round 2 Review ***
