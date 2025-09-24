#!/usr/bin/env python3
"""Test to verify sparse embedding generation for entities."""

import asyncio
import json
from nano_graphrag.config import HybridSearchConfig
from nano_graphrag.llm.providers.sparse import SparseEmbeddingProvider

async def test_sparse_generation():
    # Test various entity descriptions
    test_contents = [
        "Executive Order 14282 focuses on biotechnology and biomanufacturing innovation",  # Rich content
        "John Smith (PERSON)",  # Simple entity description
        "Microsoft Corporation (ORGANIZATION)",  # Organization
        "New York (LOCATION)",  # Location
        "UNKNOWN",  # Minimal content
        "",  # Empty content
        " ",  # Whitespace only
        "(UNKNOWN)",  # Just type
    ]

    config = HybridSearchConfig(enabled=True)
    provider = SparseEmbeddingProvider(config=config)

    print("Testing sparse embedding generation for different entity content:")
    print("=" * 60)

    results = await provider.embed(test_contents)

    for i, (content, sparse) in enumerate(zip(test_contents, results)):
        num_indices = len(sparse.get("indices", []))
        print(f"\n{i+1}. Content: '{content[:50]}{'...' if len(content) > 50 else ''}'")
        print(f"   Non-zero dimensions: {num_indices}")
        if num_indices > 0:
            print(f"   First 5 indices: {sparse['indices'][:5]}")
            print(f"   First 5 values: {[f'{v:.3f}' for v in sparse['values'][:5]]}")
        else:
            print("   WARNING: Empty sparse vector!")

    # Count empty vectors
    empty_count = sum(1 for r in results if len(r.get("indices", [])) == 0)
    print(f"\n" + "=" * 60)
    print(f"Summary: {empty_count}/{len(test_contents)} produced empty sparse vectors")

    # Test with actual entity descriptions from community generation
    entity_descriptions = [
        "John Doe (PERSON)",
        "Jane Smith is a researcher (PERSON)",
        "Department of Defense (ORGANIZATION)",
        "Washington D.C. (LOCATION)",
        "Biden Administration (ORGANIZATION)",
        "AI technology conference (EVENT)",
    ]

    print("\n\nTesting typical entity descriptions after community generation:")
    print("=" * 60)

    results = await provider.embed(entity_descriptions)

    for content, sparse in zip(entity_descriptions, results):
        num_indices = len(sparse.get("indices", []))
        status = "✓" if num_indices > 0 else "✗ EMPTY"
        print(f"{status} '{content}' -> {num_indices} non-zero dims")

if __name__ == "__main__":
    asyncio.run(test_sparse_generation())