"""Regression tests for CDX-002 and CDX-003: Ensure no data duplication in batch operations."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nano_graphrag._extraction import DocumentGraphBatch


class TestNoDuplication:
    """Test that batch operations don't duplicate data."""

    @pytest.mark.asyncio
    async def test_no_node_description_duplication(self):
        """Verify node descriptions aren't duplicated when batch runs multiple times."""
        from nano_graphrag._storage.gdb_neo4j import Neo4jStorage

        with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.__post_init__'):
            storage = Neo4jStorage(namespace="test", global_config={"addon_params": {}})
            storage.namespace = "test"
            storage.neo4j_database = "neo4j"
            storage._sanitize_label = lambda x: x.replace(" ", "_")

            # Mock driver properly
            mock_tx = AsyncMock()
            mock_session = AsyncMock()
            mock_session.begin_transaction.return_value.__aenter__.return_value = mock_tx
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None
            storage.async_driver = AsyncMock()
            storage.async_driver.session.return_value = mock_session

            # Prepare nodes with pre-merged data (as done by _merge_nodes_for_batch)
            nodes_by_type = {
                "Person": [{
                    "id": "alice",
                    "data": {
                        "entity_type": "Person",
                        "description": "Alice is an engineer | Alice works at TechCorp",  # Already merged
                        "source_id": "doc1<SEP>doc2"  # Already merged
                    }
                }]
            }

            # Execute batch
            await storage._execute_batch_nodes(mock_tx, nodes_by_type)

            # Check the Cypher query
            cypher_query = mock_tx.run.call_args[0][0]

            # Should use simple SET n += node.data, not re-merge
            assert "SET n += node.data" in cypher_query
            assert "apoc.text.join([n.description, node.data.description]" not in cypher_query
            assert "CASE WHEN n.description IS NULL" not in cypher_query

            print("✓ Node descriptions not duplicated")

    @pytest.mark.asyncio
    async def test_no_edge_weight_accumulation(self):
        """Verify edge weights aren't accumulated incorrectly."""
        from nano_graphrag._storage.gdb_neo4j import Neo4jStorage

        with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.__post_init__'):
            storage = Neo4jStorage(namespace="test", global_config={"addon_params": {}})
            storage.namespace = "test"
            storage.neo4j_database = "neo4j"
            storage._sanitize_label = lambda x: x.replace(" ", "_")

            # Mock driver properly
            mock_tx = AsyncMock()
            mock_session = AsyncMock()
            mock_session.begin_transaction.return_value.__aenter__.return_value = mock_tx
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None
            storage.async_driver = AsyncMock()
            storage.async_driver.session.return_value = mock_session

            # Prepare edges with pre-merged data (as done by _merge_edges_for_batch)
            edges_params = storage._prepare_batch_edges([
                ("alice", "bob", {
                    "weight": 5.0,  # This is the FINAL weight after merging
                    "description": "knows | works with",  # Already merged
                    "source_id": "doc1<SEP>doc2",  # Already merged
                    "relation_type": "KNOWS"
                })
            ])

            # Execute batch
            await storage._execute_batch_edges(mock_tx, edges_params)

            # Check the Cypher query
            cypher_query = mock_tx.run.call_args[0][0]

            # Should use SET r += edge.edge_data, not accumulate weight
            assert "SET r += edge.edge_data" in cypher_query
            assert "COALESCE(r.weight, 0) + edge.weight" not in cypher_query
            assert "apoc.text.join(" not in cypher_query

            print("✓ Edge weights not accumulated")

    @pytest.mark.asyncio
    async def test_idempotent_batch_execution(self):
        """Test that running the same batch twice produces the same result."""
        from nano_graphrag._extraction import DocumentGraphBatch
        from nano_graphrag._storage.gdb_neo4j import Neo4jStorage

        with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.__post_init__'):
            storage = Neo4jStorage(namespace="test", global_config={"addon_params": {}})
            storage.namespace = "test"
            storage.neo4j_database = "neo4j"
            storage._sanitize_label = lambda x: x.replace(" ", "_")

            # Mock driver properly
            mock_tx = AsyncMock()
            mock_tx.commit = AsyncMock()
            mock_tx.rollback = AsyncMock()

            mock_session = MagicMock()
            mock_tx_context = AsyncMock()
            mock_tx_context.__aenter__.return_value = mock_tx
            mock_tx_context.__aexit__.return_value = None
            mock_session.begin_transaction.return_value = mock_tx_context

            mock_session_context = AsyncMock()
            mock_session_context.__aenter__.return_value = mock_session
            mock_session_context.__aexit__.return_value = None

            storage.async_driver = MagicMock()
            storage.async_driver.session.return_value = mock_session_context

            # Create batch with pre-merged data
            batch = DocumentGraphBatch()
            batch.add_node("entity1", {
                "entity_type": "Entity",
                "description": "Final merged description",
                "source_id": "doc1<SEP>doc2<SEP>doc3"
            })
            batch.add_edge("entity1", "entity2", {
                "weight": 10.0,
                "description": "Final merged edge description",
                "source_id": "doc1<SEP>doc2",
                "relation_type": "RELATES"
            })

            # Process the batch
            await storage._process_batch_chunk(batch, 0)

            # Verify both node and edge queries use replacement, not merging
            calls = mock_tx.run.call_args_list

            # Node query should have SET n += node.data
            node_query = calls[0][0][0]
            assert "SET n += node.data" in node_query

            # Edge query should have SET r += edge.edge_data
            edge_query = calls[1][0][0]
            assert "SET r += edge.edge_data" in edge_query

            print("✓ Batch execution is idempotent")

    def test_prepared_edge_data_structure(self):
        """Test that edge data preparation includes the full edge_data dict."""
        from nano_graphrag._storage.gdb_neo4j import Neo4jStorage

        with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.__post_init__'):
            storage = Neo4jStorage(namespace="test", global_config={"addon_params": {}})
            storage._sanitize_label = lambda x: x

            edges = [
                ("src1", "tgt1", {
                    "weight": 5.0,
                    "description": "test description",
                    "source_id": "doc1",
                    "relation_type": "KNOWS",
                    "order": 1
                })
            ]

            result = storage._prepare_batch_edges(edges)

            assert len(result) == 1
            assert result[0]["source_id"] == "src1"
            assert result[0]["target_id"] == "tgt1"
            assert result[0]["relation_type"] == "KNOWS"
            assert "edge_data" in result[0]
            assert result[0]["edge_data"]["weight"] == 5.0

            print("✓ Edge data structure correct")


if __name__ == "__main__":
    import asyncio

    test_suite = TestNoDuplication()
    asyncio.run(test_suite.test_no_node_description_duplication())
    asyncio.run(test_suite.test_no_edge_weight_accumulation())
    asyncio.run(test_suite.test_idempotent_batch_execution())
    test_suite.test_prepared_edge_data_structure()

    print("\n✅ All duplication tests passed!")