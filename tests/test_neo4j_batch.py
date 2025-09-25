"""Unit tests for Neo4j batch transaction functionality (NGRAF-022)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nano_graphrag._extraction import DocumentGraphBatch
from nano_graphrag._storage.gdb_neo4j import Neo4jStorage
from nano_graphrag.prompt import GRAPH_FIELD_SEP


@pytest.fixture
def mock_neo4j_storage():
    """Create a mock Neo4j storage instance."""
    # Create with minimal config
    global_config = {
        "addon_params": {
            "neo4j_url": "neo4j://localhost",
            "neo4j_auth": ("neo4j", "password"),
            "neo4j_database": "neo4j"
        }
    }

    with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.__post_init__'):
        storage = Neo4jStorage(
            namespace="test",
            global_config=global_config
        )
        storage.neo4j_url = "neo4j://localhost"
        storage.neo4j_auth = ("neo4j", "password")
        storage.neo4j_database = "neo4j"

        # Mock the driver
        storage.async_driver = AsyncMock()
        storage._sanitize_label = lambda x: x.replace(" ", "_").replace("-", "_")

        return storage


class TestDocumentGraphBatch:
    """Test DocumentGraphBatch accumulator class."""

    def test_batch_creation(self):
        """Test batch can be created and items added."""
        batch = DocumentGraphBatch()

        # Add nodes
        batch.add_node("entity1", {"entity_type": "Person", "description": "Alice"})
        batch.add_node("entity2", {"entity_type": "Person", "description": "Bob"})

        # Add edges
        batch.add_edge("entity1", "entity2", {"weight": 1.0, "description": "knows"})

        assert len(batch.nodes) == 2
        assert len(batch.edges) == 1
        assert batch.nodes[0] == ("entity1", {"entity_type": "Person", "description": "Alice"})
        assert batch.edges[0] == ("entity1", "entity2", {"weight": 1.0, "description": "knows"})

    def test_batch_chunking(self):
        """Test batch can be chunked into smaller batches."""
        batch = DocumentGraphBatch()

        # Add 25 nodes
        for i in range(25):
            batch.add_node(f"entity{i}", {"entity_type": "Entity", "description": f"Entity {i}"})

        # Add 15 edges
        for i in range(15):
            batch.add_edge(f"entity{i}", f"entity{i+1}", {"weight": 1.0})

        # Chunk with max_size=10
        chunks = batch.chunk(max_size=10)

        assert len(chunks) == 3  # Should create 3 chunks
        assert len(chunks[0].nodes) == 10
        assert len(chunks[0].edges) == 10
        assert len(chunks[1].nodes) == 10
        assert len(chunks[1].edges) == 5
        assert len(chunks[2].nodes) == 5
        assert len(chunks[2].edges) == 0

    def test_empty_batch_chunking(self):
        """Test empty batch returns single empty chunk."""
        batch = DocumentGraphBatch()
        chunks = batch.chunk(max_size=10)

        assert len(chunks) == 1
        assert len(chunks[0].nodes) == 0
        assert len(chunks[0].edges) == 0


class TestNeo4jBatchTransaction:
    """Test Neo4j batch transaction implementation."""

    @pytest.mark.asyncio
    async def test_execute_document_batch(self, mock_neo4j_storage):
        """Test batch execution with nodes and edges."""
        storage = mock_neo4j_storage

        # Create batch with nodes and edges
        batch = DocumentGraphBatch()
        batch.add_node("alice", {"entity_type": "Person", "description": "Alice", "source_id": "doc1"})
        batch.add_node("bob", {"entity_type": "Person", "description": "Bob", "source_id": "doc1"})
        batch.add_edge("alice", "bob", {"weight": 1.0, "description": "knows", "source_id": "doc1"})

        # Mock session and transaction with proper async context manager protocol
        mock_tx = AsyncMock()
        mock_tx.commit = AsyncMock()
        mock_tx.rollback = AsyncMock()
        mock_tx.run = AsyncMock()

        mock_session = AsyncMock()
        mock_session.begin_transaction = MagicMock()
        mock_session.begin_transaction.return_value.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_session.begin_transaction.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock the session factory to return async context manager
        session_factory = MagicMock()
        session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        storage.async_driver.session = MagicMock(return_value=session_factory.return_value)

        # Execute batch
        await storage.execute_document_batch(batch)

        # Verify transaction was used
        mock_session.begin_transaction.assert_called_once()
        mock_tx.commit.assert_called_once()

        # Verify queries were executed (at least 1 for nodes, 1 for edges)
        assert mock_tx.run.call_count >= 2

    @pytest.mark.asyncio
    async def test_batch_with_bidirectional_edges(self, mock_neo4j_storage):
        """Test batch handles bidirectional edges without deadlock."""
        storage = mock_neo4j_storage

        batch = DocumentGraphBatch()
        batch.add_node("alice", {"entity_type": "Person", "description": "Alice"})
        batch.add_node("bob", {"entity_type": "Person", "description": "Bob"})
        batch.add_edge("alice", "bob", {"weight": 1.0, "description": "manages"})
        batch.add_edge("bob", "alice", {"weight": 1.0, "description": "reports_to"})

        # Mock session and transaction with proper async context manager protocol
        mock_tx = AsyncMock()
        mock_tx.commit = AsyncMock()
        mock_tx.rollback = AsyncMock()
        mock_tx.run = AsyncMock()

        mock_session = AsyncMock()
        mock_session.begin_transaction = MagicMock()
        mock_session.begin_transaction.return_value.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_session.begin_transaction.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock the session factory to return async context manager
        session_factory = MagicMock()
        session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        storage.async_driver.session = MagicMock(return_value=session_factory.return_value)

        # Should complete without deadlock
        await storage.execute_document_batch(batch)

        mock_tx.commit.assert_called_once()
        assert mock_tx.rollback.call_count == 0

    @pytest.mark.asyncio
    async def test_batch_transaction_rollback_on_error(self, mock_neo4j_storage):
        """Test batch rollback on transaction error."""
        storage = mock_neo4j_storage

        batch = DocumentGraphBatch()
        batch.add_node("test", {"entity_type": "Test"})

        # Mock session and transaction with error
        mock_tx = AsyncMock()
        mock_tx.commit = AsyncMock()
        mock_tx.rollback = AsyncMock()
        mock_tx.run = AsyncMock(side_effect=Exception("Database error"))

        mock_session = AsyncMock()
        mock_session.begin_transaction = MagicMock()
        mock_session.begin_transaction.return_value.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_session.begin_transaction.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock the session factory to return async context manager
        session_factory = MagicMock()
        session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        storage.async_driver.session = MagicMock(return_value=session_factory.return_value)

        # Execute should raise after retries
        with pytest.raises(Exception, match="Database error"):
            await storage.execute_document_batch(batch)

        # Verify rollback was called
        mock_tx.rollback.assert_called()

    @pytest.mark.asyncio
    async def test_batch_with_chunking(self, mock_neo4j_storage):
        """Test batch execution with chunking."""
        storage = mock_neo4j_storage

        batch = DocumentGraphBatch()
        # Add 25 nodes to force chunking
        for i in range(25):
            batch.add_node(f"entity{i}", {"entity_type": "Entity", "description": f"Entity {i}"})

        # Mock session and transaction with proper async context manager protocol
        mock_tx = AsyncMock()
        mock_tx.commit = AsyncMock()
        mock_tx.rollback = AsyncMock()
        mock_tx.run = AsyncMock()

        mock_session = AsyncMock()
        mock_session.begin_transaction = MagicMock()
        mock_session.begin_transaction.return_value.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_session.begin_transaction.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock the session factory to return async context manager
        session_factory = MagicMock()
        session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        storage.async_driver.session = MagicMock(return_value=session_factory.return_value)

        await storage.execute_document_batch(batch)

        # Should create 3 chunks (10, 10, 5)
        assert mock_session.begin_transaction.call_count == 3
        assert mock_tx.commit.call_count == 3

    @pytest.mark.asyncio
    async def test_apoc_merge_operations(self, mock_neo4j_storage):
        """Test APOC functions are used correctly in merge operations."""
        storage = mock_neo4j_storage

        batch = DocumentGraphBatch()
        batch.add_node("test", {
            "entity_type": "Person",
            "description": "Test description",
            "source_id": f"doc1{GRAPH_FIELD_SEP}doc2"
        })

        # Mock session and transaction with proper async context manager protocol
        mock_tx = AsyncMock()
        mock_tx.commit = AsyncMock()
        mock_tx.rollback = AsyncMock()
        mock_tx.run = AsyncMock()

        mock_session = AsyncMock()
        mock_session.begin_transaction = MagicMock()
        mock_session.begin_transaction.return_value.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_session.begin_transaction.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock the session factory to return async context manager
        session_factory = MagicMock()
        session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        storage.async_driver.session = MagicMock(return_value=session_factory.return_value)

        await storage.execute_document_batch(batch)

        # Check that the query uses SET += for property replacement (CDX-002/003 fix)
        # APOC functions are no longer used after the double-merge fix
        call_args = mock_tx.run.call_args[0][0]
        assert "SET n +=" in call_args  # Simple property replacement
        assert "MERGE" in call_args  # Node merge
        # APOC functions should NOT be in the query anymore (CDX-002/003 fix)
        assert "apoc.text.join" not in call_args
        assert "apoc.coll.toSet" not in call_args


class TestNetworkXBatchCompatibility:
    """Test NetworkX storage batch compatibility."""

    @pytest.mark.asyncio
    async def test_networkx_batch_execution(self):
        """Test NetworkX executes batch without transactions."""
        from nano_graphrag._storage.gdb_networkx import NetworkXStorage

        storage = NetworkXStorage(
            namespace="test",
            global_config={"working_dir": "/tmp"}
        )

        batch = DocumentGraphBatch()
        batch.add_node("alice", {"entity_type": "Person", "description": "Alice"})
        batch.add_node("bob", {"entity_type": "Person", "description": "Bob"})
        batch.add_edge("alice", "bob", {"weight": 1.0, "description": "knows"})

        # Should execute without error
        await storage.execute_document_batch(batch)

        # Verify nodes and edges were added
        assert storage._graph.has_node("alice")
        assert storage._graph.has_node("bob")
        assert storage._graph.has_edge("alice", "bob")

        # Check node attributes
        assert storage._graph.nodes["alice"]["entity_type"] == "Person"
        assert storage._graph.nodes["alice"]["description"] == "Alice"

        # Check edge attributes
        edge_data = storage._graph.edges["alice", "bob"]
        assert edge_data["weight"] == 1.0
        assert edge_data["description"] == "knows"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])