#!/usr/bin/env python3
"""
Test script to verify NGRAF-020-2 implementation.
This validates that entity embeddings are preserved after community generation.
"""

import asyncio
import os
import sys
from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
from nano_graphrag._utils import EmbeddingFunc, compute_mdhash_id


async def test_embedding_preservation():
    """Test that embeddings are preserved with payload-only updates."""

    print("Testing NGRAF-020-2: Entity Embedding Preservation")
    print("=" * 60)

    # Mock embedding function to track calls
    embed_call_count = 0

    async def mock_embed(texts):
        nonlocal embed_call_count
        embed_call_count += 1
        print(f"Embedding call #{embed_call_count} for {len(texts)} texts")
        # Return different values each time to detect re-embedding
        return [[0.1 * embed_call_count + i*0.01 for i in range(100)] for _ in texts]

    embedding_func = EmbeddingFunc(
        embedding_dim=100,
        max_token_size=8192,
        func=mock_embed
    )

    # Create storage with hybrid search enabled
    storage = QdrantVectorStorage(
        namespace="test_ngraf_020_2",
        global_config={
            "qdrant_url": os.getenv("QDRANT_URL", "http://localhost:6333"),
            "enable_hybrid_search": True
        },
        embedding_func=embedding_func,
        meta_fields=set()
    )

    print("\n1. Initial entity insertion with embeddings...")
    entity_id = compute_mdhash_id("Barack Obama", prefix="ent-")

    await storage.upsert({
        entity_id: {
            "content": "Barack Obama is the 44th president of the United States",
            "entity_name": "Barack Obama",
            "entity_type": "PERSON"
        }
    })

    initial_embed_count = embed_call_count
    print(f"   Initial embeddings created: {initial_embed_count}")

    print("\n2. Simulating post-community payload update...")
    await storage.update_payload({
        entity_id: {
            "entity_name": "Barack Obama",
            "entity_type": "PERSON",
            "community_description": "44th President (PERSON) - Leader of community"
        }
    })

    print(f"   Embeddings after update: {embed_call_count}")

    # Verify no new embeddings were generated
    if embed_call_count == initial_embed_count:
        print("   ✅ SUCCESS: No new embeddings generated (vectors preserved)")
    else:
        print(f"   ❌ FAILURE: New embeddings generated ({embed_call_count - initial_embed_count} extra)")
        return False

    print("\n3. Querying to verify metadata update...")
    results = await storage.query("Barack Obama", top_k=1)

    if results and "community_description" in results[0]:
        print(f"   ✅ SUCCESS: Metadata updated: {results[0]['community_description']}")
    else:
        print("   ❌ FAILURE: Metadata not updated")
        return False

    # Clean up
    try:
        client = await storage._get_client()
        await client.delete_collection("test_ngraf_020_2")
        print("\n4. Cleanup completed")
    except:
        pass

    print("\n" + "=" * 60)
    print("✅ All tests passed! NGRAF-020-2 implementation is working correctly.")
    return True


if __name__ == "__main__":
    # Check if Qdrant is available
    import httpx

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")

    try:
        response = httpx.get(f"{qdrant_url}/collections")
        if response.status_code != 200:
            print(f"⚠️  Warning: Qdrant not accessible at {qdrant_url}")
            print("   Skipping integration test. To run, ensure Qdrant is running.")
            sys.exit(0)
    except:
        print(f"⚠️  Warning: Cannot connect to Qdrant at {qdrant_url}")
        print("   Skipping integration test. To run, start Qdrant with:")
        print("   docker run -p 6333:6333 qdrant/qdrant")
        sys.exit(0)

    # Run the test
    success = asyncio.run(test_embedding_preservation())
    sys.exit(0 if success else 1)