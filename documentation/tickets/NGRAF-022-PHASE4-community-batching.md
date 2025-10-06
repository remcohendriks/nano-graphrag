# NGRAF-022 Phase 4: Community Report Neo4j Load Shedding

## Summary

Community report generation currently launches unbounded asynchronous work at three levels (per community, per node, per edge). In large datasets (e.g. 100 documents → 719 communities) this triggers thousands of concurrent Neo4j session requests and exhausts the driver pool (default 50 connections), leading to repeated `failed to obtain a connection from the pool within 60.0s` errors and blocking the ingest pipeline. Phase 4 introduces a bounded, batched execution model that keeps concurrency under control while maintaining throughput.

## Problem Statement

1. `_form_single_community_report` is invoked via `asyncio.gather` for every community in a level (`nano_graphrag/_community.py:354-367`). With hundreds of communities per level, all reports are generated in parallel.
2. `_pack_single_community_describe` uses `asyncio.gather` to call `knowledge_graph_inst.get_node` / `get_edge` for each entity/edge (`_community.py:135-180`). Each call opens its own Neo4j session (`nano_graphrag/_storage/gdb_neo4j.py:318-379`).
3. Net effect: 50–3 000 concurrent sessions vs a pool size of 50 → connection starvation and timeouts.

## Goals

- Replace per-node/edge fetch fan-out with batch APIs to minimize session count.
- Introduce a semaphore to cap the number of communities rendered simultaneously.
- Preserve performance on small datasets while staying within Neo4j limits on large loads.

## Proposed Implementation

### 1. Add an async semaphore for community processing

File: `nano_graphrag/_community.py`

- Define a module-level (or function parameter) concurrency cap, configurable via global config (`community_report_max_concurrency`, default e.g. 8).
- Wrap `_form_single_community_report` calls with an `asyncio.Semaphore`.

```python
# nano_graphrag/_community.py (inside generate_community_report)
max_concurrency = global_config.get("community_report_max_concurrency", 8)
semaphore = asyncio.Semaphore(max_concurrency)

async def _bounded_form_report(community):
    async with semaphore:
        return await _form_single_community_report(community, community_datas)

this_level_communities_reports = await asyncio.gather(
    *[_bounded_form_report(c) for c in this_level_community_values]
)
```

### 2. Batch node and edge fetches inside `_pack_single_community_describe`

File: `nano_graphrag/_community.py`

- Replace per-item `asyncio.gather` with the existing batch methods:

```python
# Before:
nodes_data = await asyncio.gather(
    *[knowledge_graph_inst.get_node(n) for n in nodes_in_order]
)
edges_data = await asyncio.gather(
    *[knowledge_graph_inst.get_edge(src, tgt) for src, tgt in edges_in_order]
)

# After:
nodes_data = await knowledge_graph_inst.get_nodes_batch(nodes_in_order)
edges_data = await knowledge_graph_inst.get_edges_batch(edges_in_order)
```

- Keep existing logic for handling `None` results; the batch API already aligns the output order.

### 3. Batch weights / degrees once

- Optional but recommended: where `_pack_single_community_describe` currently calculates edge degree per edge (`_community.py:181-217`), use `edge_degrees_batch` once per community to avoid nested session calls.

### 4. Configuration Surface

File: `nano_graphrag/config.py`

- Add `community_report_max_concurrency` to `LLMConfig` or `StorageConfig` (wherever global_config is assembled for community generation). Example default = 8.

```python
@dataclass(frozen=True)
class LLMConfig:
    ...
    community_report_max_concurrency: int = 8
```

- Ensure `GraphRAG._global_config()` includes the new setting so `_community.py` can read it.

### 5. Logging and Metrics

- After applying the semaphore, log how many communities are processed concurrently to aid observability.

```python
logger.debug(
    f"[COMMUNITY] Concurrency cap: {max_concurrency}, "
    f"total communities this level: {len(this_level_community_keys)}"
)
```

## Acceptance Criteria

- Community generation on 100-document run completes without Neo4j connection pool timeouts.
- No regressions in smaller test cases (all existing unit/integration tests pass).
- Logs show the concurrency limiter being applied (debug-level message).
- Prompt size and generation speed remain within acceptable ranges (no disproportionate slowdown).

## Testing

- Re-run ingestion for 100-document dataset against Neo4j backend; record absence of `failed to obtain a connection from the pool` errors.
- Verify community reports contain expected node/edge content after batching.
- Add regression test (optional) that mocks Neo4j storage to track session call counts before/after change.

## Rollout Notes

- No config migration required; new concurrency cap defaults to 8 and can be adjusted via env (`COMMUNITY_REPORT_MAX_CONCURRENCY`).
- Works with both Neo4j and NetworkX (semaphore still bounds tasks but NetworkX has no session cost).
- Coordinate with ops to ensure the new config is exposed in docker/helm charts if needed.

