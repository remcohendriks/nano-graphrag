# NGRAF-020-2 — Round 2 Review (expert-codex)

## Summary

The Round 2 changes are minimal and address the two critical gaps from Round 1:
- Entity ID derivation is now consistent with initial insertion (hashing uses `entity_name` rather than `node_id`).
- Hybrid enablement is resolved from `GraphRAGConfig/StorageConfig` first, with a fallback to the previous global/env flag.

These fixes prevent silent payload misses and ensure the payload‑only path is actually used when hybrid is enabled. The added DEBUG logging for filtered fields is a small but useful observability win. The fallback path is clearly documented.

## Verification

- ID Consistency: The fix aligns post‑community keys with the initial upsert convention; tests cover the mismatch case.
- Config Path: The conditional now checks `self.config.storage.hybrid_search.enabled` before falling back, matching the hybrid feature’s config‑first pattern established in NGRAF‑020.
- Payload Updates: Qdrant `set_payload` continues to filter out `content`/`embedding` defensively, and logging only triggers at DEBUG to avoid noise.

## Remaining Notes

- As intended for minimal change, batch payload optimizations were not pursued — acceptable given Qdrant’s current API and typical entity counts.
- Ensure the same helper is used everywhere for “is hybrid enabled” to avoid future drift.

## Recommendation

Approve. The fixes are surgical, low‑risk, and directly eliminate the re‑embedding regression while preserving dense+sparse vectors. Proceed to merge and monitor that post‑community logs consistently show “Updated payload … (vectors preserved)” and that no points lose sparse vectors after community generation.
