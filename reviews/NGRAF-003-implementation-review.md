**NGRAF-003 Implementation Review — Storage Factory Pattern**

- Ticket: `tickets/NGRAF-003-storage-factory-pattern.md`
- Report: `reports/NGRAF-003-implementation-report.md`
- Scope: Centralized storage creation for vector/graph/KV; GraphRAG refactor

**Summary**

- The factory is well-implemented, aligns with current storage contracts, and keeps backend restrictions explicit. GraphRAG now delegates storage creation cleanly, and tests cover registration, creation, and parameter plumbing. Overall, the implementation meets the ticket goals with low complexity and good readability.

**What’s Good**

- Centralization: `StorageFactory` consolidates creation logic with clear `create_*` APIs.
- Contracts preserved: Factory signatures match existing backends (`namespace`, `global_config`, `embedding_func`, optional `meta_fields`).
- Lazy registration: `_register_backends()` avoids heavy imports at module load.
- Backend restrictions: Allowed sets enforced consistently (vector `{nano,hnswlib}`, graph `{networkx}`, KV `{json}`).
- GraphRAG integration: `_init_storage()` is smaller and easier to read; meta fields are set explicitly.
- Config mapping: `GraphRAGConfig.to_dict()` surfaces `vector_db_storage_cls_kwargs` for HNSW parameters.
- Tests: Solid coverage for registration, creation, unknown backend errors, HNSW param passthrough, and lazy registration.

**Minor Nits / Readability**

- DRY on allowed sets: The allowed backend sets are defined in both `StorageConfig.__post_init__` and `StorageFactory`. To avoid drift, consider a single source of truth (e.g., constants module or deriving factory allowed sets from config).

- Circular import risk (low): `_register_backends()` imports from `nano_graphrag._storage`, which re-exports the classes and the factory. It’s inside the function so it likely works fine, but you can reduce coupling by importing modules directly:
  ```python
  # nano_graphrag/_storage/factory.py
  from .vdb_hnswlib import HNSWVectorStorage
  from .vdb_nanovectordb import NanoVectorDBStorage
  from .gdb_networkx import NetworkXStorage
  from .kv_json import JsonKVStorage
  ```

- Double plumbing of HNSW params: You both pass `ef_*`/`M`/`max_elements` via factory kwargs and read them again inside `HNSWVectorStorage.__post_init__` from `global_config["vector_db_storage_cls_kwargs"]`. It works, but consider picking one path (prefer the factory kwargs) to reduce confusion.

- Unused direct imports: `graphrag.py` still imports storage classes directly (for types), but creation is via the factory. Consider removing unused imports to underscore the single creation path.

**Suggested Tweaks (Optional, Low-Complexity)**

- Single source for allowed sets:
  - Move allowed backend names to a small constants module (e.g., `nano_graphrag/_storage/constants.py`) and import in both `StorageConfig` and `StorageFactory`.

- Prefer direct module imports in `_register_backends()` to avoid package-level cycles:
  ```python
  # nano_graphrag/_storage/factory.py
  def _register_backends():
      if not StorageFactory._vector_backends:
          from .vdb_hnswlib import HNSWVectorStorage
          from .vdb_nanovectordb import NanoVectorDBStorage
          StorageFactory.register_vector("hnswlib", HNSWVectorStorage)
          StorageFactory.register_vector("nano", NanoVectorDBStorage)
      if not StorageFactory._graph_backends:
          from .gdb_networkx import NetworkXStorage
          StorageFactory.register_graph("networkx", NetworkXStorage)
      if not StorageFactory._kv_backends:
          from .kv_json import JsonKVStorage
          StorageFactory.register_kv("json", JsonKVStorage)
  ```

- HNSW params: If you stick with factory kwargs, you can simplify `HNSWVectorStorage.__post_init__` by trusting dataclass field values and only falling back to `global_config` when fields aren’t set.

**Verification Notes**

- GraphRAG uses the factory for all KV/graph/vector stores and sets `meta_fields` for:
  - `entities_vdb`: `{"entity_name", "entity_type"}`
  - `chunks_vdb`: `{"doc_id"}`
- Config now includes `vector_db_storage_cls_kwargs` when `vector_backend == "hnswlib"`.
- Allowed set remains strict; if you later add `neo4j` or others, update both validation and factory registration in the same PR.

**Verdict**

- Looks good and achieves the ticket goals. If you address the small DRY/cycle nits above, we’ll have a very clean, maintainable storage creation story. No blockers.

