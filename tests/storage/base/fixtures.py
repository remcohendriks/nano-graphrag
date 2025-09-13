"""Shared fixtures and test data for storage testing."""

import hashlib
import pytest
import tempfile
import numpy as np
from pathlib import Path
from typing import Dict, Any, List
from nano_graphrag._utils import wrap_embedding_func_with_attrs


@wrap_embedding_func_with_attrs(embedding_dim=128, max_token_size=8192)
async def mock_embedding_func(texts: List[str]) -> np.ndarray:
    """Random embeddings for testing (non-deterministic)."""
    return np.random.rand(len(texts), 128)


@wrap_embedding_func_with_attrs(embedding_dim=128, max_token_size=8192)
async def deterministic_embedding_func(texts: List[str]) -> np.ndarray:
    """Semantic embeddings for testing - uses OpenAI if available, else keyword-based."""
    import os

    # Try to use real OpenAI embeddings if API key is available
    if os.getenv("OPENAI_API_KEY"):
        try:
            from nano_graphrag.llm.providers.openai import OpenAIProvider, OpenAIEmbedder

            # Use a small, cheap model for testing
            embedder = OpenAIEmbedder(
                model="text-embedding-3-small",
                dimensions=128  # Request 128 dimensions to match our test dim
            )

            response = await embedder.embed(texts)
            return np.array(response.embeddings)
        except Exception:
            # Fall back to keyword-based if OpenAI fails
            pass

    # Fallback: Keyword-based semantic embeddings for predictable tests
    embeddings = []
    for text in texts:
        # Create embedding based on word presence
        embedding = np.zeros(128)
        words = text.lower().split()

        # Important keywords for our tests
        keyword_indices = {
            'fruit': [0, 10, 20],
            'apple': [1, 11, 21],
            'banana': [2, 12, 22],
            'orange': [3, 13, 23],
            'citrus': [4, 14, 24],
            'red': [5, 15, 25],
            'yellow': [6, 16, 26],
            'vehicle': [30, 40, 50],
            'car': [31, 41, 51],
            'bike': [32, 42, 52],
            'transport': [33, 43, 53],
            'eco': [34, 44, 54]
        }

        # Set values based on keyword presence
        for word in words:
            if word in keyword_indices:
                for idx in keyword_indices[word]:
                    embedding[idx] = 1.0

        # Add small hash-based variation for uniqueness
        hash_obj = hashlib.md5(text.encode())
        seed = int(hash_obj.hexdigest()[:8], 16)
        np.random.seed(seed)
        embedding += np.random.rand(128) * 0.1

        # Normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        embeddings.append(embedding)

    return np.array(embeddings)


@pytest.fixture
def temp_storage_dir():
    """Temporary directory for storage tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_global_config(temp_storage_dir) -> Dict[str, Any]:
    """Mock global configuration for storage tests."""
    return {
        "working_dir": str(temp_storage_dir),
        "embedding_func": deterministic_embedding_func,
        "embedding_batch_num": 32,
        "embedding_func_max_async": 16,
        "addon_params": {
            "neo4j_url": "neo4j://localhost:7687",
            "neo4j_auth": ("neo4j", "password"),
            "neo4j_database": "neo4j",
            "qdrant_path": str(temp_storage_dir / "qdrant")
        },
        "vector_db_storage_cls_kwargs": {
            "ef_construction": 100,
            "M": 16,
            "ef_search": 50,
            "max_elements": 10000
        }
    }


@pytest.fixture
def standard_test_dataset() -> Dict[str, Any]:
    """Standard test dataset for all storage types."""
    return {
        "vectors": {
            "vec1": {
                "content": "apple fruit food",
                "metadata": {"type": "fruit", "category": "food"}
            },
            "vec2": {
                "content": "banana fruit yellow",
                "metadata": {"type": "fruit", "category": "food"}
            },
            "vec3": {
                "content": "car vehicle transport",
                "metadata": {"type": "vehicle", "category": "transport"}
            },
            "vec4": {
                "content": "bike vehicle eco",
                "metadata": {"type": "vehicle", "category": "transport"}
            },
            "vec5": {
                "content": "orange fruit citrus",
                "metadata": {"type": "fruit", "category": "food"}
            }
        },
        "nodes": {
            "person_alice": {
                "type": "Person",
                "name": "Alice",
                "age": "30",
                "occupation": "Engineer"
            },
            "person_bob": {
                "type": "Person",
                "name": "Bob",
                "age": "25",
                "occupation": "Designer"
            },
            "person_charlie": {
                "type": "Person",
                "name": "Charlie",
                "age": "35",
                "occupation": "Manager"
            },
            "org_acme": {
                "type": "Organization",
                "name": "ACME Corp",
                "industry": "Technology"
            },
            "org_xyz": {
                "type": "Organization",
                "name": "XYZ Inc",
                "industry": "Finance"
            }
        },
        "edges": [
            ("person_alice", "person_bob", {"relation": "knows", "since": "2020"}),
            ("person_bob", "person_charlie", {"relation": "knows", "since": "2019"}),
            ("person_alice", "org_acme", {"relation": "works_at", "role": "Senior Engineer"}),
            ("person_bob", "org_acme", {"relation": "works_at", "role": "Lead Designer"}),
            ("person_charlie", "org_xyz", {"relation": "works_at", "role": "Product Manager"})
        ],
        "kv_data": {
            "doc_001": {
                "title": "Document 1",
                "content": "This is the first test document.",
                "metadata": {"author": "Alice", "date": "2024-01-01"}
            },
            "doc_002": {
                "title": "Document 2",
                "content": "This is the second test document.",
                "metadata": {"author": "Bob", "date": "2024-01-02"}
            },
            "chunk_001": {
                "content": "First chunk of text",
                "doc_id": "doc_001",
                "chunk_index": 0
            },
            "chunk_002": {
                "content": "Second chunk of text",
                "doc_id": "doc_001",
                "chunk_index": 1
            },
            "report_001": {
                "community_id": "comm_1",
                "summary": "Community of software engineers",
                "entities": ["person_alice", "person_bob"]
            }
        }
    }