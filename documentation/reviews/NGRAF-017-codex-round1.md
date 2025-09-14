# NGRAF-017 — Codex Round 1 Review (Debug & Security)

## Summary
- Change category: New Feature (FastAPI REST wrapper, async stack, Docker)
- Commit: feat(api): Implement FastAPI REST wrapper with full async stack - NGRAF-017
- Overall: Solid async FastAPI scaffolding, routers, and tests. However, several production blockers exist: document ID mismatch and deletion API contract, env parsing bug that prevents startup, and incomplete config propagation to GraphRAG. Metrics endpoint from the ticket is missing.

## Critical Issues (Must fix before deploy)

COD-001: nano_graphrag/api/routers/documents.py:24,42 | Critical | Returned doc_id does not match stored ID | Fix to use GraphRAG’s ID
- Evidence:
  - insert single: `doc_id = ... md5(...).hexdigest()[:12]`
  - batch: same 12-char md5
  - GraphRAG actually stores docs using `compute_mdhash_id(doc_string, prefix="doc-")` (full md5 with `doc-` prefix).
- Impact: The API returns IDs that cannot be used to retrieve or delete documents; GET/DELETE will fail for inserted resources.
- Recommendation: Use the same ID generation as GraphRAG when returning IDs, e.g.:
  ```python
  from nano_graphrag._utils import compute_mdhash_id
  doc_id = document.doc_id or compute_mdhash_id(document.content, prefix="doc-")
  ```
  For batch: compute and return actual IDs for each content item. Consider returning immediately with IDs and status=queued if you keep background insertion.

COD-002: nano_graphrag/api/routers/documents.py:73 | Critical | Calls nonexistent `delete_by_id` on KV storage | Implement delete or adapt
- Evidence: `success = await graphrag.full_docs.delete_by_id(doc_id)` but neither RedisKVStorage nor JsonKVStorage implement `delete_by_id` (search shows no definition).
- Impact: DELETE endpoint raises AttributeError at runtime; tests mask this with mocks.
- Recommendation: Add a `delete_by_id(id: str) -> bool` method to `BaseKVStorage` and all KV implementations, or add a generic delete method on GraphRAG that delegates to KV storage. As a stopgap, implement delete in KV backends (Redis: `del key` with namespace; JSON: `pop` then persist) and update BaseKVStorage contract.

COD-003: nano_graphrag/api/config.py | Critical | Env parsing error for `ALLOWED_ORIGINS` | Adjust type or parsing
- Evidence: `allowed_origins: List[str] = ["*"]` and docker-compose sets `ALLOWED_ORIGINS: "*"`.
- Repro: `Settings()` with `ALLOWED_ORIGINS='*'` raises “error parsing value for field "allowed_origins" from EnvSettingsSource”.
- Impact: App fails to start in the provided docker-compose.
- Recommendation: Either (a) set env to valid JSON list: `ALLOWED_ORIGINS='["*"]'`, and update `.env.api.example` and compose; or (b) change field to `Union[str, List[str]]` and normalize to list in `__init__`.

COD-004: nano_graphrag/api/app.py | Critical | GraphRAG config does not consume env for LLM/embedding/query | Use GraphRAGConfig.from_env
- Evidence: The app constructs `GraphRAGConfig(storage=storage_config)` only. GraphRAGConfig reads env vars only via `from_env()`.
- Impact: LLM/provider/model, embedding provider/model, and query flags (e.g., enabling naive mode) in env are silently ignored; behavior deviates from configured expectations.
- Recommendation: Build from env and override storage:
  ```python
  cfg = GraphRAGConfig.from_env()
  cfg = dataclasses.replace(cfg, storage=storage_config)
  app.state.graphrag = GraphRAG(config=cfg)
  ```
  Alternatively map `settings` → GraphRAGConfig explicitly.

COD-005: Query naive mode can 500 by default | Critical | Needs config or error mapping
- Evidence: `QueryParam(mode='naive')` will hit `GraphRAG.aquery` which raises if `enable_naive_rag` is False (default). The API does not catch/translate this.
- Impact: Client receives 500 for a valid-looking request.
- Recommendation: Expose `QUERY_ENABLE_NAIVE_RAG=true` in env and propagate to GraphRAGConfig; or catch `ValueError` and return 400 with clear message when mode is disabled.

## High Priority (Should fix soon)

COD-006: GET /documents response shape inconsistent | High | Returns nested dict instead of content string
- Evidence: `return {"doc_id": doc_id, "content": doc}` where `doc` is `{"content": ...}`.
- Impact: Confusing schema; not aligned with typical REST expectations and your own models.
- Recommendation: Define a response model and normalize: `{"doc_id": id, "content": doc["content"], "metadata": doc.get("metadata")}`.

COD-007: Missing Prometheus metrics endpoint | High | Ticket acceptance not fully met
- Evidence: Ticket lists `GET /api/v1/metrics` and “Prometheus metrics exposed”; code does not include `prometheus-fastapi-instrumentator` or a metrics route.
- Impact: Deployment monitoring gap; acceptance criteria incomplete.
- Recommendation: Add `prometheus-fastapi-instrumentator` and expose `/metrics` under the API prefix.

COD-008: Tests don’t exercise app lifespan/config paths | High | Gaps in coverage for real app setup
- Evidence: tests create a bare `FastAPI()` and include routers with a mocked `graphrag`; they do not import/use `create_app()` or the `lifespan` initialization.
- Impact: Startup/config regressions (like ALLOWED_ORIGINS parsing, GraphRAG env propagation) are not caught.
- Recommendation: Add an integration-style test that imports `create_app()`, overrides env via monkeypatch, and verifies startup, OpenAPI, and health endpoints.

COD-009: Dependencies not declared for local dev/CI | High | FastAPI stack missing from pyproject/requirements
- Evidence: `requirements.txt` comments FastAPI deps; `pyproject.toml` lacks `fastapi`, `uvicorn`, `pydantic-settings`, `httpx`. Tests import FastAPI.
- Impact: CI or contributors installing via `pyproject` won’t have FastAPI; tests will fail outside this environment.
- Recommendation: Add an extra like `api` in `pyproject.toml` or include FastAPI stack in base deps; update docs.

## Medium Priority (Improvements)

COD-010: Exception handling centralization | Medium | No registered handlers
- Evidence: `exceptions.py` exists but no `@app.exception_handler` registrations.
- Impact: Inconsistent error responses; opportunity to map domain errors and `ValueError` to structured JSON.
- Recommendation: Add exception handlers for `GraphRAGError`, `ValueError` (400), and storage unavailability (503).

COD-011: CORS default too permissive | Medium | `*` in production
- Evidence: Default `allowed_origins=["*"]`.
- Impact: Security exposure in prod.
- Recommendation: Default to a safe list (or empty), document how to enable `*` only for dev.

COD-012: Streaming SSE robustness | Medium | Minimal implementation
- Evidence: Manual `data:` chunks, no `id:`/`event:` management, fixed chunk size.
- Impact: Fragile clients, no resume, no heartbeats.
- Recommendation: Consider `sse-starlette` and periodic keepalives; document the event schema.

COD-013: Management /stats relies on non-existent methods | Medium | `get_stats`, `node_count`, `edge_count`
- Evidence: Backends do not implement these; code guards with `hasattr` and returns `{}`.
- Impact: Endpoint not useful now; misleading in docs.
- Recommendation: Implement minimal stats or clearly document it as best-effort; return counts derived from available methods.

## Low Priority (Nice to have)

COD-014: Logging configuration | Low | No structured/JSON logs or uvicorn config
- Recommendation: Add structured logging (json), request/response logging middleware with sampling, and align log levels for storage/LLM providers.

COD-015: Root `"/"` info | Low | Consider including `api_prefix` and health links
- Recommendation: Return `health`, `ready`, and `openapi` links to improve UX.

COD-016: Background insertion feedback | Low | No way to check status when using background task for single insert
- Recommendation: Return an operation ID and a `/operations/{id}` endpoint or avoid backgrounding single insert if you need strong consistency.

## Positive Observations

COD-GOOD-001: Clean async-first design in routers
- Evidence: Consistent `async` endpoints, proper use of `StreamingResponse`, and non-blocking health probes via `asyncio.gather`.

COD-GOOD-002: Neat modularization
- Evidence: Separation into `app.py`, `config.py`, `models.py`, `exceptions.py`, and `routers/*` keeps concerns clear and extensible.

COD-GOOD-003: Test scaffolding with mocks
- Evidence: `tests/api/test_api.py` uses `TestClient` and `AsyncMock` effectively to validate endpoint behavior, including concurrency testing.

COD-GOOD-004: Docker bootstrapping
- Evidence: Dedicated `Dockerfile.api` and `docker-compose-api.yml` to run the full stack locally; healthcheck for liveness.

COD-GOOD-005: Sensible defaults and extensibility
- Evidence: Query modes exposed, SSE example client, and Pydantic settings to grow into production hygiene.

## Reproduction Steps (Key Bugs)

1) Env parsing crash
- `ALLOWED_ORIGINS="*"` then import app:
  ```bash
  python -c "import os; os.environ['ALLOWED_ORIGINS']='*'; from nano_graphrag.api.app import create_app; create_app()"
  ```
- Expected: app created; Actual: pydantic parse error for `allowed_origins`.

2) Document ID mismatch
- Insert a document via POST /api/v1/documents, note returned `doc_id` (12-char md5).
- Try GET/DELETE with that `doc_id`.
- Expected: retrieve/delete works; Actual: GET returns 404 and DELETE errors (nonexistent method), because stored ID is `doc-<full_md5>`.

3) Naive mode 500
- POST /api/v1/query with `{ "mode": "naive" }` on default config.
- Expected: 200 or 400 if disabled; Actual: 500 due to uncaught ValueError from `GraphRAG.aquery`.

## Concrete Fix Plan (Minimal Surface)

- Config
  - Parse `allowed_origins` robustly; fix compose/.env to JSON list.
  - Build `GraphRAGConfig` from env and override storage.
  - Add `QUERY_ENABLE_NAIVE_RAG` to env and propagate.

- Documents
  - Return `compute_mdhash_id(..., prefix="doc-")` IDs.
  - Implement `delete_by_id` in KV backends and update BaseKVStorage.
  - Normalize GET response model.

- Metrics
  - Add Prometheus instrumentator and expose `/metrics`.

- Tests
  - Add a `create_app()` startup test with env variations (origins list, naive mode on/off) to catch regressions.
  - Add a test for the real ID format roundtrip once delete exists.

- Packaging
  - Add FastAPI deps to `pyproject.toml` (or an `[project.optional-dependencies]` extra like `api`).

## Notes
- The current tests all pass locally, but they do not cover the above critical runtime issues because they bypass app startup and use mocks for storage. Addressing the test gaps will make these issues detectable in CI.

