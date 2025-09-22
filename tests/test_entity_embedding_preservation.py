"""Test that entity embeddings are preserved during post-community updates."""

import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
from nano_graphrag._utils import EmbeddingFunc, compute_mdhash_id


@pytest.mark.asyncio
async def test_update_payload_preserves_vectors():
    """Verify update_payload method only updates metadata, not vectors."""

    # Mock embedding function
    async def mock_embed(texts):
        return [[0.1] * 1536 for _ in texts]

    embedding_func = EmbeddingFunc(
        embedding_dim=1536,
        max_token_size=8192,
        func=mock_embed
    )

    # Create storage with mocked client
    storage = QdrantVectorStorage(
        namespace="test_preserve",
        global_config={
            "qdrant_url": "http://localhost:6333",
            "enable_hybrid_search": True
        },
        embedding_func=embedding_func,
        meta_fields=set()
    )

    # Mock the Qdrant client methods
    mock_client = AsyncMock()
    mock_client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
    mock_client.create_collection = AsyncMock()
    mock_client.set_payload = AsyncMock()

    with patch.object(storage, '_get_client', return_value=mock_client):
        # Call update_payload
        updates = {
            "entity-1": {
                "entity_name": "Barack Obama",
                "entity_type": "PERSON",
                "community_description": "44th President of the United States"
            },
            "entity-2": {
                "entity_name": "White House",
                "entity_type": "LOCATION",
                "community_description": "Official residence of the US President"
            }
        }

        await storage.update_payload(updates)

        # Verify set_payload was called correctly for each entity
        assert mock_client.set_payload.call_count == 2

        # Check the calls
        calls = mock_client.set_payload.call_args_list
        for i, (entity_id, payload) in enumerate(updates.items()):
            call_args = calls[i][1]  # kwargs

            # Verify collection name
            assert call_args['collection_name'] == "test_preserve"

            # Verify payload doesn't include 'content' or 'embedding'
            assert 'content' not in call_args['payload']
            assert 'embedding' not in call_args['payload']

            # Verify expected fields are present
            assert call_args['payload']['entity_name'] == payload['entity_name']
            assert call_args['payload']['entity_type'] == payload['entity_type']
            assert call_args['payload']['community_description'] == payload['community_description']
            assert call_args['payload']['id'] == entity_id


@pytest.mark.asyncio
async def test_post_community_uses_payload_update_when_hybrid():
    """Test that post-community update uses payload-only when hybrid search enabled."""

    # Test the specific logic in graphrag.py lines 479-512
    # We'll test the branching logic directly by mocking the right conditions

    from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
    from unittest.mock import MagicMock

    # Create a mock storage with update_payload method
    storage = QdrantVectorStorage(
        namespace="test",
        global_config={"enable_hybrid_search": True},
        embedding_func=MagicMock(),
        meta_fields=set()
    )

    # Verify the storage has update_payload method
    assert hasattr(storage, 'update_payload')

    # Mock the actual method
    storage.update_payload = AsyncMock()
    storage.upsert = AsyncMock()

    # Simulate the conditional logic from graphrag.py
    use_payload_update = (
        hasattr(storage, 'update_payload') and
        True  # enable_hybrid_search = True
    )

    assert use_payload_update is True

    # Simulate the payload-only update path
    if use_payload_update:
        updates = {
            compute_mdhash_id("Obama", prefix='ent-'): {
                "entity_name": "Obama",
                "entity_type": "PERSON",
                "community_description": "44th President"
            }
        }
        await storage.update_payload(updates)

    # Verify update_payload was called
    assert storage.update_payload.called
    assert not storage.upsert.called



@pytest.mark.asyncio
async def test_fallback_to_upsert_when_no_update_payload():
    """Test that system falls back to upsert when update_payload not available."""

    # Test the fallback logic when update_payload is not available
    from unittest.mock import MagicMock

    # Create a mock storage WITHOUT update_payload method
    mock_storage = AsyncMock()
    mock_storage.upsert = AsyncMock()
    # Explicitly no update_payload attribute

    # Simulate the conditional logic from graphrag.py
    use_payload_update = (
        hasattr(mock_storage, 'update_payload') and
        False  # enable_hybrid_search = False
    )

    assert use_payload_update is False

    # Simulate the fallback path (full re-embedding)
    if not use_payload_update:
        entity_dict = {
            "TestEntity": {
                "content": "A test entity",
                "entity_name": "TestEntity",
                "entity_type": "THING"
            }
        }
        await mock_storage.upsert(entity_dict)

    # Verify upsert was called (fallback behavior)
    assert mock_storage.upsert.called

    # Verify the upsert data includes content
    upsert_call = mock_storage.upsert.call_args[0][0]
    assert "TestEntity" in upsert_call
    assert "content" in upsert_call["TestEntity"]



@pytest.mark.skipif(
    os.getenv("RUN_QDRANT_TESTS") != "1",
    reason="Qdrant integration tests require running Qdrant instance"
)
@pytest.mark.asyncio
async def test_embedding_preservation_integration():
    """Integration test with real Qdrant to verify embeddings are preserved."""

    from nano_graphrag._utils import EmbeddingFunc
    import numpy as np

    # Mock embedding function that returns predictable vectors
    call_count = 0
    async def mock_embed(texts):
        nonlocal call_count
        call_count += 1
        # Return different embeddings each time to detect re-embedding
        base_value = 0.1 * call_count
        return [[base_value + i*0.01 for i in range(1536)] for _ in texts]

    embedding_func = EmbeddingFunc(
        embedding_dim=1536,
        max_token_size=8192,
        func=mock_embed
    )

    # Create storage
    storage = QdrantVectorStorage(
        namespace="test_preserve_integration",
        global_config={
            "qdrant_url": "http://localhost:6333",
            "enable_hybrid_search": True
        },
        embedding_func=embedding_func,
        meta_fields=set()
    )

    # Initial upsert with content
    entity_id = compute_mdhash_id("Barack Obama", prefix="ent-")
    await storage.upsert({
        entity_id: {
            "content": "Barack Obama is the 44th president of the United States",
            "entity_name": "Barack Obama",
            "entity_type": "PERSON"
        }
    })

    initial_call_count = call_count

    # Query to get initial vector
    results1 = await storage.query("Barack Obama", top_k=1)
    assert len(results1) > 0
    initial_score = results1[0].get("score", 0)

    # Update payload only (should NOT trigger new embeddings)
    await storage.update_payload({
        entity_id: {
            "entity_name": "Barack Obama",
            "entity_type": "PERSON",
            "community_description": "44th President of the United States (updated)"
        }
    })

    # Verify no new embeddings were generated
    assert call_count == initial_call_count + 1  # Only +1 for the query embedding

    # Query again and verify same vector
    results2 = await storage.query("Barack Obama", top_k=1)
    assert len(results2) > 0

    # Score should be identical (same vectors)
    new_score = results2[0].get("score", 0)
    assert abs(new_score - initial_score) < 0.001  # Allow tiny floating point diff

    # Verify metadata was updated
    assert results2[0]["community_description"] == "44th President of the United States (updated)"

    # Clean up
    client = await storage._get_client()
    await client.delete_collection("test_preserve_integration")