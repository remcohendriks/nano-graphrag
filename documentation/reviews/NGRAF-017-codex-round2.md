# NGRAF-017 — Codex Round 2 Review (Debug & Security)

## Summary
- Scope: Verify fixes from Round 1 and re-assess readiness.
- Status: All Round 1 critical blockers are addressed. Remaining items are minor or deferred per PO. Close to approval with a few polish suggestions.

## Verification Highlights
- Document IDs now use `compute_mdhash_id(..., prefix="doc-")` and match storage IDs.
- `delete_by_id` added to `BaseKVStorage` and implemented in `JsonKVStorage` and `RedisKVStorage`; DELETE route uses it via `StorageAdapter`.
- `ALLOWED_ORIGINS` parsing fixed (string or JSON array). App starts with `ALLOWED_ORIGINS='*'`.
- `GraphRAGConfig.from_env()` used; storage selectively replaced, so env-driven LLM/embedding/query config now effective.
- Query param whitelist prevents unsafe `setattr` on arbitrary attributes; disabled naive mode now returns 400 in non-streaming endpoint.
- Docker compose credentials now via env substitution (no hardcoded secrets).
- Tests: existing API tests pass locally.

## Critical Issues (Must fix before deploy)
- None remaining from Round 1.

## High Priority (Should fix soon)

COD-R2-001: Packaging of API deps | High
- Location: `pyproject.toml`, `requirements.txt`
- Evidence: FastAPI stack is still missing in `pyproject.toml`; in `requirements.txt` they are commented as optional.
- Impact: Fresh installs via `pyproject` will lack FastAPI; CI/packagers may fail.
- Recommendation: Add an extra (e.g., `api`) to `pyproject.toml` with `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `httpx`; or include them in base deps and update docs.

## Medium Priority (Improvements)

COD-R2-002: Streaming endpoint lacks param whitelist and uniform error mapping | Medium
- Location: `nano_graphrag/api/routers/query.py` (streaming handler, ~lines 60–100)
- Evidence: Streaming path still does `if hasattr(param, key): setattr(param, key, value)` without the `ALLOWED_QUERY_PARAMS` whitelist and doesn’t map disabled-mode errors to 400.
- Impact: Inconsistent safety and behavior vs non-streaming endpoint; potential unexpected param mutation; 500 on disabled naive mode.
- Recommendation: Reuse the same whitelist and try/except mapping as the non-streaming endpoint.

COD-R2-003: Exception handlers not registered | Medium
- Location: `nano_graphrag/api/app.py` (app setup)
- Evidence: `exceptions.py` exists but no `app.add_exception_handler(...)` registrations.
- Impact: Inconsistent error shape; harder production ops.
- Recommendation: Register handlers for `GraphRAGError`, map `ValueError` to 400, storage outages to 503.

COD-R2-004: Background insertion race (single insert) | Medium
- Location: `documents.insert_document`
- Evidence: Single insert uses `BackgroundTasks`; immediate GET/DELETE may 404.
- Impact: Surprise for clients expecting immediate consistency.
- Recommendation: Document eventual consistency semantics or return an operation ID + status endpoint. Alternatively, make single insert awaitable and keep batch async.

## Low Priority (Nice to have)

COD-R2-005: Metrics endpoint deferred | Low
- Location: N/A
- Evidence: Ticket acceptance listed `/metrics`; deferred per PO.
- Impact: Monitoring gap if needed at launch.
- Recommendation: Track as follow-up; `prometheus-fastapi-instrumentator` is straightforward.

COD-R2-006: CORS default `*` in production | Low
- Location: `nano_graphrag/api/config.py`
- Recommendation: Default to safe allowlist; document how to enable `*` for dev only.

COD-R2-007: /stats best-effort only | Low
- Location: `nano_graphrag/api/routers/management.py`
- Evidence: Uses `hasattr(..., get_stats)`; graph counts not implemented.
- Recommendation: Either implement minimal counts or clearly label as best-effort.

COD-R2-008: Structured logging | Low
- Recommendation: Add JSON logging and optional request/response sampling in production.

## Positive Observations

COD-GOOD-006: StorageAdapter abstraction
- Evidence: `nano_graphrag/api/storage_adapter.py` cleanly normalizes sync/async storage usage.

COD-GOOD-007: Safer query param handling
- Evidence: Whitelist of `ALLOWED_QUERY_PARAMS` eliminates arbitrary attribute setting.

COD-GOOD-008: Env-driven GraphRAG config
- Evidence: `GraphRAGConfig.from_env()` plus targeted storage override is the right pattern.

COD-GOOD-009: Credentials via env in compose
- Evidence: Removed hardcoded Neo4j password; now uses env substitution with defaults.

COD-GOOD-010: GET document response normalized
- Evidence: Returns `{doc_id, content, metadata}` consistently.

## Acceptance & Readiness
- Round 1 critical issues: Fixed.
- Remaining items: Packaging and streaming parity are the only notable polish items; metrics explicitly deferred by PO.
- Recommendation: Approve contingent on addressing COD-R2-001 (packaging). The streaming parity (COD-R2-002) is advisable but can follow if timelines are tight.

## Commands Used
- git diff/name-status, stat, last commit message
- File inspection and targeted runtime checks
- pytest of API suite

