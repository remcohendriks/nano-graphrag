#!/usr/bin/env python3
"""
Health check script for nano-graphrag.
Tests basic functionality with tuned parameters for <10 minute runtime.
"""

import os
import sys
import time
import asyncio
import json
import shutil
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timezone
from dotenv import load_dotenv

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)

# Add parent directory to path to import nano_graphrag
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nano_graphrag import GraphRAG, QueryParam
from nano_graphrag.config import GraphRAGConfig


class HealthCheck:
    """End-to-end health check for nano-graphrag."""
    
    def __init__(self, env_file: Optional[str] = None, working_dir: Optional[str] = None, fresh: bool = False):
        """Initialize health check with optional environment file.
        
        Args:
            env_file: Environment configuration file
            working_dir: Persistent working directory (default: .health/dickens)
            fresh: If True, clear working directory before starting
        """
        if env_file:
            load_dotenv(env_file, override=True)
        
        # Use persistent working directory by default
        if working_dir:
            self.working_dir = Path(working_dir).resolve()
        else:
            self.working_dir = Path(".health/dickens").resolve()
        
        # Clear if requested
        if fresh and self.working_dir.exists():
            shutil.rmtree(self.working_dir)
            print(f"Cleared working directory: {self.working_dir}")
        
        # Create directory
        self.working_dir.mkdir(parents=True, exist_ok=True)
        print(f"Working directory: {self.working_dir}")
        
        # Set working directory in environment for GraphRAG to pick up
        os.environ["STORAGE_WORKING_DIR"] = str(self.working_dir)
        
        # Initialize results tracking
        self.results: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": os.environ.get("LLM_PROVIDER", "openai"),
            "model": os.environ.get("LLM_MODEL", "unknown"),
            "storage": {
                "vector_backend": os.environ.get("STORAGE_VECTOR_BACKEND", "nano"),
                "graph_backend": os.environ.get("STORAGE_GRAPH_BACKEND", "networkx"),
                "kv_backend": os.environ.get("STORAGE_KV_BACKEND", "json"),
            },
            "status": "running",
            "timings": {},
            "counts": {
                "nodes": 0,
                "edges": 0,
                "communities": 0,
                "chunks": 0
            },
            "errors": [],
            "tests": {}
        }
        
        # Only set defaults if not already set by env file
        # These can be overridden by the config files
        if "LLM_MAX_CONCURRENT" not in os.environ:
            os.environ["LLM_MAX_CONCURRENT"] = "8"  # Limited concurrency for stability
        if "EMBEDDING_MAX_CONCURRENT" not in os.environ:
            os.environ["EMBEDDING_MAX_CONCURRENT"] = "8"
        if "LLM_CACHE_ENABLED" not in os.environ:
            os.environ["LLM_CACHE_ENABLED"] = "true"  # Enable caching for repeated queries
        
    def cleanup(self, keep_persistent: bool = True):
        """Clean up working directory.
        
        Args:
            keep_persistent: If True, keep persistent directories (default behavior)
        """
        # Only clean up if it's a temp directory or explicitly requested
        if not keep_persistent and self.working_dir.exists():
            shutil.rmtree(self.working_dir)
            print(f"Cleaned up: {self.working_dir}")
    
    def load_test_data(self) -> str:
        """Load test data - using smaller subset for faster testing."""
        test_data_path = Path(__file__).parent.parent / "mock_data.txt"
        if not test_data_path.exists():
            raise FileNotFoundError(f"Test data not found: {test_data_path}")
        
        with open(test_data_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Remove empty lines
        lines = [line for line in lines if line.strip()]
        
        # Truncate if TEST_DATA_LINES is set (for faster testing)
        test_data_lines = os.environ.get("TEST_DATA_LINES")
        if test_data_lines:
            try:
                max_lines = int(test_data_lines)
                if max_lines > 0:
                    lines = lines[:max_lines]
                    print(f"Using first {max_lines} non-empty lines for testing")
            except ValueError:
                print(f"Warning: Invalid TEST_DATA_LINES value: {test_data_lines}")
        
        return "".join(lines)
    
    def count_graph_elements(self) -> Tuple[int, int]:
        """Count nodes and edges in the generated graph."""
        # Check if we're using Neo4j backend
        graph_backend = os.environ.get("STORAGE_GRAPH_BACKEND", "networkx")
        
        if graph_backend == "neo4j":
            # Count nodes and edges from Neo4j
            try:
                from neo4j import GraphDatabase
                
                neo4j_url = os.environ.get("NEO4J_URL", "neo4j://localhost:7687")
                neo4j_username = os.environ.get("NEO4J_USERNAME", "neo4j")
                neo4j_password = os.environ.get("NEO4J_PASSWORD", "neo4j")
                neo4j_database = os.environ.get("NEO4J_DATABASE", "neo4j")
                
                driver = GraphDatabase.driver(neo4j_url, auth=(neo4j_username, neo4j_password))
                
                with driver.session(database=neo4j_database) as session:
                    # Count all nodes with the namespace label
                    # Check for custom namespace from environment
                    custom_namespace = os.environ.get("NEO4J_GRAPH_NAMESPACE")
                    if custom_namespace:
                        namespace_label = custom_namespace
                    else:
                        # Default format: GraphRAG_{namespace}
                        clean_namespace = f"{self.working_dir.name}_chunk_entity_relation"
                        clean_namespace = clean_namespace.replace("/", "_").replace("-", "_").replace(".", "_")
                        namespace_label = f"GraphRAG_{clean_namespace}"
                    
                    # Count nodes
                    result = session.run(f"MATCH (n:`{namespace_label}`) RETURN count(n) as count")
                    node_count = result.single()["count"]
                    
                    # Count relationships
                    result = session.run(f"MATCH (:`{namespace_label}`)-[r]->(:`{namespace_label}`) RETURN count(r) as count")
                    edge_count = result.single()["count"]
                    
                driver.close()
                return node_count, edge_count
                
            except Exception as e:
                print(f"Error querying Neo4j: {e}")
                return 0, 0
        else:
            # Default: look for GraphML file
            graphml_path = self.working_dir / "graph_chunk_entity_relation.graphml"
            if not graphml_path.exists():
                return 0, 0
            
            try:
                tree = ET.parse(graphml_path)
                root = tree.getroot()
                
                # GraphML namespace
                ns = {'g': 'http://graphml.graphdrawing.org/xmlns'}
                
                # Count nodes and edges
                nodes = root.findall('.//g:node', ns)
                edges = root.findall('.//g:edge', ns)
                
                return len(nodes), len(edges)
            except Exception as e:
                print(f"Error parsing GraphML: {e}")
                return 0, 0
    
    async def test_insert_and_build(self, graph: GraphRAG, text: str) -> bool:
        """Test document insertion and graph building."""
        print("\n=== Testing Insert and Build ===")
        start_time = time.time()
        
        try:
            # Insert document with timeout
            print("Inserting document...")
            print(f"Using LLM model: {graph.config.llm.model}")
            print(f"Using embedding model: {graph.config.embedding.model}")
            print(f"Using vector backend: {graph.config.storage.vector_backend}")
            print(f"Chunk size: {graph.config.chunking.size}")
            print(f"Max gleaning: {graph.config.entity_extraction.max_gleaning}")
            print(f"Document size: {len(text):,} characters")
            
            start_time = time.time()
            
            print("Starting async insert task...")
            # Add longer timeout for GPT-5 models
            insert_task = asyncio.create_task(graph.ainsert(text))
            print("Waiting for insert to complete (600s timeout)...")
            await asyncio.wait_for(insert_task, timeout=600)  # 10 minute timeout
            print("Insert task completed!")
            
            artifacts = [
                "kv_store_full_docs.json",
                "kv_store_text_chunks.json", 
                "graph_chunk_entity_relation.graphml",
                "kv_store_community_reports.json",
                "vdb_entities.json",
                "vdb_chunks.json"
            ]
            
            for artifact in artifacts:
                path = self.working_dir / artifact
                if path.exists():
                    if path.is_file():
                        size = path.stat().st_size
                        print(f"✓ {artifact}: {size:,} bytes")
                    else:
                        # Directory - count files
                        files = list(path.glob("*"))
                        print(f"✓ {artifact}: {len(files)} files")
                else:
                    print(f"✗ {artifact}: Not found")
            
            # Count graph elements
            nodes, edges = self.count_graph_elements()
            print(f"Graph statistics: {nodes} nodes, {edges} edges")
            
            # Count communities and chunks for metrics
            try:
                with open(self.working_dir / "kv_store_community_reports.json") as f:
                    reports = json.load(f)
                    self.results["counts"]["communities"] = len(reports)
                    print(f"Communities: {len(reports)}")
            except Exception:
                self.results["counts"]["communities"] = 0
            
            try:
                with open(self.working_dir / "kv_store_text_chunks.json") as f:
                    chunks = json.load(f)
                    self.results["counts"]["chunks"] = len(chunks)
                    print(f"Chunks: {len(chunks)}")
            except Exception:
                self.results["counts"]["chunks"] = 0
            
            elapsed = time.time() - start_time
            print(f"Insert completed in {elapsed:.1f} seconds")
            
            # Validate graph was built
            assert nodes > 10, f"Expected >10 nodes, got {nodes}"
            assert edges > 5, f"Expected >5 edges, got {edges}"
            
            # Store results
            self.results["timings"]["insert"] = elapsed
            self.results["counts"]["nodes"] = nodes
            self.results["counts"]["edges"] = edges
            self.results["tests"]["insert"] = "passed"
            
            return True
            
        except Exception as e:
            print(f"Insert failed: {e}")
            import traceback
            print("Traceback:")
            traceback.print_exc()
            self.results["errors"].append(f"Insert failed: {str(e)}")
            self.results["tests"]["insert"] = "failed"
            return False
    
    async def test_query(self, graph: GraphRAG) -> bool:
        """Test different query modes."""
        print("\n=== Testing Query Modes ===")
        
        queries = [
            ("What are the main themes in the story?", "global"),
            ("Who is Scrooge and what is his character?", "local"),
            ("What happens on Christmas Eve?", "naive")
        ]
        
        all_passed = True
        
        for query_text, mode in queries:
            try:
                print(f"\nQuery ({mode}): {query_text[:50]}...")
                
                param = QueryParam(mode=mode)
                start_time = time.time()
                
                result = await graph.aquery(query_text, param=param)
                
                elapsed = time.time() - start_time
                response_len = len(result) if result else 0
                
                print(f"Response length: {response_len} chars")
                print(f"Query time: {elapsed:.1f} seconds")
                
                # Validate response
                # Check for default "no context" response
                if result and "No context" in result:
                    print(f"Warning: Got default 'no context' response for {mode} query")
                    print(f"This likely means the graph wasn't built properly")
                    all_passed = False
                    continue
                
                # Store timing
                self.results["timings"][f"{mode}_query"] = elapsed
                
                # Validate response (more lenient)
                min_expected = 100 if mode == "naive" else 200
                if response_len < min_expected:
                    print(f"Warning: Response too short for {mode} (expected >{min_expected}, got {response_len})")
                    self.results["tests"][f"{mode}_query"] = "failed"
                    all_passed = False
                else:
                    print(f"✓ {mode.capitalize()} query passed")
                    self.results["tests"][f"{mode}_query"] = "passed"
                
                # Show preview of response
                if result:
                    preview = result[:200] + "..." if len(result) > 200 else result
                    print(f"Preview: {preview}")
                
            except Exception as e:
                print(f"Query ({mode}) failed: {e}")
                import traceback
                print("Traceback:")
                traceback.print_exc()
                self.results["errors"].append(f"{mode} query failed: {str(e)}")
                self.results["tests"][f"{mode}_query"] = "failed"
                all_passed = False
                continue
        
        return all_passed
    
    async def test_reload(self) -> bool:
        """Test reloading from cached state."""
        print("\n=== Testing Reload from Cache ===")
        
        try:
            # Create new instance from same working dir - uses existing config from env
            graph = GraphRAG(config=GraphRAGConfig.from_env())
            
            # Quick global query to verify cached state works
            query = "Summarize the story in one sentence."
            param = QueryParam(mode="global")
            
            start_time = time.time()
            result = await graph.aquery(query, param=param)
            elapsed = time.time() - start_time
            
            response_len = len(result) if result else 0
            print(f"Reload query response: {response_len} chars in {elapsed:.1f} seconds")
            
            # Check for default "no context" response
            if result and "No context" in result:
                print("Warning: Got default 'no context' response after reload")
                return False
            
            # Store timing
            self.results["timings"]["reload"] = elapsed
            
            # Reload should be much faster than initial insert
            insert_time = self.results["timings"].get("insert", 300)
            if elapsed > insert_time * 0.3:  # Should be <30% of insert time
                print(f"Warning: Reload slow ({elapsed:.1f}s, expected <{insert_time * 0.3:.1f}s)")
            
            if response_len < 50:
                print(f"Warning: Reload response too short (expected >50, got {response_len})")
                self.results["tests"]["reload"] = "failed"
                return False
            
            print(f"✓ Reload test passed")
            self.results["tests"]["reload"] = "passed"
            return True
            
        except Exception as e:
            print(f"Reload test failed: {e}")
            self.results["errors"].append(f"Reload failed: {str(e)}")
            self.results["tests"]["reload"] = "failed"
            return False
    
    def save_report(self):
        """Save JSON report with test results, preserving history."""
        report_dir = Path("tests/health/reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "latest.json"
        
        # Load existing history
        history = []
        if report_path.exists():
            try:
                with open(report_path) as f:
                    existing = json.load(f)
                    # Handle both old format (single dict) and new format (array)
                    if isinstance(existing, dict):
                        history = [existing]
                    else:
                        history = existing
            except Exception as e:
                print(f"Warning: Could not load existing history: {e}")
        
        # Add current run at the beginning
        history.insert(0, self.results)
        
        # Keep only last 100 runs to prevent unbounded growth
        MAX_HISTORY = 100
        history = history[:MAX_HISTORY]
        
        # Save updated history
        with open(report_path, "w") as f:
            json.dump(history, f, indent=2)
        
        print(f"\n📊 Report saved to {report_path} (keeping {len(history)} runs)")
    
    async def run(self) -> bool:
        """Run complete health check."""
        print("=" * 60)
        print("NANO-GRAPHRAG HEALTH CHECK")
        print("=" * 60)
        
        overall_start = time.time()
        
        try:
            # Load test data
            print("\nLoading test data...")
            text = self.load_test_data()
            print(f"Loaded {len(text):,} characters")
            
            # Initialize GraphRAG using only environment configuration
            # No function injection - GraphRAG will use env vars for LLM/embedding config
            config = GraphRAGConfig.from_env()
            graph = GraphRAG(config=config)
            
            # Print storage configuration
            print(f"\nStorage Configuration:")
            print(f"  Vector Backend: {config.storage.vector_backend}")
            print(f"  Graph Backend: {config.storage.graph_backend}")
            print(f"  KV Backend: {config.storage.kv_backend}")
            if config.storage.vector_backend == "qdrant":
                print(f"  Qdrant URL: {config.storage.qdrant_url}")
            
            # Update results with actual config values
            self.results["storage"]["vector_backend"] = config.storage.vector_backend
            self.results["storage"]["graph_backend"] = config.storage.graph_backend
            self.results["storage"]["kv_backend"] = config.storage.kv_backend
            if config.storage.vector_backend == "qdrant":
                self.results["storage"]["qdrant_url"] = config.storage.qdrant_url
            
            # Run tests
            tests_passed = []
            
            # Test 1: Insert and build graph
            tests_passed.append(await self.test_insert_and_build(graph, text))
            
            # Test 2: Query modes
            tests_passed.append(await self.test_query(graph))
            
            # Test 3: Reload from cache
            tests_passed.append(await self.test_reload())
            
            # Summary
            print("\n" + "=" * 60)
            print("HEALTH CHECK SUMMARY")
            print("=" * 60)
            
            total_time = time.time() - overall_start
            passed = sum(tests_passed)
            total = len(tests_passed)
            
            print(f"Tests passed: {passed}/{total}")
            print(f"Total time: {total_time:.1f} seconds ({total_time/60:.1f} minutes)")
            
            if total_time > 600:
                print("⚠️  Warning: Runtime exceeded 10 minutes")
            
            success = passed == total
            self.results["status"] = "passed" if success else "failed"
            self.results["timings"]["total"] = total_time
            
            # Save JSON report
            self.save_report()
            
            if success:
                print("✅ Health check PASSED")
            else:
                print("❌ Health check FAILED")
            
            return success
            
        except Exception as e:
            print(f"\n❌ Health check crashed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            # Clean up Neo4j if we're using it
            if os.environ.get("STORAGE_GRAPH_BACKEND") == "neo4j":
                try:
                    from neo4j import GraphDatabase
                    neo4j_url = os.environ.get("NEO4J_URL", "neo4j://localhost:7687")
                    neo4j_username = os.environ.get("NEO4J_USERNAME", "neo4j")
                    neo4j_password = os.environ.get("NEO4J_PASSWORD", "neo4j")
                    neo4j_database = os.environ.get("NEO4J_DATABASE", "neo4j")
                    
                    driver = GraphDatabase.driver(neo4j_url, auth=(neo4j_username, neo4j_password))
                    with driver.session(database=neo4j_database) as session:
                        # Delete all nodes and relationships
                        result = session.run("MATCH (n) DETACH DELETE n")
                        summary = result.consume()
                        if summary.counters.nodes_deleted > 0:
                            print(f"\n🧹 Cleaned up Neo4j: {summary.counters.nodes_deleted} nodes, {summary.counters.relationships_deleted} relationships")
                    driver.close()
                except Exception as e:
                    print(f"Warning: Could not clean up Neo4j: {e}")
            
            # Clean up Qdrant if we're using it
            if os.environ.get("STORAGE_VECTOR_BACKEND") == "qdrant":
                try:
                    from qdrant_client import QdrantClient
                    
                    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
                    qdrant_api_key = os.environ.get("QDRANT_API_KEY", None)
                    
                    # Use synchronous client for cleanup to avoid event loop issues
                    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
                    
                    # Get the namespace prefix
                    namespace_prefix = os.environ.get("QDRANT_NAMESPACE_PREFIX")
                    if not namespace_prefix:
                        # Use working directory basename as prefix
                        namespace_prefix = self.working_dir.name
                    
                    # Delete collections with our namespace prefix
                    collections_to_delete = [
                        f"{namespace_prefix}_entities",
                        f"{namespace_prefix}_chunks"
                    ]
                    
                    deleted_count = 0
                    for collection_name in collections_to_delete:
                        try:
                            # Check if collection exists first
                            collections = client.get_collections()
                            if any(c.name == collection_name for c in collections.collections):
                                client.delete_collection(collection_name)
                                deleted_count += 1
                        except Exception as e:
                            print(f"Warning: Could not delete Qdrant collection {collection_name}: {e}")
                    
                    if deleted_count > 0:
                        print(f"\n🧹 Cleaned up Qdrant: {deleted_count} collections deleted")
                    
                    client.close()
                    
                except Exception as e:
                    print(f"Warning: Could not clean up Qdrant: {e}")
            
            # Keep persistent directory by default
            self.cleanup(keep_persistent=True)


def print_history_summary():
    """Print a summary of historical health check runs."""
    report_path = Path("tests/health/reports/latest.json")
    if not report_path.exists():
        print("No history found")
        return
    
    try:
        with open(report_path) as f:
            history = json.load(f)
            if isinstance(history, dict):
                history = [history]
        
        print("\n=== Health Check History ===")
        print(f"Total runs: {len(history)}")
        
        if history:
            # Summary stats
            passed = sum(1 for run in history if run.get("status") == "passed")
            failed = sum(1 for run in history if run.get("status") == "failed")
            
            print(f"Success rate: {passed}/{len(history)} ({passed*100//len(history)}%)")
            
            # Show last 5 runs
            print("\nRecent runs:")
            for run in history[:5]:
                timestamp = run.get("timestamp", "unknown")
                # Support both old 'mode' and new 'provider' field for backward compatibility
                provider = run.get("provider", run.get("mode", "unknown"))
                model = run.get("model", "")
                status = run.get("status", "unknown")
                total_time = run.get("timings", {}).get("total", 0)
                
                # Get storage backend info if available
                storage_info = run.get("storage", {})
                vector_backend = storage_info.get("vector_backend", "")
                
                status_emoji = "✅" if status == "passed" else "❌"
                # Show model name and storage backend if available
                if model and model != "unknown":
                    # Truncate long model names for display
                    model_display = model if len(model) <= 20 else model[:17] + "..."
                    if vector_backend and vector_backend != "nano":
                        print(f"  {status_emoji} {timestamp[:19]} - {provider:8} - {model_display:20} - {vector_backend:8} - {total_time:6.1f}s")
                    else:
                        print(f"  {status_emoji} {timestamp[:19]} - {provider:8} - {model_display:20} - {total_time:6.1f}s")
                else:
                    print(f"  {status_emoji} {timestamp[:19]} - {provider:8} - {total_time:6.1f}s")
    
    except Exception as e:
        print(f"Error reading history: {e}")


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run nano-graphrag health check")
    parser.add_argument(
        "--env",
        help="Environment file to load (e.g., config_openai.env)",
        default=None
    )
    parser.add_argument(
        "--mode",
        choices=["openai", "lmstudio"],
        help="Quick mode selection (alternative to --env)",
        default=None
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Clear working directory before starting"
    )
    parser.add_argument(
        "--workdir",
        default=".health/dickens",
        help="Persistent working directory (default: .health/dickens)"
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Show health check history and exit"
    )
    
    args = parser.parse_args()
    
    # If --history flag, show history and exit
    if args.history:
        print_history_summary()
        return
    
    # Determine environment file
    env_file = args.env
    if args.mode and not env_file:
        env_file = f"config_{args.mode}.env"
        # Look for it in the same directory as this script
        env_path = Path(__file__).parent / env_file
        if env_path.exists():
            env_file = str(env_path)
        else:
            print(f"Warning: {env_file} not found, using system environment")
            env_file = None
    
    # Run health check
    health_check = HealthCheck(env_file, working_dir=args.workdir, fresh=args.fresh)
    success = await health_check.run()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())