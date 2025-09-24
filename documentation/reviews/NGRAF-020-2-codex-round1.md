# NGRAF-020-2 — Round 1 Review (expert-codex)

## Scope & Changes Reviewed

- Ticket: Entity Embedding Preservation via Payload-Only Updates
- Report: documentation/reports/NGRAF-020-2-round1-report.md
- Core changes:
  - Add Qdrant-only `update_payload` that never touches vectors
  - Switch post‑community entity refresh to payload-only updates
  - Introduce `community_description` payload field; keep `content` immutable (canonical embedding source)

## Critical/High Findings

- CODEX-0202-001: Entity ID derivation consistency | High
  - Location: Post-community update path (graphrag.py changes described in report)
  - Evidence: Initial upsert uses `compute_mdhash_id(dp["entity_name"], prefix="ent-")`; post‑community path computes `entity_key = compute_mdhash_id(node_id, prefix='ent-')`.
  - Impact: If `node_id` ≠ `entity_name` for some entities, payload updates won’t hit the intended Qdrant point, leaving vectors and metadata out of sync.
  - Recommendation: Use the exact same source field for hashing in both paths (prefer the existing initial convention). If `node_id` is already equal to `entity_name`, document this invariant; otherwise, normalize to a single canonical ID derivation.

- CODEX-0202-002: Hybrid enablement check path | High
  - Location: Conditional branching for payload-only updates (graphrag.py)
  - Evidence: Report references `self.global_config.get("enable_hybrid_search", False)` to decide payload-only vs upsert.
  - Impact: If the runtime hybrid toggle is stored under `storage/hybrid_search` (config-first pattern), but the code only checks a flat `enable_hybrid_search`, you can silently take the re‑embedding path.
  - Recommendation: Resolve hybrid enablement from `GraphRAGConfig/StorageConfig` first, then env as a fallback (consistent with round‑2 hybrid changes). Add a single helper (e.g., `is_hybrid_enabled()`), and use it everywhere.

## Medium Findings

- CODEX-0202-003: Payload API usage breadth | Medium
  - Location: Qdrant `update_payload`
  - Evidence: Iterative `set_payload` per point is simple and correct, but can be chatty at scale.
  - Impact: Minor performance overhead for large batches. Not a blocker for minimal-change scope.
  - Recommendation: None required now. If needed later, consider grouping points by shared fields and using `key` updates; otherwise keep as-is for clarity.

- CODEX-0202-004: Guarding embedding fields | Medium
  - Location: Qdrant `update_payload`
  - Evidence: The method filters `content` and `embedding` to avoid re‑embedding.
  - Impact: Good protection; ensure tests cover attempts to pass these keys and assert they’re stripped.
  - Recommendation: Keep the filter list minimal and explicit (as implemented). Optionally log a DEBUG warning if filtered keys were present in an update.

## Low Findings

- CODEX-0202-005: Fallback path clarity | Low
  - Location: Post‑community else-path (legacy upsert)
  - Evidence: Falls back to full upsert if `update_payload` not present or hybrid disabled.
  - Impact: Acceptable for minimal change, but document in code that this path re‑embeds vectors by design.
  - Recommendation: Add a concise comment indicating the trade-off, to prevent accidental reuse in hybrid contexts.

## Positive Observations

- CODEX-GOOD-0202-001: Correct primitive
  - Using Qdrant’s `set_payload` cleanly avoids vector churn and preserves both dense and sparse vectors.
- CODEX-GOOD-0202-002: Field separation
  - `content` remains the canonical embedding source; `community_description` provides mutable, display-friendly metadata.
- CODEX-GOOD-0202-003: Minimal, targeted change
  - No cross-backend burden, no heavy refactoring; low-risk and high impact.
- CODEX-GOOD-0202-004: Test intent
  - Tests verify no re-embedding (via embed call counts) and that content/embedding keys are not sent in payload updates.

## Reproduction/Verification Steps

1) Insert entities and confirm Qdrant points include both `dense` and `sparse` vectors.
2) Trigger post‑community update and verify logs show "Updated payload … (vectors preserved)".
3) Inspect Qdrant: updated points still have both named vectors; payload includes `community_description` without changes to `content`.
4) Run a name/ID query and compare scores before/after; top-1 ID match should remain the same entity.

## Conclusion

This solution fixes the class of issues caused by post‑community re‑embedding with a minimal, correct change: payload‑only updates on Qdrant and immutability of the canonical embedding field. Before merging, ensure:
- The entity ID hashing source matches initial upsert (prevent silent misses), and
- The hybrid flag is resolved from config consistently.

With those checks, this is safe to roll out and will stop sparse/dense vector churn while preserving retrieval quality.
