Debug reviewer ready.

# Abstract

I re-checked the latest commit (5e1da28). Round 2 has fixed the big gaps: `_storage/__init__.py` now lazily resolves backends via `__getattr__`, and both HNSW and Neo4j storages expose lazy properties (`hnswlib`/`neo4j`) and use them internally, aligning with the test expectations. Providers remain lazy via factories and `__getattr__`; the factory registers loader callables; graspologic is gated with `ensure_dependency()`; and a DSPy lazy wrapper exists. One remaining change is needed for full alignment with the ticket: remove dependency checks from factory loaders. DSPy still imports at module scope in entity_extraction modules (non‑blocking, recommended to fix).

# Critical Issues (must fix before merge)

- Factory loader dependency checks
  - File: `nano_graphrag/_storage/factory.py`
  - Issue: `_get_hnswlib_storage()` and `_get_neo4j_storage()` still call `ensure_dependency()`. With the new lazy properties on the storage classes, dependency checks should happen at instantiation/first use, not when resolving the loader. This keeps loaders lightweight and avoids premature errors.
  - Fix: Remove `ensure_dependency` from these loader functions and rely on the storages’ lazy properties to raise actionable errors when needed.

# High Priority Issues (should fix soon)

- DSPy still imported at module scope in entity extraction
  - Files: `nano_graphrag/entity_extraction/module.py`, `extract.py`, `metric.py` — `import dspy` at top-level.
  - Fix: Use `TYPE_CHECKING` + lazy import in call paths with `ensure_dependency('dspy','dspy','typed entity extraction')`, or route usages via `entity_extraction/lazy.py`.

- Bedrock provider module-level import (acceptable with lazy providers)
  - File: `nano_graphrag/llm/providers/bedrock.py` — imports `aioboto3` at module scope.
  - Given providers are lazy, this is acceptable. Optional polish: import on first use with `ensure_dependency()` for friendlier direct-import behavior.

# Positives

- LLM providers: `get_llm_provider`/`get_embedding_provider` now import only the requested provider; `__getattr__` lazily resolves provider classes and legacy exports.
- StorageFactory: registers loader callables; instances created only load dependencies at construction time.
- NetworkX storage: `graspologic` imports gated by `ensure_dependency()` with actionable messages.
- Dependency helpers: `ensure_dependency()` and `check_optional_dependencies()` centralize friendly ImportError UX.
- DSPy lazy wrapper: available for decoupling import-time from usage-time.

# Recommendation

Close to merge. Remove `ensure_dependency()` from the StorageFactory loader functions. If time allows, also move DSPy imports in entity_extraction modules to lazy. With that change, NGRAF-010 fully meets its goals.
