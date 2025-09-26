# NGRAF-022 – Neo4j Batch Transaction for Document Processing

## Summary
Eliminate Neo4j deadlocks by processing each document's graph operations in a single atomic transaction instead of concurrent individual operations.

## Problem Statement
Current implementation experiences deadlocks (`Neo.TransientError.Transaction.DeadlockDetected`) even with serial document processing because entity/edge operations within each document run concurrently via `asyncio.gather`. This causes lock contention when bidirectional relationships or shared entities are processed.

## Root Cause
- `nano_graphrag/_extraction.py:201`: `asyncio.gather` for parallel edge operations
- Each edge operation creates separate transaction
- No consistent lock ordering for nodes
- Circular wait conditions when processing bidirectional relationships

## Solution Approach
Process entire document as single atomic transaction with deterministic operation ordering.

## Implementation Requirements

### 1. Create Batch Accumulator (`nano_graphrag/_storage/batch.py`)
```python
from dataclasses import dataclass, field
from typing import Dict, List
from nano_graphrag._utils import compute_mdhash_id

@dataclass
class DocumentGraphBatch:
    doc_id: str
    nodes: Dict[str, dict] = field(default_factory=dict)
    edges: Dict[tuple[str, str], dict] = field(default_factory=dict)

    def add_node(self, node_id: str, data: dict):
        node_key = compute_mdhash_id(node_id, prefix="ent-")
        if node_key in self.nodes:
            self.nodes[node_key] = merge_node_attributes(self.nodes[node_key], data)
        else:
            self.nodes[node_key] = normalize_node_attributes(node_id, data)

    def add_edge(self, source: str, target: str, data: dict):
        # Canonical ordering for undirected storage, feel free to adjust if direction matters
        src_key = compute_mdhash_id(source, prefix="ent-")
        tgt_key = compute_mdhash_id(target, prefix="ent-")
        edge_key = tuple(sorted((src_key, tgt_key)))
        if edge_key in self.edges:
            self.edges[edge_key] = merge_edge_attributes(self.edges[edge_key], data)
        else:
            self.edges[edge_key] = normalize_edge_attributes(src_key, tgt_key, data)

    def prepare_parameters(self) -> dict:
        sorted_nodes = [self.nodes[k] for k in sorted(self.nodes.keys())]
        sorted_edges = [self.edges[k] for k in sorted(self.edges.keys())]
        return {
            "nodes": sorted_nodes,
            "edges": sorted_edges,
        }
```

Utilities `merge_node_attributes`, `normalize_node_attributes`, `merge_edge_attributes`, `normalize_edge_attributes` should reuse the logic currently in `_merge_nodes_then_upsert` / `_merge_edges_then_upsert` to preserve description aggregation, source deduplication, relation types, etc.

### 2. Modify Edge Processing (`nano_graphrag/_extraction.py`)
Replace parallel processing:
```python
# REMOVE:
await asyncio.gather(*[
    _merge_edges_then_upsert(edge_data) for edge_data in edges
])

# ADD:
batch = DocumentGraphBatch(doc_id)
for node_name, node_variants in maybe_nodes.items():
    for node_dp in node_variants:
        batch.add_node(node_name, node_dp)
for (src, tgt), edge_variants in maybe_edges.items():
    for edge_dp in edge_variants:
        batch.add_edge(src, tgt, edge_dp)
await knowledge_graph_inst.execute_batch(batch)
```

### 3. Add Batch Transaction (`nano_graphrag/_storage/gdb_neo4j.py`)
```python
BATCH_UPSERT_QUERY = """
WITH $nodes AS nodes, $edges AS edges
UNWIND nodes AS node
MERGE (n:Entity {id: node.id})
SET n += node.properties
WITH edges
UNWIND edges AS edge
MATCH (a:Entity {id: edge.source})
MATCH (b:Entity {id: edge.target})
MERGE (a)-[r:RELATES_TO {id: edge.id}]->(b)
SET r += edge.properties
"""

async def execute_batch(self, batch: DocumentGraphBatch):
    params = batch.prepare_parameters()
    for chunk in chunk_payload(params, max_nodes=1000, max_edges=2000):
        async with self.async_driver.session(database=self.neo4j_database) as session:
            async with session.begin_transaction() as tx:
                try:
                    await tx.run(BATCH_UPSERT_QUERY, chunk)
                    await tx.commit()
                except TransientError as exc:
                    await tx.rollback()
                    raise
```
This `execute_batch` should live alongside existing upsert helpers.

### 4. Payload Chunking (`nano_graphrag/_storage/batch.py`)
Prevent sending overly large payloads to Neo4j by splitting the prepared parameters:
```python
def chunk_payload(params: dict, max_nodes: int = 1000, max_edges: int = 2000):
    nodes = params["nodes"]
    edges = params["edges"]

    node_chunks = [nodes[i:i + max_nodes] for i in range(0, len(nodes), max_nodes)] or [[]]
    edge_chunks = [edges[i:i + max_edges] for i in range(0, len(edges), max_edges)] or [[]]

    # Align chunks to avoid partial duplication; handle cases where one list is empty
    max_chunks = max(len(node_chunks), len(edge_chunks))
    for i in range(max_chunks):
        yield {
            "nodes": node_chunks[i] if i < len(node_chunks) else [],
            "edges": edge_chunks[i] if i < len(edge_chunks) else [],
        }
```
Tune limits based on Neo4j parameter caps (65k values) and empirical tests. We should also log chunk sizes for observability.

### 5. Cypher Query Adjustments
Ensure merge semantics match existing logic. For example:
```cypher
UNWIND nodes AS node
MERGE (n:Entity {id: node.id})
SET n.entity_type = coalesce(node.entity_type, n.entity_type, "UNKNOWN"),
    n.description = apoc.text.join([n.description, node.description], " | "),
    n.source_id = apoc.coll.toSet(apoc.coll.flatten([n.source_id, node.source_id]))
```
Use `COALESCE`/APOC to handle `NULL` properties and preserve deduplicated sets. Similar care is needed for edge weight accumulation (`coalesce(r.weight, 0) + edge.weight`) and relation types.

## Critical Constraints

1. **Preserve existing merge logic**:
   - Description concatenation
   - Weight accumulation
   - Source ID deduplication

2. **Maintain consistent IDs**:
   - Use `compute_mdhash_id(name, prefix='ent-')` everywhere
   - Ensure nodes created before edges reference them

3. **Sort operations**:
   - Nodes by ID alphabetically
   - Edges by `(source_id, target_id)`

4. **No behavior changes**:
   - Same final graph state
   - Same entity/relationship data
   - Just different transaction boundaries

## Files to Modify

1. `nano_graphrag/_storage/batch.py` (new file with `DocumentGraphBatch`, merge helpers, chunking)
2. `nano_graphrag/_extraction.py` (replace `asyncio.gather` sections with batch accumulation)
3. `nano_graphrag/_storage/gdb_neo4j.py` (add `execute_batch`, query constants)
4. `nano_graphrag/graphrag.py` (wire entity extraction wrapper to pass batch to storage)
5. Tests (`tests/test_neo4j_batch.py`, updates to existing extraction tests)

## Definition of Done

- [ ] No `asyncio.gather` in entity/edge processing for writes
- [ ] Single transaction per chunked batch (document or chunked slices)
- [ ] All operations sorted deterministically
- [ ] Existing merge semantics preserved (verified by tests)
- [ ] Batch chunking prevents exceeding Neo4j parameter limits
- [ ] Tests pass without deadlock errors
- [ ] Integration test with 100 documents succeeds

## Test Strategy

```python
# tests/test_neo4j_batch.py
async def test_batch_prevents_deadlock():
    batch = DocumentGraphBatch("test-doc")
    batch.add_edge("Alice", "Bob", {"description": "manages", "weight": 1})
    batch.add_edge("Bob", "Alice", {"description": "reports", "weight": 1})

    params = batch.prepare_parameters()
    async with gdb_session.begin_transaction() as tx:
        await tx.run(BATCH_UPSERT_QUERY, params)
        await tx.commit()

async def test_merge_semantics_preserved():
    batch = DocumentGraphBatch("test-doc")
    batch.add_node("Alice", {"description": "Engineer", "source_id": ["chunk-1"]})
    batch.add_node("Alice", {"description": "Manager", "source_id": ["chunk-2"]})

    await graph_storage.execute_batch(batch)
    node = await graph_storage.get_node("ent-...hash...")
    assert "Engineer" in node["description"]
    assert "chunk-1" in node["source_id"] and "chunk-2" in node["source_id"]
```

Add tests for chunking to ensure large batches split, and tests that verify fallback/retry on TransientError.

## Risk Mitigation

- Add retry logic with exponential backoff for remaining transient errors
- Monitor batch sizes (log nodes/edges per chunk)
- Ensure indexes exist on `Entity.id` and relationship identifying properties

## Notes

- No changes to external APIs or interfaces
- Backward compatible with existing data
- Performance improvement expected from reduced transaction overhead

## Open Questions

1. How to handle APOC dependency? (May need guard or pure-Cypher alternative)
2. Should node descriptions continue concatenating unboundedly? Might need summarization if they become huge.
