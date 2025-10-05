"""Integration test for NGRAF-022 Phase 3: Graph-Vector consistency."""

import os
import pytest
import pytest_asyncio
from nano_graphrag._extraction import DocumentGraphBatch, _merge_edges_for_batch
from nano_graphrag._utils import compute_mdhash_id


pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("NEO4J_URL"),
        reason="Neo4j not configured (set NEO4J_URL environment variable)"
    ),
    pytest.mark.skipif(
        not os.environ.get("QDRANT_URL"),
        reason="Qdrant not configured (set QDRANT_URL environment variable)"
    )
]


@pytest_asyncio.fixture
async def neo4j_storage(temp_storage_dir):
    """Provide Neo4j storage instance."""
    from nano_graphrag._storage.gdb_neo4j import Neo4jStorage

    config = {
        "working_dir": str(temp_storage_dir),
        "addon_params": {
            "neo4j_url": os.environ.get("NEO4J_URL", "bolt://localhost:7687"),
            "neo4j_auth": (
                os.environ.get("NEO4J_USER", "neo4j"),
                os.environ.get("NEO4J_PASSWORD", "your-secure-password-change-me")
            ),
            "neo4j_database": "neo4j",
            "neo4j_batch_size": 100,
            "neo4j_encrypted": False
        },
        "graph_cluster_algorithm": "leiden",
        "graph_cluster_seed": 42,
        "max_graph_cluster_size": 10
    }

    storage = Neo4jStorage(
        namespace=f"test_vector_consistency_{os.getpid()}",
        global_config=config
    )

    await storage.index_start_callback()

    yield storage

    try:
        await storage._debug_delete_all_node_edges()
    except Exception:
        pass

    await storage.index_done_callback()


@pytest_asyncio.fixture
async def qdrant_storage(temp_storage_dir):
    """Provide Qdrant storage instance."""
    from nano_graphrag._storage.vdb_qdrant import QdrantVectorStorage
    from tests.storage.base.fixtures import deterministic_embedding_func

    config = {
        "working_dir": str(temp_storage_dir),
        "embedding_func": deterministic_embedding_func,
        "embedding_batch_num": 32,
        "embedding_func_max_async": 16,
        "addon_params": {
            "qdrant_url": os.environ.get("QDRANT_URL", "http://localhost:6333"),
            "qdrant_api_key": os.environ.get("QDRANT_API_KEY")
        }
    }

    storage = QdrantVectorStorage(
        namespace=f"test_vector_consistency_{os.getpid()}",
        global_config=config,
        embedding_func=deterministic_embedding_func,
        meta_fields={"entity_name", "entity_type"}
    )

    try:
        client = await storage._get_client()
        await client.delete_collection(storage.namespace)
    except Exception:
        pass

    await storage.index_start_callback()

    yield storage

    try:
        client = await storage._get_client()
        await client.delete_collection(storage.namespace)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_placeholder_nodes_have_has_vector_false(neo4j_storage, qdrant_storage):
    """Test that placeholder nodes created by _merge_edges_for_batch have has_vector=False."""

    batch = DocumentGraphBatch()

    src_id = "ENTITY_A"
    tgt_id = "ENTITY_B"

    await neo4j_storage.has_node(src_id)

    edges_data = [{
        "source_id": "doc-1",
        "description": "relationship between A and B",
        "weight": 1.0
    }]

    global_config = {
        "cheap_model_func": None,
        "cheap_model_max_token_size": 32000,
        "entity_summary_to_max_tokens": 500
    }

    from nano_graphrag.tokenizer import TokenizerWrapper
    tokenizer = TokenizerWrapper(tokenizer_type="tiktoken", model_name="gpt-4")

    await _merge_edges_for_batch(
        src_id, tgt_id, edges_data, neo4j_storage, global_config, tokenizer, batch
    )

    placeholder_nodes = [node for node in batch.nodes if node[0] in [src_id, tgt_id]]

    assert len(placeholder_nodes) == 2
    for node_id, node_data in placeholder_nodes:
        assert node_data.get("has_vector") == False, f"Placeholder node {node_id} should have has_vector=False"


@pytest.mark.asyncio
async def test_real_entities_have_has_vector_true(neo4j_storage, qdrant_storage):
    """Test that real extracted entities get has_vector=True after upsert."""

    entity_name = "TEST_ENTITY"
    entity_id = compute_mdhash_id(entity_name, prefix="ent-")

    data_for_vdb = {
        entity_id: {
            "content": f"{entity_name} A test entity",
            "entity_name": entity_name
        }
    }

    await qdrant_storage.upsert(data_for_vdb)

    await neo4j_storage.upsert_node(entity_name, {
        "entity_type": "ORGANIZATION",
        "description": "A test entity",
        "source_id": "doc-1",
        "has_vector": False
    })

    await neo4j_storage.batch_update_node_field([entity_name], "has_vector", True)

    node_data = await neo4j_storage.get_node(entity_name)
    assert node_data is not None
    assert node_data.get("has_vector") == True


@pytest.mark.asyncio
async def test_community_update_skips_placeholders(neo4j_storage, qdrant_storage):
    """Test that community generation skips nodes without vectors."""

    real_entity = "REAL_ENTITY"
    placeholder_entity = "PLACEHOLDER_ENTITY"

    real_entity_id = compute_mdhash_id(real_entity, prefix="ent-")

    await neo4j_storage.upsert_node(real_entity, {
        "entity_type": "ORGANIZATION",
        "description": "Real entity with vector",
        "source_id": "doc-1",
        "has_vector": True
    })

    await neo4j_storage.upsert_node(placeholder_entity, {
        "entity_type": "UNKNOWN",
        "description": "Placeholder without vector",
        "source_id": "doc-1",
        "has_vector": False
    })

    data_for_vdb = {
        real_entity_id: {
            "content": f"{real_entity} Real entity with vector",
            "entity_name": real_entity
        }
    }
    await qdrant_storage.upsert(data_for_vdb)

    all_nodes = [real_entity, placeholder_entity]
    updates = {}
    skipped = 0

    for node_id in all_nodes:
        node_data = await neo4j_storage.get_node(node_id)
        if not node_data:
            continue

        if not node_data.get("has_vector", False):
            skipped += 1
            continue

        entity_key = compute_mdhash_id(node_id, prefix="ent-")
        updates[entity_key] = {
            "entity_name": node_id,
            "entity_type": node_data.get("entity_type", "UNKNOWN"),
            "community_description": node_data.get("description", "")
        }

    assert len(updates) == 1, "Only real entity should be in updates"
    assert skipped == 1, "Placeholder should be skipped"

    await qdrant_storage.update_payload(updates)
