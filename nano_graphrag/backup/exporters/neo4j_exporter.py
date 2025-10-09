"""Neo4j backup/restore exporter using APOC Core procedures."""

import os
import shutil
from pathlib import Path
from typing import Any, Dict

from ..._utils import logger


class Neo4jExporter:
    """Export and restore Neo4j graph database using APOC Core procedures.

    Uses apoc.export.cypher.query for export and apoc.cypher.runMany for restore.
    Both procedures are available in APOC Core (no Extended edition required).
    """

    def __init__(self, storage: Any):
        """Initialize exporter with Neo4j storage backend.

        Args:
            storage: Neo4jStorage instance
        """
        self.storage = storage
        self.database = storage.neo4j_database
        self.namespace = storage.namespace

    async def export(self, output_dir: Path) -> Path:
        """Export Neo4j database to Cypher dump file using APOC.

        Args:
            output_dir: Directory to write export file

        Returns:
            Path to dump file
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        dump_file = output_dir / "neo4j.dump"

        await self._export_with_apoc(dump_file)

        logger.info(f"Neo4j export complete: {dump_file}")
        return dump_file

    async def _export_with_apoc(self, dump_file: Path) -> None:
        """Export using APOC apoc.export.cypher.query procedure.

        Args:
            dump_file: Output dump file path
        """
        relative_path = dump_file.name
        neo4j_import_dir = os.getenv("NEO4J_IMPORT_DIR", "/neo4j_import")

        async with self.storage.async_driver.session(database=self.database) as session:
            # Export all nodes and relationships with the namespace label
            query = f"""
            CALL apoc.export.cypher.query(
                "MATCH (n:`{self.namespace}`) OPTIONAL MATCH (n)-[r]->(m:`{self.namespace}`) RETURN n, r, m",
                "{relative_path}",
                {{format: 'cypher-shell', useOptimizations: {{type: 'UNWIND_BATCH', unwindBatchSize: 20}}}}
            )
            """

            result = await session.run(query)
            record = await result.single()

            if record:
                logger.debug(f"APOC export result: {record}")
            else:
                raise RuntimeError("APOC export returned no results")

        # Copy export file from Neo4j import directory to output directory
        neo4j_import_path = Path(neo4j_import_dir) / relative_path
        if neo4j_import_path.exists():
            shutil.copy2(neo4j_import_path, dump_file)
            logger.info(f"Copied export from {neo4j_import_path} to {dump_file}")
        else:
            logger.warning(
                f"Export file not found at {neo4j_import_path}, "
                "file may still be in Neo4j container"
            )

    async def restore(self, dump_file: Path) -> None:
        """Restore Neo4j database from dump file using APOC.

        Args:
            dump_file: Path to dump file
        """
        if not dump_file.exists():
            raise FileNotFoundError(f"Dump file not found: {dump_file}")

        await self._restore_with_apoc(dump_file)

        logger.info(f"Neo4j restore complete from: {dump_file}")

    async def _restore_with_apoc(self, dump_file: Path) -> None:
        """Restore using APOC apoc.cypher.runMany procedure.

        Reads the Cypher dump file and executes it using apoc.cypher.runMany
        which handles multiple statements separated by semicolons.

        Args:
            dump_file: Dump file path
        """
        # Read the Cypher script
        with open(dump_file, 'r', encoding='utf-8') as f:
            cypher_script = f.read()

        # Clean the script: remove cypher-shell specific commands
        cleaned_statements = []
        for line in cypher_script.split('\n'):
            line = line.strip()
            # Skip empty lines, comments, and shell commands
            if not line or line.startswith('//') or line.startswith(':'):
                continue
            cleaned_statements.append(line)

        # Rejoin into single script
        cleaned_script = '\n'.join(cleaned_statements)

        logger.info(
            f"Restoring Neo4j database with {len(cleaned_script)} characters of Cypher"
        )

        # Execute using apoc.cypher.runMany
        async with self.storage.async_driver.session(database=self.database) as session:
            result = await session.run(
                "CALL apoc.cypher.runMany($cypher, {})",
                cypher=cleaned_script
            )

            # Consume all results to ensure execution completes
            records = []
            async for record in result:
                records.append(record)

            logger.info(
                f"Successfully executed restore with {len(records)} result records"
            )

    async def get_statistics(self) -> Dict[str, int]:
        """Get Neo4j database statistics.

        Returns:
            Dictionary with entity and relationship counts
        """
        async with self.storage.async_driver.session(database=self.database) as session:
            # Count nodes
            node_result = await session.run(
                f"MATCH (n:`{self.namespace}`) RETURN count(n) AS count"
            )
            node_record = await node_result.single()
            node_count = node_record["count"] if node_record else 0

            # Count relationships
            rel_result = await session.run(
                f"MATCH (:`{self.namespace}`)-[r]->(:`{self.namespace}`) RETURN count(r) AS count"
            )
            rel_record = await rel_result.single()
            rel_count = rel_record["count"] if rel_record else 0

            # Count communities (nodes with communityIds)
            comm_result = await session.run(
                f"""
                MATCH (n:`{self.namespace}`)
                WHERE n.communityIds IS NOT NULL
                WITH DISTINCT n.communityIds[-1] AS community_id
                RETURN count(community_id) AS count
                """
            )
            comm_record = await comm_result.single()
            comm_count = comm_record["count"] if comm_record else 0

        return {
            "entities": node_count,
            "relationships": rel_count,
            "communities": comm_count
        }
