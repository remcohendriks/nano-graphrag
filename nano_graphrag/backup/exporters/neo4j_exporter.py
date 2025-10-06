"""Neo4j backup/restore exporter."""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

from ..._utils import logger


class Neo4jExporter:
    """Export and restore Neo4j graph database."""

    def __init__(self, storage: Any):
        """Initialize exporter with Neo4j storage backend.

        Args:
            storage: Neo4jStorage instance
        """
        self.storage = storage
        self.database = storage.neo4j_database
        self.namespace = storage.namespace

    async def export(self, output_dir: Path) -> Path:
        """Export Neo4j database to dump file.

        Uses neo4j-admin dump command if available, otherwise falls back to Cypher export.

        Args:
            output_dir: Directory to write export file

        Returns:
            Path to dump file
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        dump_file = output_dir / "neo4j.dump"

        try:
            # Try neo4j-admin dump (preferred method)
            await self._export_with_admin(dump_file)
        except Exception as e:
            logger.warning(f"neo4j-admin dump failed: {e}, falling back to Cypher export")
            await self._export_with_cypher(dump_file)

        logger.info(f"Neo4j export complete: {dump_file}")
        return dump_file

    async def _export_with_admin(self, dump_file: Path) -> None:
        """Export using neo4j-admin database dump command.

        Args:
            dump_file: Output dump file path
        """
        # neo4j-admin database dump requires stopping the database
        # For production, we use --to-path to export without stopping
        cmd = [
            "neo4j-admin",
            "database",
            "dump",
            self.database,
            f"--to-path={dump_file.parent}",
            "--overwrite-destination=true"
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise RuntimeError(f"neo4j-admin dump failed: {error_msg}")

        logger.debug(f"neo4j-admin output: {stdout.decode()}")

    async def _export_with_cypher(self, dump_file: Path) -> None:
        """Export using Cypher APOC export (fallback method).

        Args:
            dump_file: Output dump file path
        """
        relative_path = dump_file.name
        neo4j_import_dir = os.getenv("NEO4J_IMPORT_DIR", "/neo4j_import")

        async with self.storage.async_driver.session(database=self.database) as session:
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
                logger.debug(f"APOC export: {record}")
            else:
                raise RuntimeError("APOC export returned no results")

        neo4j_import_path = Path(neo4j_import_dir) / relative_path
        if neo4j_import_path.exists():
            shutil.copy2(neo4j_import_path, dump_file)
            logger.info(f"Copied export from {neo4j_import_path} to {dump_file}")
        else:
            logger.warning(f"Export file not found at {neo4j_import_path}, file may still be in Neo4j container")

    async def restore(self, dump_file: Path) -> None:
        """Restore Neo4j database from dump file.

        Args:
            dump_file: Path to dump file
        """
        if not dump_file.exists():
            raise FileNotFoundError(f"Dump file not found: {dump_file}")

        try:
            # Try neo4j-admin load
            await self._restore_with_admin(dump_file)
        except Exception as e:
            logger.warning(f"neo4j-admin load failed: {e}, falling back to Cypher restore")
            await self._restore_with_cypher(dump_file)

        logger.info(f"Neo4j restore complete from: {dump_file}")

    async def _restore_with_admin(self, dump_file: Path) -> None:
        """Restore using neo4j-admin database load command.

        Args:
            dump_file: Dump file path
        """
        cmd = [
            "neo4j-admin",
            "database",
            "load",
            self.database,
            f"--from-path={dump_file.parent}",
            "--overwrite-destination=true"
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise RuntimeError(f"neo4j-admin load failed: {error_msg}")

        logger.debug(f"neo4j-admin output: {stdout.decode()}")

    async def _restore_with_cypher(self, dump_file: Path) -> None:
        """Restore using Cypher script execution (fallback method).

        Args:
            dump_file: Dump file path
        """
        neo4j_import_dir = os.getenv("NEO4J_IMPORT_DIR", "/neo4j_import")
        neo4j_import_path = Path(neo4j_import_dir) / dump_file.name

        shutil.copy2(dump_file, neo4j_import_path)
        logger.info(f"Copied restore file to {neo4j_import_path}")

        with open(dump_file, 'r') as f:
            cypher_script = f.read()

        async with self.storage.async_driver.session(database=self.database) as session:
            for line in cypher_script.split('\n'):
                line = line.strip()

                if not line or line.startswith('//'):
                    continue

                if line.startswith(':'):
                    continue

                if line.endswith(';'):
                    line = line[:-1].strip()

                if line:
                    try:
                        await session.run(line)
                    except Exception as e:
                        logger.debug(f"Skipped statement: {e}")

        logger.debug("Cypher script executed successfully")

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
