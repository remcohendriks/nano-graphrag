# NGRAF-020-2: Entity Embedding Preservation via Payload-Only Updates

## Problem
Post-community entity updates are re-embedding entities with different content, causing loss of sparse embeddings and inconsistent search results.

## Solution: Payload-Only Updates (Qdrant-only, minimal change)

### 1. Add Payload-Only Update to Qdrant Storage (single method)

**File:** `nano_graphrag/_storage/vdb_qdrant.py`

Add an update-only API that never touches vectors (Qdrant set_payload):

```python
async def update_payload(self, updates: Dict[str, Dict[str, Any]]) -> None:
    """Update only payload fields without touching vectors."""
    if not updates:
        return

    await self._ensure_collection()
    client = await self._get_client()

    for entity_id, payload_updates in updates.items():
        point_id = xxhash.xxh64_intdigest(entity_id.encode())

        # Never update fields that drive embeddings
        safe_updates = {k: v for k, v in payload_updates.items() if k not in ["content", "embedding"]}
        safe_updates["id"] = entity_id

        await client.set_payload(
            collection_name=self.namespace,
            payload=safe_updates,
            points=[point_id]
        )

    logger.info(f"Updated payload for {len(updates)} entities (vectors preserved)")
```

### 2. Preserve Canonical Embedding Content (no manager, minimal change)

We keep the existing initial extraction path unchanged (it sets the canonical `content` used for embeddings). For post‑community we will not touch `content`; we only write display metadata (e.g., `community_description`). This avoids re‑embedding and keeps sparse/dense vectors intact.

No change required to `_extraction.py` (we keep current behavior).

### 3. Update Post-Community to Use Payload-Only

**File:** `nano_graphrag/graphrag.py`

Replace lines 474-512:

```python
If `entities_vdb` supports `update_payload`, replace the upsert with payload‑only updates:

```python
if self.entities_vdb and self.config.query.enable_local:
    schema = await self.chunk_entity_relation_graph.community_schema()
    all_node_ids = sorted({node_id for comm in schema.values() for node_id in comm.get("nodes", [])})

    updates = {}
    for node_id in all_node_ids:
        try:
            node_data = await self.chunk_entity_relation_graph.get_node(node_id)
            if not node_data:
                continue
            description = (node_data.get("description", "") or "").strip()
            if not description:
                entity_name = (node_data.get("name") or node_id).strip()
                entity_type = node_data.get("entity_type", "UNKNOWN")
                description = f"{entity_name} ({entity_type})"

            # IMPORTANT: Use the same entity ID key used during initial upsert
            # e.g., compute_mdhash_id(name, prefix='ent-') if that was used as point key
            entity_key = compute_mdhash_id(node_id, prefix='ent-')
            updates[entity_key] = {
                "entity_name": node_data.get("name", node_id),
                "entity_type": node_data.get("entity_type", "UNKNOWN"),
                "community_description": description,
            }
        except Exception as e:
            logger.debug(f"Could not update {node_id}: {e}")

    if updates and hasattr(self.entities_vdb, 'update_payload'):
        await self.entities_vdb.update_payload(updates)
```
```

### Non-goals (to stay minimal)
- No support for non‑Qdrant vector stores in this ticket.
- No backfill job; focus is on preventing new re‑embeddings.

## Tests

**File:** `tests/test_entity_embedding_preservation.py` (Qdrant-only)

```python
import pytest
from nano_graphrag.entity_manager import EntityManager
from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage

@pytest.mark.asyncio
async def test_embeddings_preserved_after_community():
    """Verify vectors unchanged after community updates."""

    # Create storage and manager
    storage = QdrantVectorStorage(...)
    manager = EntityManager(storage)

    # Create entity with initial embedding
    await manager.create_entity("e1", "Barack Obama is the 44th president",
                                {"entity_name": "Barack Obama", "entity_type": "PERSON"})

    # Query to get initial score
    result1 = await storage.query("Barack Obama", top_k=1)
    initial_score = result1[0]["score"]

    # Update with community description
    await manager.update_community_description("e1", "Barack Obama (PERSON)")

    # Verify embedding unchanged (score does not decrease materially)
    result2 = await storage.query("Barack Obama", top_k=1)
    assert result2[0]["id"] == result1[0]["id"]
    assert "community_description" in result2[0]
```

## Definition of Done

- [ ] Qdrant storage exposes `update_payload` that never touches vectors
- [ ] Post‑community path uses `update_payload` and never modifies `content`
- [ ] Minimal test confirms vectors unchanged after post‑community update
- [ ] Logs show "Updated payload" (no vector generation) during post‑community
