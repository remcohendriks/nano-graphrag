# NGRAF-022 Phase 2.5: Controlled Parallel Inserts & Batch Tuning

## User Story
As a platform engineer, I need to reintroduce controlled parallelism for document ingestion while keeping Neo4j deadlock-free, so that large backfills finish in acceptable time without sacrificing the stability we achieved in Phase 2.

## Current State
- Phase 2 moved ingestion to a strict serial loop (`nano_graphrag/graphrag.py:413-416`) to avoid `Neo.TransientError.Transaction.DeadlockDetected` when multiple documents touched the same entities.
- Each document now builds a `DocumentGraphBatch` and executes a single Neo4j transaction (`nano_graphrag/_extraction.py:422-460` → `nano_graphrag/_storage/gdb_neo4j.py:600-661`). Deadlocks are gone, but throughput dropped ~5× compared with the original `asyncio.gather` approach.
- Batch execution still slices nodes/edges into `max_size=10` chunks (`nano_graphrag/_extraction.py:43-55`); large documents therefore incur dozens of sequential UNWIND round-trips even within a single transaction.

## Problem Statement
We need to (1) safely allow multiple documents in flight when they do not touch the same entity IDs, and (2) reduce the number of round-trips a single document makes inside its transaction. Without these improvements, ingesting hundreds of medium documents takes hours.

## Objectives
1. Introduce an application-level locking layer that enforces a consistent lock order for shared entity IDs across concurrent documents.
2. Replace the per-document `for` loop with a bounded concurrency worker pool that leverages the lock layer.
3. Tune the batch executor so that a document submits larger UNWIND payloads per transaction chunk, minimizing network chatter.
4. Add observability around waiting time, retries, and chunk counts to validate the tuning in staging.

## Detailed Plan

### 1. Entity-Level Lock Coordinator
Create a reusable helper to guard Neo4j writes:
```python
# nano_graphrag/_coordination.py
class EntityLockCoordinator:
    def __init__(self):
        self._locks = collections.defaultdict(asyncio.Lock)
        self._global = asyncio.Lock()

    async def lock_many(self, entity_ids: Iterable[str]):
        ids = sorted(set(entity_ids))
        async with self._global:
            locks = [self._locks[i] for i in ids]
        for lock in locks:
            await lock.acquire()
        return LocksGuard(locks)
```
Usage inside `_extract_entities_wrapper`:
```python
entity_ids = list(maybe_nodes.keys()) + [edge[0] for edge in maybe_edges] + [edge[1] for edge in maybe_edges]
async with self.entity_lock_coordinator.lock_many(entity_ids):
    await graph_storage.execute_document_batch(batch)
```
This guarantees consistent lock ordering and prevents the circular wait pattern that triggered Neo4j deadlocks.

### 2. Bounded Parallel Document Processing
Update `GraphRAG.ainsert()` to run documents through a worker pool:
```python
semaphore = asyncio.Semaphore(self.config.storage.neo4j_max_parallel_docs)
async def worker(doc_idx, doc):
    async with semaphore:
        await process_single_document(doc, doc_idx)
await asyncio.gather(*(worker(i, doc) for i, doc in enumerate(string_or_strings)))
```
`neo4j_max_parallel_docs` becomes a new config knob (default 2). The entity lock coordinator ensures that overlapping documents serialize, while unrelated documents progress concurrently.

### 3. Batch Chunk Size and Combined UNWIND
- Expose `DocumentGraphBatch.chunk(max_size)` as configurable via `NEO4J_BATCH_CHUNK_SIZE` to raise the default from 10 to e.g. 100.
- Collapse node/edge writes into a single Cypher statement per chunk (`_process_batch_chunk`):
```cypher
UNWIND $nodes AS node
MERGE (n:`{namespace}` {id: node.id})
SET n += node.data
WITH $edges AS edges
UNWIND edges AS edge
MATCH (s:`{namespace}` {id: edge.source_id})
MATCH (t:`{namespace}` {id: edge.target_id})
MERGE (s)-[r:RELATED]->(t)
SET r += edge.edge_data
```
This keeps lock acquisition deterministic and halves the number of driver round-trips.

### 4. Instrumentation
Add structured logs and counters:
- Wait duration for entity locks.
- Number of chunks per document and average chunk size.
- TransientError retries (still using Tenacity).
Expose the data through the existing logging framework so we can compare staging runs before/after.

## Risks & Mitigations
- **Lock explosion**: Hot entities could create a convoy. Mitigate with metrics; if needed, add timeout + backoff before retrying lock acquisition.
- **Increased memory in a chunk**: Larger UNWIND batches raise payload size. Neo4j’s limit is generous, but keep `NEO4J_BATCH_CHUNK_SIZE` configurable and default to a conservative value (100).
- **Config drift**: New knobs (`neo4j_max_parallel_docs`, `NEO4J_BATCH_CHUNK_SIZE`) must flow through `GraphRAGConfig` and docs; include defaults in `.env.example`.

## Validation Strategy
1. Unit tests for `EntityLockCoordinator` (ordering, reentrancy, release).
2. Stress test: simulate overlapping documents (>=10) and assert zero deadlocks, bounded lock wait, and successful completion.
3. Performance regression suite: measure total insert time and Neo4j query count before/after on a 300-document fixture.
4. Manual staging run capturing metrics for log review.

## Opinion
Phase 2 gave us safety but sacrificed throughput. Coordinating writes at the application layer lets us reclaim parallelism without depending on Neo4j’s internal lock scheduler, which remains the unpredictable part of the system. Because we already batch nodes and edges deterministically, the incremental changes above are localised and align with the architecture: entity-awareness lives close to extraction, transaction batching remains in the storage layer, and `GraphRAGConfig` becomes the single place to tune behaviour. By instrumenting the new path we also future-proof ingestion against regressions when dataset size or model throughput grows.

## References
- `_extract_entities_wrapper` batching: `nano_graphrag/_extraction.py:422-460`
- Current sequential guard: `nano_graphrag/graphrag.py:413-416`
- Batch executor: `nano_graphrag/_storage/gdb_neo4j.py:600-661`
- Tenacity retry handling: `nano_graphrag/_storage/gdb_neo4j.py:629-661`
