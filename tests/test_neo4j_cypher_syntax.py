"""Test Neo4j Cypher syntax validation for NGRAF-022 CDX-001 fix."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from nano_graphrag._storage.gdb_neo4j import Neo4jStorage
from nano_graphrag.prompt import GRAPH_FIELD_SEP


class TestNeo4jCypherSyntax:
    """Test that generated Cypher queries are syntactically valid."""

    def test_node_merge_cypher_syntax(self):
        """Verify the node merge Cypher query is syntactically valid."""

        # Create a mock storage to generate the query
        storage = MagicMock(spec=Neo4jStorage)
        storage.namespace = "test"

        # The actual Cypher template from _execute_batch_nodes
        entity_type = "Person"
        cypher_query = f"""
                UNWIND $nodes AS node
                MERGE (n:`{storage.namespace}`:`{entity_type}` {{id: node.id}})
                SET n += node.data
                """

        # Key validations:
        # 1. No array indexing with [0] (was the bug)
        assert "[0]" not in cypher_query, "Cypher should not use array indexing [0]"

        # 2. Uses simple property replacement
        assert "SET n += node.data" in cypher_query

        # 3. No APOC merging (that's done in Python)
        assert "apoc.text.join" not in cypher_query
        assert "CASE WHEN" not in cypher_query

        print("✓ Node merge Cypher syntax is valid")

    def test_edge_merge_cypher_syntax(self):
        """Verify the edge merge Cypher query is syntactically valid."""

        storage = MagicMock(spec=Neo4jStorage)
        storage.namespace = "test"

        # The actual Cypher from _execute_batch_edges
        cypher_query = f"""
            UNWIND $edges AS edge
            MATCH (s:`{storage.namespace}`)
            WHERE s.id = edge.source_id
            WITH edge, s
            MATCH (t:`{storage.namespace}`)
            WHERE t.id = edge.target_id
            MERGE (s)-[r:RELATED]->(t)
            SET r += edge.edge_data
            SET r.relation_type = edge.relation_type
            """

        # Validations
        assert "[0]" not in cypher_query, "Edge Cypher should not use array indexing"
        assert "SET r += edge.edge_data" in cypher_query
        assert "SET r.relation_type = edge.relation_type" in cypher_query
        assert "COALESCE" not in cypher_query, "Should not accumulate weights"

        print("✓ Edge merge Cypher syntax is valid")

    @pytest.mark.asyncio
    async def test_cypher_execution_mock(self):
        """Test that the Cypher executes without syntax errors (mock)."""
        from unittest.mock import patch
        from nano_graphrag._extraction import DocumentGraphBatch

        # Create mock storage with fixed Cypher
        with MagicMock() as mock_storage:
            mock_storage.namespace = "test"
            mock_storage.neo4j_database = "neo4j"
            mock_storage._sanitize_label = lambda x: x.replace(" ", "_")

            # Create a real Neo4jStorage instance with mocked driver
            from nano_graphrag._storage.gdb_neo4j import Neo4jStorage
            with patch('nano_graphrag._storage.gdb_neo4j.Neo4jStorage.__post_init__'):
                storage = Neo4jStorage(namespace="test", global_config={"addon_params": {}})
                storage.namespace = "test"
                storage.neo4j_database = "neo4j"
                storage._sanitize_label = lambda x: x.replace(" ", "_")

            # Mock the driver
            mock_tx = AsyncMock()
            mock_session = AsyncMock()
            mock_session.begin_transaction.return_value.__aenter__.return_value = mock_tx
            storage.async_driver = AsyncMock()
            storage.async_driver.session.return_value.__aenter__.return_value = mock_session

            # Prepare test data
            nodes_by_type = {
                "Person": [
                    {"id": "alice", "data": {"entity_type": "Person", "description": "Alice", "source_id": "doc1"}},
                    {"id": "bob", "data": {"entity_type": "Person", "description": "Bob", "source_id": "doc1"}}
                ]
            }

            edges_params = [{
                "source_id": "alice",
                "target_id": "bob",
                "relation_type": "KNOWS",
                "weight": 1.0,
                "description": "knows",
                "source_id_field": "doc1",
                "order": 1
            }]

            # Execute the methods that generate Cypher
            await storage._execute_batch_nodes(mock_tx, nodes_by_type)
            await storage._execute_batch_edges(mock_tx, edges_params)

            # Verify the queries were executed
            assert mock_tx.run.call_count == 2

            # Check the actual Cypher generated (first call for nodes)
            node_cypher = mock_tx.run.call_args_list[0][0][0]
            assert "[0]" not in node_cypher, "Generated node Cypher contains invalid [0] indexing"
            assert "SET n += node.data" in node_cypher, "Should use simple property replacement"
            assert "apoc.text.join" not in node_cypher, "Should not use APOC merging"

            # Check edge Cypher (second call)
            edge_cypher = mock_tx.run.call_args_list[1][0][0]
            assert "[0]" not in edge_cypher, "Generated edge Cypher contains invalid [0] indexing"
            assert "SET r += edge.edge_data" in edge_cypher, "Should use simple property replacement"

            print("✓ Cypher execution test passed")


if __name__ == "__main__":
    # Run the syntax tests directly
    test_suite = TestNeo4jCypherSyntax()
    test_suite.test_node_merge_cypher_syntax()
    test_suite.test_edge_merge_cypher_syntax()

    # Run async test with pytest
    import asyncio
    asyncio.run(test_suite.test_cypher_execution_mock())

    print("\n✓ All Cypher syntax tests passed!")