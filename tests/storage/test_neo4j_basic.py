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
            "neo4j_url": "neo4j://localhost:7687",
            "neo4j_auth": ("neo4j", "testpassword"),
            "neo4j_database": "neo4j"
        },
        "working_dir": "./test_neo4j"
    }
    
    with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.neo4j') as mock_neo4j:
        # Mock the driver
        mock_driver = AsyncMock()
        mock_neo4j.AsyncGraphDatabase.driver.return_value = mock_driver
        
        storage = Neo4jStorage(namespace="test", global_config=config)
        
        assert storage.neo4j_url == "neo4j://localhost:7687"
        assert storage.neo4j_auth == ("neo4j", "testpassword")
        assert storage.neo4j_database == "neo4j"
        assert "test_neo4j" in storage.namespace


@pytest.mark.asyncio
async def test_constraint_creation():
    """Test that constraints are created properly."""
    config = {
        "addon_params": {
            "neo4j_url": "neo4j://localhost:7687",
            "neo4j_auth": ("neo4j", "testpassword"),
            "neo4j_database": "neo4j"
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
            "neo4j_url": "neo4j://localhost:7687",
            "neo4j_auth": ("neo4j", "testpassword"),
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
            "neo4j_url": "neo4j://localhost:7687",
            "neo4j_auth": ("neo4j", "testpassword"),
            "neo4j_database": "neo4j"
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
            "neo4j_url": "neo4j://localhost:7687",
            "neo4j_auth": ("neo4j", "testpassword"),
            "neo4j_database": "neo4j"
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