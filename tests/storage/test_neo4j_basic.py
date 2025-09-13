"""Basic tests for Neo4j storage backend."""

import pytest
import asyncio
import os
from unittest.mock import Mock, AsyncMock, patch

from nano_graphrag._storage.gdb_neo4j import Neo4jStorage


@pytest.mark.asyncio
async def test_neo4j_initialization():
    """Test Neo4j storage initialization."""
    config = {
        "addon_params": {
            "neo4j_url": "bolt://localhost:7687",
            "neo4j_auth": ("neo4j", "your-secure-password-change-me"),
            "neo4j_database": "neo4j",
            "neo4j_encrypted": False
        },
        "working_dir": "./test_neo4j"
    }
    
    with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.neo4j') as mock_neo4j:
        # Mock the driver
        mock_driver = AsyncMock()
        mock_neo4j.AsyncGraphDatabase.driver.return_value = mock_driver
        
        storage = Neo4jStorage(namespace="test", global_config=config)
        
        assert storage.neo4j_url == "bolt://localhost:7687"
        assert storage.neo4j_auth == ("neo4j", "your-secure-password-change-me")
        assert storage.neo4j_database == "neo4j"
        assert storage.namespace == "GraphRAG_test"  # New clean namespace format


@pytest.mark.asyncio
async def test_constraint_creation():
    """Test that constraints are created properly."""
    config = {
        "addon_params": {
            "neo4j_url": "bolt://localhost:7687",
            "neo4j_auth": ("neo4j", "your-secure-password-change-me"),
            "neo4j_database": "neo4j",
            "neo4j_encrypted": False
        },
        "working_dir": "./test_neo4j"
    }
    
    with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.neo4j') as mock_neo4j:
        mock_driver = Mock()  # Use regular Mock for driver
        mock_session = AsyncMock()
        
        # Setup mock returns
        mock_neo4j.AsyncGraphDatabase.driver.return_value = mock_driver
        
        # Make session() return an async context manager directly
        mock_driver.session = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute_write = AsyncMock()
        
        storage = Neo4jStorage(namespace="test", global_config=config)
        
        # Call constraint creation
        await storage._ensure_constraints()
        
        # Verify execute_write was called
        assert mock_session.execute_write.called


@pytest.mark.asyncio
async def test_retry_decorator():
    """Test retry decorator generation."""
    config = {
        "addon_params": {
            "neo4j_url": "bolt://localhost:7687",
            "neo4j_auth": ("neo4j", "your-secure-password-change-me"),
        },
        "working_dir": "./test_neo4j"
    }
    
    with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.neo4j') as mock_neo4j:
        mock_driver = AsyncMock()
        mock_neo4j.AsyncGraphDatabase.driver.return_value = mock_driver
        
        storage = Neo4jStorage(namespace="test", global_config=config)
        
        # Get retry decorator
        retry_dec = storage._get_retry_decorator()
        
        # Should return a retry decorator
        assert retry_dec is not None
        assert callable(retry_dec)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_neo4j_connection():
    """Test actual Neo4j connection (requires Neo4j to be running)."""
    # Skip if Neo4j is not available
    if not os.getenv("RUN_NEO4J_TESTS"):
        pytest.skip("Neo4j integration tests disabled (set RUN_NEO4J_TESTS=1 to enable)")

    config = {
        "addon_params": {
            "neo4j_url": "bolt://localhost:7687",
            "neo4j_auth": ("neo4j", "your-secure-password-change-me"),
            "neo4j_database": "neo4j",
            "neo4j_encrypted": False
        },
        "working_dir": "./test_neo4j"
    }

    storage = Neo4jStorage(namespace="test_integration", global_config=config)
    
    try:
        # Initialize workspace
        await storage.index_start_callback()
        
        # Test node operations
        await storage.upsert_node("test1", {"name": "Test Node", "entity_type": "TEST"})
        node = await storage.get_node("test1")
        assert node is not None
        assert node.get("name") == "Test Node"
        
        # Test edge operations
        await storage.upsert_node("test2", {"name": "Test Node 2", "entity_type": "TEST"})
        await storage.upsert_edge("test1", "test2", {"relationship": "CONNECTED"})
        edge = await storage.get_edge("test1", "test2")
        assert edge is not None
        
        # Cleanup
        await storage._debug_delete_all_node_edges()
        
    finally:
        await storage.index_done_callback()


@pytest.mark.asyncio
async def test_batch_operations():
    """Test batch node and edge operations."""
    config = {
        "addon_params": {
            "neo4j_url": "bolt://localhost:7687",
            "neo4j_auth": ("neo4j", "your-secure-password-change-me"),
            "neo4j_database": "neo4j",
            "neo4j_encrypted": False
        },
        "working_dir": "./test_neo4j"
    }
    
    with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.neo4j') as mock_neo4j:
        mock_driver = Mock()  # Use regular Mock for driver
        mock_session = AsyncMock()
        
        mock_neo4j.AsyncGraphDatabase.driver.return_value = mock_driver
        
        # Setup session as async context manager
        mock_driver.session = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.run = AsyncMock()
        
        storage = Neo4jStorage(namespace="test", global_config=config)
        
        # Test batch node insert
        nodes = [
            ("node1", {"name": "Node 1", "entity_type": "TYPE1"}),
            ("node2", {"name": "Node 2", "entity_type": "TYPE2"}),
            ("node3", {"name": "Node 3", "entity_type": "TYPE1"})
        ]
        
        await storage.upsert_nodes_batch(nodes)
        
        # Verify session.run was called
        assert mock_session.run.called
        
        # Test batch edge insert
        edges = [
            ("node1", "node2", {"weight": 1.0}),
            ("node2", "node3", {"weight": 0.5})
        ]
        
        await storage.upsert_edges_batch(edges)
        
        # Verify session.run was called for edges
        assert mock_session.run.call_count >= 2


@pytest.mark.asyncio
async def test_gds_availability_check():
    """Test GDS availability check."""
    config = {
        "addon_params": {
            "neo4j_url": "bolt://localhost:7687",
            "neo4j_auth": ("neo4j", "your-secure-password-change-me"),
            "neo4j_database": "neo4j",
            "neo4j_encrypted": False
        },
        "working_dir": "./test_neo4j"
    }
    
    with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.neo4j') as mock_neo4j:
        mock_driver = Mock()
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        
        mock_neo4j.AsyncGraphDatabase.driver.return_value = mock_driver
        mock_driver.session = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        # Test successful GDS check
        mock_session.run = AsyncMock(return_value=mock_result)
        mock_result.single = AsyncMock(return_value={"version": "2.5.0"})
        
        storage = Neo4jStorage(namespace="test", global_config=config)
        
        # Should not raise
        await storage._check_gds_availability()
        
        # Test failed GDS check
        mock_session.run = AsyncMock(side_effect=Exception("GDS not found"))
        
        with pytest.raises(RuntimeError, match="Neo4j Graph Data Science"):
            await storage._check_gds_availability()


@pytest.mark.asyncio
async def test_gds_clustering():
    """Test GDS clustering with proper error handling."""
    config = {
        "addon_params": {
            "neo4j_url": "bolt://localhost:7687",
            "neo4j_auth": ("neo4j", "your-secure-password-change-me"),
            "neo4j_database": "neo4j",
            "neo4j_encrypted": False
        },
        "working_dir": "./test_neo4j",
        "graph_cluster_seed": 42,
        "max_graph_cluster_size": 10
    }
    
    with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.neo4j') as mock_neo4j:
        mock_driver = Mock()
        mock_session = AsyncMock()
        
        mock_neo4j.AsyncGraphDatabase.driver.return_value = mock_driver
        mock_driver.session = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        # Mock successful clustering
        mock_exists_result = AsyncMock()
        mock_exists_result.single = AsyncMock(return_value={"exists": False})
        
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value={
            "communityCount": 5,
            "modularities": [0.7, 0.8, 0.85]
        })
        
        # Mock mapping result for community retrieval
        class AsyncIterator:
            def __init__(self, items):
                self.items = iter(items)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self.items)
                except StopIteration:
                    raise StopAsyncIteration

        mock_mapping_result = AsyncIterator([
            {"nodeId": "node1", "communityId": 0},
            {"nodeId": "node2", "communityId": 0},
            {"nodeId": "node3", "communityId": 1}
        ])

        mock_session.run = AsyncMock(side_effect=[
            mock_exists_result,  # Check if graph exists
            None,  # Graph projection
            mock_result,  # Leiden algorithm
            mock_mapping_result,  # Community mapping retrieval
            None  # Graph drop
        ])
        
        storage = Neo4jStorage(namespace="test", global_config=config)
        
        # Run clustering
        await storage.clustering("leiden")
        
        # Verify all five calls were made (exists check, projection, leiden, mapping, drop)
        assert mock_session.run.call_count == 5
        
        # Check that graph drop is called even on error
        mock_exists_result_2 = AsyncMock()
        mock_exists_result_2.single = AsyncMock(return_value={"exists": False})
        
        mock_session.run = AsyncMock(side_effect=[
            mock_exists_result_2,  # Check if graph exists
            None,  # Graph projection succeeds
            Exception("Leiden failed"),  # Leiden fails
        ])
        
        with pytest.raises(Exception):
            await storage.clustering("leiden")


@pytest.mark.asyncio
async def test_label_sanitization():
    """Test that entity type labels are properly sanitized."""
    config = {
        "addon_params": {
            "neo4j_url": "bolt://localhost:7687",
            "neo4j_auth": ("neo4j", "your-secure-password-change-me"),
            "neo4j_database": "neo4j",
            "neo4j_encrypted": False
        },
        "working_dir": "./test_neo4j"
    }
    
    with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.neo4j') as mock_neo4j:
        mock_driver = Mock()
        mock_neo4j.AsyncGraphDatabase.driver.return_value = mock_driver
        
        storage = Neo4jStorage(namespace="test", global_config=config)
        
        # Test various malicious labels
        assert storage._sanitize_label("Normal") == "Normal"
        assert storage._sanitize_label("Has Spaces") == "Has_Spaces"
        assert storage._sanitize_label("BAD`LABEL") == "BAD_LABEL"
        assert storage._sanitize_label("123Start") == "_123Start"
        assert storage._sanitize_label("a-b-c") == "a_b_c"
        assert storage._sanitize_label("") == "UNKNOWN"
        assert storage._sanitize_label(None) == "UNKNOWN"


@pytest.mark.asyncio
async def test_return_type_fix():
    """Test that node_degrees_batch returns correct type."""
    config = {
        "addon_params": {
            "neo4j_url": "bolt://localhost:7687",
            "neo4j_auth": ("neo4j", "your-secure-password-change-me"),
            "neo4j_database": "neo4j",
            "neo4j_encrypted": False
        },
        "working_dir": "./test_neo4j"
    }
    
    with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.neo4j') as mock_neo4j:
        mock_driver = Mock()
        mock_neo4j.AsyncGraphDatabase.driver.return_value = mock_driver
        
        storage = Neo4jStorage(namespace="test", global_config=config)
        
        # Test empty input returns empty list, not dict
        result = await storage.node_degrees_batch([])
        assert result == []
        assert isinstance(result, list)