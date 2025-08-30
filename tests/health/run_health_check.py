#!/usr/bin/env python3
"""
Health check script for nano-graphrag.
Tests basic functionality with tuned parameters for <10 minute runtime.
"""

import os
import sys
import time
import asyncio
import tempfile
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple
from dotenv import load_dotenv

# Add parent directory to path to import nano_graphrag
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nano_graphrag import GraphRAG, QueryParam
from nano_graphrag.config import GraphRAGConfig


class HealthCheck:
    """End-to-end health check for nano-graphrag."""
    
    def __init__(self, env_file: Optional[str] = None):
        """Initialize health check with optional environment file."""
        if env_file:
            load_dotenv(env_file, override=True)
        
        # Create temporary working directory
        self.working_dir = Path(tempfile.mkdtemp(prefix="nano_graphrag_health_"))
        print(f"Working directory: {self.working_dir}")
        
        # Set working directory in environment for GraphRAG to pick up
        os.environ["STORAGE_WORKING_DIR"] = str(self.working_dir)
        
        # Only set defaults if not already set by env file
        # These can be overridden by the config files
        if "LLM_MAX_CONCURRENT" not in os.environ:
            os.environ["LLM_MAX_CONCURRENT"] = "8"  # Limited concurrency for stability
        if "EMBEDDING_MAX_CONCURRENT" not in os.environ:
            os.environ["EMBEDDING_MAX_CONCURRENT"] = "8"
        if "LLM_CACHE_ENABLED" not in os.environ:
            os.environ["LLM_CACHE_ENABLED"] = "true"  # Enable caching for repeated queries
        
    def cleanup(self):
        """Clean up temporary working directory."""
        if self.working_dir.exists():
            shutil.rmtree(self.working_dir)
            print(f"Cleaned up: {self.working_dir}")
    
    def load_test_data(self) -> str:
        """Load test data - using smaller subset for faster testing."""
        test_data_path = Path(__file__).parent.parent / "mock_data.txt"
        if not test_data_path.exists():
            raise FileNotFoundError(f"Test data not found: {test_data_path}")
        
        with open(test_data_path, "r", encoding="utf-8") as f:
            full_text = f.read()
        
        # Use full text for proper testing
        return full_text
    
    def count_graph_elements(self) -> Tuple[int, int]:
        """Count nodes and edges in the generated graph."""
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
            print(f"Chunk size: {graph.config.chunking.size}")
            print(f"Max gleaning: {graph.config.entity_extraction.max_gleaning}")
            
            start_time = time.time()
            
            # Add longer timeout for GPT-5 models
            insert_task = asyncio.create_task(graph.ainsert(text))
            await asyncio.wait_for(insert_task, timeout=600)  # 10 minute timeout
            
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
            
            elapsed = time.time() - start_time
            print(f"Insert completed in {elapsed:.1f} seconds")
            
            elapsed = time.time() - start_time
            print(f"Insert completed in {elapsed:.1f} seconds")
            
            # Validate graph was built
            assert nodes > 10, f"Expected >10 nodes, got {nodes}"
            assert edges > 5, f"Expected >5 edges, got {edges}"
            
            return True
            
        except Exception as e:
            print(f"Insert failed: {e}")
            import traceback
            print("Traceback:")
            traceback.print_exc()
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
                
                # Validate response (more lenient)
                min_expected = 100 if mode == "naive" else 200
                if response_len < min_expected:
                    print(f"Warning: Response too short for {mode} (expected >{min_expected}, got {response_len})")
                    all_passed = False
                else:
                    print(f"✓ {mode.capitalize()} query passed")
                
                # Show preview of response
                if result:
                    preview = result[:200] + "..." if len(result) > 200 else result
                    print(f"Preview: {preview}")
                
            except Exception as e:
                print(f"Query ({mode}) failed: {e}")
                import traceback
                print("Traceback:")
                traceback.print_exc()
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
            
            # Should be fast since using cached data
            if elapsed > 30:
                print(f"Warning: Reload query slow ({elapsed:.1f}s, expected <30s)")
            
            if response_len < 50:
                print(f"Warning: Reload response too short (expected >50, got {response_len})")
                return False
            
            print(f"✓ Reload test passed")
            return True
            
        except Exception as e:
            print(f"Reload test failed: {e}")
            return False
    
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
            graph = GraphRAG(config=GraphRAGConfig.from_env())
            
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
            self.cleanup()


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
    
    args = parser.parse_args()
    
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
    health_check = HealthCheck(env_file)
    success = await health_check.run()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())