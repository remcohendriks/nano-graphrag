Debug reviewer ready.

# NGRAF-007 — Config Normalization (Round 1)

This review evaluates the implementation against the NGRAF-007 ticket and highlights any defects, risks, and improvements from a debugging/security perspective.

## Scope Adherence
- Clean/legacy split implemented as specified:
  - `to_dict()` now returns only active configuration plus conditional storage params (HNSW and Node2Vec).
  - `to_legacy_dict()` preserves all legacy/compat fields previously in `to_dict()`.
- `GraphRAG._global_config()` uses `to_legacy_dict()`; storage creation continues to use the clean `to_dict()`.
- `validate_config(config)` helper added per ticket.
- Tests updated to assert separation and validator behavior.

Overall, the changes align well with the ticket intent while minimizing churn.

## Critical Issues
- None blocking merge identified.

## High Priority Issues

- Clean dict vs. Node2Vec dimensions coupling
  - Files: `nano_graphrag/config.py` (Node2VecConfig; clean dict), `nano_graphrag/_storage/gdb_networkx.py` (node2vec usage)
  - Behavior: Clean `to_dict()` conditionally includes `node2vec_params` when using the NetworkX backend and Node2Vec is enabled (default True). The legacy dict also includes node2vec params (sourced from embedding dimension in legacy form).
  - Risk: Divergence between clean `node2vec_params['dimensions']` (from `StorageConfig.node2vec.dimensions`, default 128) and legacy dict dimensions (from `EmbeddingConfig.dimension`, default 1536). Not harmful currently because storage creation uses the clean dict and ops use the legacy dict, but be mindful when mixing dicts in future refactors.
  - Recommendation: Document that clean `node2vec_params` is authoritative for NetworkX storage. Optionally align legacy dict’s node2vec dimension to the same source (storage config) for consistency.

## Medium Priority Suggestions

- Optional: Run config validation on init
  - File: `nano_graphrag/graphrag.py`
  - Suggestion: Invoke `validate_config(self.config)` in `__init__` and log `warning`s if present. This remains non-breaking and improves early feedback.

- Clarify addon_params propagation for future graph backends
  - Files: `graphrag.py`, `config.py`, `_storage/gdb_neo4j.py`
  - Note: Neo4j backend (not enabled in factory) expects `global_config['addon_params']`. Currently, storage creation uses the clean dict (no `addon_params`) and ops use legacy (with `addon_params`). This is fine for NetworkX but, for a future Neo4j enablement, ensure storage receives the needed fields (either pass legacy dict to storage for that backend or introduce typed constructor args).

- Type hint polish
  - File: `nano_graphrag/base.py`
  - Minor: `node_degrees_batch` return type is `List[str]` but used as numeric degrees. Consider changing to `List[int]` in a follow-up for consistency.

## Low Priority Notes
- Ticket sample clean `to_dict()` listed `tokenizer_type`; the implementation omits tokenizer fields from the clean dict. This is acceptable (they are not used by storage or ops when clean dict is used) and better reflects the “active only” intent.
- Good choice to add a frozen `Node2VecConfig` in `StorageConfig`; it makes the clean config self-contained for NetworkX.
- `validate_config()` intentionally excludes the overlap check since `ChunkingConfig.__post_init__` enforces it — sensible deduplication.

## Positive Observations
- Minimal touch surface: only 1 line change in `graphrag.py`, focused additions in `config.py` and tests.
- Backward compatibility preserved; ops wiring uses `to_legacy_dict()` so legacy keys remain available (`cheap_model_*`, tokenizer names, `addon_params`).
- Clean separation clarifies what the system actually uses vs. legacy shims.
- Tests cover both clean vs legacy expectations and validation warnings.

## Verification
- Diff confirms:
  - `to_dict()` returns only active params plus conditional HNSW/Node2Vec.
  - `to_legacy_dict()` contains the prior full set of fields (tokenizer names, cheap model limits, node2vec, addon flags).
  - `GraphRAG._global_config()` now spreads `to_legacy_dict()` while `_init_storage()` still passes the clean dict into the factory.
  - Tests added for legacy/clean split and `validate_config()`.

## Conclusion

The implementation meets the ticket’s goals and is robust. No blockers found. Consider the medium‑priority improvements (init-time validation logging and future `addon_params` propagation plan for Neo4j) as follow-ups. Approved from a debugging/security perspective.

