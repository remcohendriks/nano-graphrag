Debug reviewer ready.

# Abstract

NGRAF-010 focuses on import hygiene and lazy loading to reduce import time and memory. This change set makes strong progress: providers are lazily imported via on-demand factories and `__getattr__`, StorageFactory registers loader callables instead of classes, graspologic imports in NetworkX storage are guarded with helpful `ensure_dependency()` checks, and a DSPy lazy wrapper is introduced. However, several gaps remain: (1) entity_extraction modules still import dspy at module scope, (2) the storage aggregator nano_graphrag/_storage/__init__.py still eagerly imports heavy backends, (3) HNSW/Neo4j storages do not expose the class-level lazy properties claimed (and used by tests), and (4) Bedrock provider still imports aioboto3 at module scope (mitigated by the providers’ lazy __getattr__, but worth noting). With a few targeted fixes, this PR will fully meet the ticket’s goals.

# Critical Issues (must fix before merge)

- Missing lazy properties in storages (test mismatch)
  - Files:
    - `nano_graphrag/_storage/vdb_hnswlib.py`
    - `nano_graphrag/_storage/gdb_neo4j.py`
  - Problem: The implementation report and `tests/test_lazy_imports.py` expect class-level lazy properties (e.g., `hasattr(HNSWVectorStorage, 'hnswlib')` and `hasattr(Neo4jStorage, 'neo4j')`). These properties are not defined in the classes, so the tests will fail.
  - Fix (pattern): add properties that import on first use and leverage `ensure_dependency()`.
    - HNSW example:
      ```python
      from nano_graphrag._utils import ensure_dependency
      class HNSWVectorStorage(BaseVectorStorage):
          @property
          def hnswlib(self):
              ensure_dependency('hnswlib', 'hnswlib', 'HNSW vector storage')
              import hnswlib
              return hnswlib
      ```
      Then replace module-level `hnswlib.Index` references with `self.hnswlib.Index`.
    - Neo4j example:
      ```python
      from nano_graphrag._utils import ensure_dependency
      class Neo4jStorage(BaseGraphStorage):
          @property
          def neo4j(self):
              ensure_dependency('neo4j', 'neo4j', 'Neo4j graph storage')
              from neo4j import AsyncGraphDatabase
              return AsyncGraphDatabase
      ```
      Use `self.neo4j` to obtain `AsyncGraphDatabase` in `__post_init__`.

- Eager storage aggregator import undermines hygiene
  - File: `nano_graphrag/_storage/__init__.py` (lines 1–5)
  - Problem: Eagerly imports `NetworkXStorage`, `Neo4jStorage`, and `HNSWVectorStorage` at module load, pulling heavy deps even when unused.
  - Fix: Convert to a lazy `__getattr__`-based resolver (mirroring providers) or remove these re-exports. Recommend steering users to `StorageFactory` or direct module imports to preserve hygiene.

# High Priority Issues (should fix soon)

- DSPy still imported at module scope in entity extraction
  - Files:
    - `nano_graphrag/entity_extraction/module.py`
    - `nano_graphrag/entity_extraction/extract.py`
    - `nano_graphrag/entity_extraction/metric.py`
  - Problem: These import `dspy` at top-level; importing these modules fails if DSPy is not installed and negates the lazy benefits.
  - Fix: Use `TYPE_CHECKING` for hints and lazy-load DSPy via `ensure_dependency()` at first use (or refactor to depend on `entity_extraction/lazy.py`).

- Bedrock provider still imports `aioboto3` at module scope
  - File: `nano_graphrag/llm/providers/bedrock.py`
  - Note: Thanks to providers’ lazy factory/`__getattr__`, this module isn’t imported unless Bedrock is requested, so impact is limited. Optional polish: move import inside `__init__`/first use with `ensure_dependency()` for friendlier errors when importing bedrock directly.

# Medium Priority Suggestions (improvements)

- Providers: Add a short docstring note that names are lazily resolved to set expectations for users.
- StorageFactory: `ALLOWED_GRAPH` currently only lists `networkx`. If Neo4j support will be exposed soon, update allowed set and registration (guarded by env/config as needed).
- Redundant re-raises: In `gdb_networkx.py`, after calling `ensure_dependency('graspologic', ...)`, you immediately `raise`. Since `ensure_dependency` raises, the extra raise is redundant.

# Low Priority Notes (nice to have)

- `tests/test_lazy_imports.py` uses an unusual late `import os`; move it to the top for clarity.
- Consider adding a documentation matrix (feature → extra package) in the readme and calling out lazy loading explicitly.

# Positive Observations (well-done aspects)

- LLM providers now import lazily:
  - `get_llm_provider`/`get_embedding_provider` import the selected provider on demand.
  - `__getattr__` resolves provider classes and legacy exports lazily, maintaining backward compatibility.
- StorageFactory refactor is clean: registers loader callables and instantiates via loader → class, so optional deps aren’t pulled until needed.
- Graspologic hygiene in NetworkX storage is solid with actionable messages through `ensure_dependency()`.
- Dependency utilities (`ensure_dependency`, `check_optional_dependencies`) standardize friendly ImportError guidance.
- DSPy lazy wrapper (`entity_extraction/lazy.py`) is a good foundation to decouple import-time from usage-time.

# Reproduction / Verification

- Without `dspy/neo4j/hnswlib/graspologic` installed:
  - `import nano_graphrag` succeeds.
  - `from nano_graphrag.llm.providers import get_llm_provider` succeeds, and no provider submodule is imported until requested.
  - `from nano_graphrag._storage.factory import StorageFactory` then creating the `nano` vector store works; creating `hnswlib` vector store should raise a friendly ImportError.
- `tests/test_lazy_imports.py` should pass once the storages expose the expected lazy properties and `_storage/__init__.py` stops eager imports.

# Recommendation

Approve with changes. Add the lazy properties expected by tests to HNSW/Neo4j storages and remove (or lazify) `_storage/__init__.py` eager imports. Consider moving remaining DSPy imports to lazy at first use. With these small, targeted updates, this PR will fully meet NGRAF-010’s goals of faster imports and lower memory without sacrificing UX.
