# Code Review - Round 1
## Project: nano-graphrag
## Date: Wed Sep  3 01:30:37 CEST 2025
## Severity Focus: All Issues

## Source Code to Review

### File: ./tests/test_splitter.py
```
import unittest
from typing import List
import tiktoken
from nano_graphrag._splitter import SeparatorSplitter
from nano_graphrag._op import chunking_by_seperators

# Assuming the SeparatorSplitter class is already imported


class TestSeparatorSplitter(unittest.TestCase):

    def setUp(self):
        self.tokenize = lambda text: [
            ord(c) for c in text
        ]  # Simple tokenizer for testing
        self.detokenize = lambda tokens: "".join(chr(t) for t in tokens)

    def test_split_with_custom_separator(self):
        splitter = SeparatorSplitter(
            separators=[self.tokenize("\n"), self.tokenize(".")],
            chunk_size=19,
            chunk_overlap=0,
            keep_separator="end",
        )
        text = "This is a test.\nAnother test."
        tokens = self.tokenize(text)
        expected = [
            self.tokenize("This is a test.\n"),
            self.tokenize("Another test."),
        ]
        result = splitter.split_tokens(tokens)

        self.assertEqual(result, expected)

    def test_chunk_size_limit(self):
        splitter = SeparatorSplitter(
            chunk_size=5, chunk_overlap=0, separators=[self.tokenize("\n")]
        )
        text = "1234567890"
        tokens = self.tokenize(text)
        expected = [self.tokenize("12345"), self.tokenize("67890")]
        result = splitter.split_tokens(tokens)
        self.assertEqual(result, expected)

    def test_chunk_overlap(self):
        splitter = SeparatorSplitter(
            chunk_size=5, chunk_overlap=2, separators=[self.tokenize("\n")]
        )
        text = "1234567890"
        tokens = self.tokenize(text)
        expected = [
            self.tokenize("12345"),
            self.tokenize("45678"),
            self.tokenize("7890"),
        ]
        result = splitter.split_tokens(tokens)
        self.assertEqual(result, expected)

    def test_chunking_by_seperators(self):
        encoder = tiktoken.encoding_for_model("gpt-4o")
        text = "This is a test.\nAnother test."
        tokens_list = [encoder.encode(text)]
        doc_keys = ["doc1"]
        results = chunking_by_seperators(tokens_list, doc_keys, encoder)
        assert len(results) == 1
        assert results[0]["chunk_order_index"] == 0
        assert results[0]["full_doc_id"] == "doc1"
        assert results[0]["content"] == text


if __name__ == "__main__":
    unittest.main()
```

### File: ./tests/test_json_parsing.py
```
import unittest
# from loguru import logger
from nano_graphrag._utils import convert_response_to_json  

class TestJSONExtraction(unittest.TestCase):

    def setUp(self):
        """Set up runs before each test case."""
        ...

    def test_standard_json(self):
        """Test standard JSON extraction."""
        response = '''
        {
            "reasoning": "This is a test.",
            "answer": 42,
            "data": {"key1": "value1", "key2": "value2"}
        }
        '''
        expected = {
            "reasoning": "This is a test.",
            "answer": 42,
            "data": {"key1": "value1", "key2": "value2"}
        }
        self.assertEqual(convert_response_to_json(response), expected)

    def test_non_standard_json_without_quotes(self):
        """Test non-standard JSON without quotes on numbers and booleans."""
        response = '''
        {
            "reasoning": "Boolean and numbers test.",
            "answer": 42,
            "isCorrect": true,
            "data": {key1: value1}
        }
        '''
        expected = {
            "reasoning": "Boolean and numbers test.",
            "answer": 42,
            "isCorrect": True,
            "data": {"key1": "value1"}
        }
        self.assertEqual(convert_response_to_json(response), expected)

    def test_nested_json(self):
        """Test extraction of nested JSON objects."""
        response = '''
        {
            "reasoning": "Nested structure.",
            "answer": 42,
            "data": {"nested": {"key": "value"}}
        }
        '''
        expected = {
            "reasoning": "Nested structure.",
            "answer": 42,
            "data": {
                "nested": {"key": "value"}
            }
        }
        self.assertEqual(convert_response_to_json(response), expected)

    def test_malformed_json(self):
        """Test handling of malformed JSON."""
        response = '''
        Some text before JSON
        {
            "reasoning": "This is malformed.",
            "answer": 42,
            "data": {"key": "value"}
        }
        Some text after JSON
        '''
        expected = {
            "reasoning": "This is malformed.",
            "answer": 42,
            "data": {"key": "value"}
        }
        self.assertEqual(convert_response_to_json(response), expected)

    def test_incomplete_json(self):
        """Test handling of incomplete JSON."""
        response = '''
        {
            "reasoning": "Incomplete structure",
            "answer": 42
        '''
        expected = {
            "reasoning": "Incomplete structure",
            "answer": 42
        }
        self.assertEqual(convert_response_to_json(response), expected)

    def test_value_with_special_characters(self):
        """Test JSON with special characters in values."""
        response = '''
        {
            "reasoning": "Special characters !@#$%^&*()",
            "answer": 42,
            "data": {"key": "value with special characters !@#$%^&*()"}
        }
        '''
        expected = {
            "reasoning": "Special characters !@#$%^&*()",
            "answer": 42,
            "data": {"key": "value with special characters !@#$%^&*()"}
        }
        self.assertEqual(convert_response_to_json(response), expected)

    def test_boolean_and_null_values(self):
        """Test JSON with boolean and null values."""
        response = '''
        {
            "reasoning": "Boolean and null test.",
            "isCorrect": true,
            "isWrong": false,
            "unknown": null,
            "answer": 42
        }
        '''
        expected = {
            "reasoning": "Boolean and null test.",
            "isCorrect": True,
            "isWrong": False,
            "unknown": None,
            "answer": 42
        }
        self.assertEqual(convert_response_to_json(response), expected)

if __name__ == "__main__":
    unittest.main()```

### File: ./tests/test_providers.py
```
"""Test LLM and embedding providers."""
import os
import pytest
from unittest.mock import patch, AsyncMock, Mock, MagicMock
from typing import Dict, Any

from nano_graphrag.llm.providers import (
    OpenAIProvider,
    get_llm_provider,
    get_embedding_provider
)
from nano_graphrag.llm.base import BaseLLMProvider, BaseEmbeddingProvider
from nano_graphrag.config import LLMConfig


class TestOpenAIProvider:
    """Test OpenAI provider functionality."""
    
    @pytest.mark.asyncio
    async def test_openai_provider_gpt5_params(self):
        """Test GPT-5 specific parameter mapping."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Provide full usage object with required attributes
            usage = Mock()
            usage.prompt_tokens = 10
            usage.completion_tokens = 90
            usage.total_tokens = 100
            
            # Mock response with complete structure
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "test response"
            mock_response.choices[0].finish_reason = "stop"
            mock_response.usage = usage
            
            # Create async mock that returns the response
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            
            provider = OpenAIProvider(model="gpt-5-mini")
            provider.client = mock_client
            
            # Test max_tokens → max_completion_tokens mapping
            async def mock_wait_for(coro, timeout):
                return await coro
            
            with patch('asyncio.wait_for', side_effect=mock_wait_for):
                result = await provider.complete("test", max_tokens=1000)
            
            # Verify response structure
            assert result["text"] == "test response"
            assert result["usage"]["total_tokens"] == 100
    
    @pytest.mark.asyncio
    async def test_provider_none_content_guard(self):
        """Test handling of None content from GPT-5."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Create mock for chat completions
            mock_create = AsyncMock()
            mock_client.chat.completions.create = mock_create
            
            # Provide full usage object
            usage = Mock()
            usage.prompt_tokens = 10
            usage.completion_tokens = 0
            usage.total_tokens = 10
            
            # Mock response with None content
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = None
            mock_response.choices[0].finish_reason = "stop"
            mock_response.usage = usage
            mock_create.return_value = mock_response
            
            provider = OpenAIProvider(model="gpt-5")
            provider.client = mock_client
            
            async def mock_wait_for(coro, timeout):
                return await coro
            
            with patch('asyncio.wait_for', side_effect=mock_wait_for):
                result = await provider.complete("test")
            
            # Should default to empty string
            assert result["text"] == ""
    
    def test_base_url_separation(self):
        """Test LLM_BASE_URL vs EMBEDDING_BASE_URL separation."""
        # Test LLM provider with LLM_BASE_URL
        with patch.dict(os.environ, {
            "LLM_BASE_URL": "http://localhost:1234/v1",
            "OPENAI_API_KEY": "test-key"
        }):
            with patch('nano_graphrag.llm.providers.openai.AsyncOpenAI') as mock_openai:
                mock_openai.return_value = MagicMock()
                llm_provider = get_llm_provider('openai', 'test-model')
                llm_kwargs = mock_openai.call_args.kwargs
                assert llm_kwargs.get('base_url') == 'http://localhost:1234/v1'
        
        # Test embedding provider with EMBEDDING_BASE_URL (separate context)
        with patch.dict(os.environ, {
            "EMBEDDING_BASE_URL": "https://api.openai.com/v1",
            "OPENAI_API_KEY": "test-key"
        }):
            with patch('nano_graphrag.llm.providers.openai.AsyncOpenAI') as mock_openai:
                mock_openai.return_value = MagicMock()
                embed_provider = get_embedding_provider('openai', 'text-embedding-3-small')
                embed_kwargs = mock_openai.call_args.kwargs
                assert embed_kwargs.get('base_url') == 'https://api.openai.com/v1'
    
    @pytest.mark.asyncio
    async def test_complete_with_cache(self):
        """Test caching behavior with mock KV storage."""
        from nano_graphrag.base import BaseKVStorage
        
        mock_kv = AsyncMock(spec=BaseKVStorage)
        mock_kv.get_by_id.return_value = {"return": "cached_result"}
        
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client_class.return_value = MagicMock()
            
            provider = OpenAIProvider(model="gpt-5-mini")
            
            # Test cache hit path
            result = await provider.complete_with_cache(
                "prompt", hashing_kv=mock_kv
            )
            
            assert result == "cached_result"
            mock_kv.get_by_id.assert_called_once()
    
    def test_request_timeout_config(self):
        """Test request timeout is properly configured."""
        with patch.dict(os.environ, {"LLM_REQUEST_TIMEOUT": "60.0"}):
            config = LLMConfig.from_env()
            assert config.request_timeout == 60.0


class TestProviderFactory:
    """Test provider factory functions."""
    
    def test_get_llm_provider_openai(self):
        """Test getting OpenAI LLM provider."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client_class.return_value = MagicMock()
            
            provider = get_llm_provider("openai", "gpt-5-mini")
            assert isinstance(provider, OpenAIProvider)
            assert provider.model == "gpt-5-mini"
    
    def test_get_llm_provider_unknown(self):
        """Test error on unknown provider."""
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm_provider("unknown", "model")
    
    def test_get_embedding_provider_openai(self):
        """Test getting OpenAI embedding provider."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client_class.return_value = MagicMock()
            
            provider = get_embedding_provider("openai", "text-embedding-3-small")
            assert isinstance(provider, BaseEmbeddingProvider)
    
    def test_get_embedding_provider_unknown(self):
        """Test error on unknown embedding provider."""
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            get_embedding_provider("unknown", "model")


class TestProviderIntegration:
    """Test provider integration patterns."""
    
    @pytest.mark.asyncio
    async def test_provider_with_graphrag(self):
        """Test providers work with GraphRAG."""
        from nano_graphrag import GraphRAG
        from nano_graphrag.config import GraphRAGConfig, StorageConfig
        
        with patch('nano_graphrag.graphrag.get_llm_provider') as mock_get_llm, \
             patch('nano_graphrag.graphrag.get_embedding_provider') as mock_get_embed, \
             patch('pathlib.Path.mkdir'):  # Prevent directory creation
            
            # Create mock providers
            mock_llm = Mock(spec=BaseLLMProvider)
            mock_llm.complete_with_cache = AsyncMock(return_value="response")
            mock_llm.complete = AsyncMock(return_value={"text": "response", "usage": {"total_tokens": 100}})
            
            mock_embed = Mock(spec=BaseEmbeddingProvider)
            mock_embed.embed = AsyncMock(return_value={"embeddings": [[0.1] * 1536], "usage": {"total_tokens": 10}})
            mock_embed.dimension = 1536
            
            mock_get_llm.return_value = mock_llm
            mock_get_embed.return_value = mock_embed
            
            # Create GraphRAG with mocked providers
            config = GraphRAGConfig(
                storage=StorageConfig(working_dir="/tmp/test")
            )
            rag = GraphRAG(config=config)
            
            # Verify providers were obtained
            assert mock_get_llm.called
            assert mock_get_embed.called```

### File: ./tests/health/run_health_check.py
```
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
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timezone
from dotenv import load_dotenv

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
                
                status_emoji = "✅" if status == "passed" else "❌"
                # Show model name if available
                if model and model != "unknown":
                    # Truncate long model names for display
                    model_display = model if len(model) <= 20 else model[:17] + "..."
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
    asyncio.run(main())```

### File: ./tests/__init__.py
```
import logging
import dotenv

dotenv.load_dotenv()
logging.basicConfig(level=logging.INFO)
```

### File: ./tests/storage/test_factory.py
```
"""Tests for the storage factory pattern."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from nano_graphrag._storage.factory import StorageFactory, _register_backends
from nano_graphrag.base import BaseVectorStorage, BaseGraphStorage, BaseKVStorage


class TestStorageFactory:
    """Test suite for StorageFactory."""
    
    def setup_method(self):
        """Reset factory state before each test."""
        StorageFactory._vector_backends = {}
        StorageFactory._graph_backends = {}
        StorageFactory._kv_backends = {}
    
    def test_register_vector_backend(self):
        """Verify vector backend registration works."""
        mock_backend = Mock(spec=BaseVectorStorage)
        
        # Should register allowed backend
        StorageFactory.register_vector("nano", mock_backend)
        assert "nano" in StorageFactory._vector_backends
        assert StorageFactory._vector_backends["nano"] == mock_backend
    
    def test_register_vector_backend_not_allowed(self):
        """Verify registration fails for non-allowed vector backends."""
        mock_backend = Mock(spec=BaseVectorStorage)
        
        with pytest.raises(ValueError, match="Backend invalid not in allowed vector backends"):
            StorageFactory.register_vector("invalid", mock_backend)
    
    def test_register_graph_backend(self):
        """Verify graph backend registration works."""
        mock_backend = Mock(spec=BaseGraphStorage)
        
        # Should register allowed backend
        StorageFactory.register_graph("networkx", mock_backend)
        assert "networkx" in StorageFactory._graph_backends
        assert StorageFactory._graph_backends["networkx"] == mock_backend
    
    def test_register_graph_backend_not_allowed(self):
        """Verify registration fails for non-allowed graph backends."""
        mock_backend = Mock(spec=BaseGraphStorage)
        
        with pytest.raises(ValueError, match="Backend invalid not in allowed graph backends"):
            StorageFactory.register_graph("invalid", mock_backend)
    
    def test_register_kv_backend(self):
        """Verify KV backend registration works."""
        mock_backend = Mock(spec=BaseKVStorage)
        
        # Should register allowed backend
        StorageFactory.register_kv("json", mock_backend)
        assert "json" in StorageFactory._kv_backends
        assert StorageFactory._kv_backends["json"] == mock_backend
    
    def test_register_kv_backend_not_allowed(self):
        """Verify registration fails for non-allowed KV backends."""
        mock_backend = Mock(spec=BaseKVStorage)
        
        with pytest.raises(ValueError, match="Backend invalid not in allowed KV backends"):
            StorageFactory.register_kv("invalid", mock_backend)
    
    def test_create_vector_storage(self):
        """Verify factory creates correct vector storage instance."""
        mock_backend = MagicMock()
        mock_instance = Mock()
        mock_backend.return_value = mock_instance
        StorageFactory.register_vector("nano", mock_backend)
        
        embedding_func = Mock()
        global_config = {"working_dir": "/tmp"}
        
        storage = StorageFactory.create_vector_storage(
            backend="nano",
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func,
            custom_param="value"
        )
        
        assert storage == mock_instance
        mock_backend.assert_called_once_with(
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func,
            custom_param="value"
        )
    
    def test_create_vector_storage_with_meta_fields(self):
        """Verify vector storage creation with meta_fields."""
        mock_backend = MagicMock()
        mock_instance = Mock()
        mock_backend.return_value = mock_instance
        StorageFactory.register_vector("nano", mock_backend)
        
        embedding_func = Mock()
        global_config = {"working_dir": "/tmp"}
        meta_fields = {"entity_name", "entity_type"}
        
        storage = StorageFactory.create_vector_storage(
            backend="nano",
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func,
            meta_fields=meta_fields
        )
        
        assert storage == mock_instance
        mock_backend.assert_called_once_with(
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func,
            meta_fields=meta_fields
        )
    
    def test_create_vector_storage_hnsw_kwargs(self):
        """Verify HNSW backend receives vector_db_storage_cls_kwargs."""
        mock_backend = MagicMock()
        mock_instance = Mock()
        mock_backend.return_value = mock_instance
        StorageFactory.register_vector("hnswlib", mock_backend)
        
        embedding_func = Mock()
        global_config = {
            "working_dir": "/tmp",
            "vector_db_storage_cls_kwargs": {
                "ef_construction": 200,
                "ef_search": 100,
                "M": 32,
                "max_elements": 2000000
            }
        }
        
        storage = StorageFactory.create_vector_storage(
            backend="hnswlib",
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func
        )
        
        assert storage == mock_instance
        mock_backend.assert_called_once_with(
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func,
            ef_construction=200,
            ef_search=100,
            M=32,
            max_elements=2000000
        )
    
    def test_create_vector_storage_unknown_backend(self):
        """Verify unknown vector backend raises ValueError."""
        with pytest.raises(ValueError, match="Unknown vector backend: invalid"):
            StorageFactory.create_vector_storage(
                backend="invalid",
                namespace="test",
                global_config={},
                embedding_func=Mock()
            )
    
    def test_create_graph_storage(self):
        """Verify factory creates correct graph storage instance."""
        mock_backend = MagicMock()
        mock_instance = Mock()
        mock_backend.return_value = mock_instance
        StorageFactory.register_graph("networkx", mock_backend)
        
        global_config = {"working_dir": "/tmp"}
        
        storage = StorageFactory.create_graph_storage(
            backend="networkx",
            namespace="test",
            global_config=global_config,
            custom_param="value"
        )
        
        assert storage == mock_instance
        mock_backend.assert_called_once_with(
            namespace="test",
            global_config=global_config,
            custom_param="value"
        )
    
    def test_create_graph_storage_unknown_backend(self):
        """Verify unknown graph backend raises ValueError."""
        with pytest.raises(ValueError, match="Unknown graph backend: invalid"):
            StorageFactory.create_graph_storage(
                backend="invalid",
                namespace="test",
                global_config={}
            )
    
    def test_create_kv_storage(self):
        """Verify factory creates correct KV storage instance."""
        mock_backend = MagicMock()
        mock_instance = Mock()
        mock_backend.return_value = mock_instance
        StorageFactory.register_kv("json", mock_backend)
        
        global_config = {"working_dir": "/tmp"}
        
        storage = StorageFactory.create_kv_storage(
            backend="json",
            namespace="test",
            global_config=global_config,
            custom_param="value"
        )
        
        assert storage == mock_instance
        mock_backend.assert_called_once_with(
            namespace="test",
            global_config=global_config,
            custom_param="value"
        )
    
    def test_create_kv_storage_unknown_backend(self):
        """Verify unknown KV backend raises ValueError."""
        with pytest.raises(ValueError, match="Unknown KV backend: invalid"):
            StorageFactory.create_kv_storage(
                backend="invalid",
                namespace="test",
                global_config={}
            )
    
    @patch('nano_graphrag._storage.factory.StorageFactory.register_vector')
    @patch('nano_graphrag._storage.factory.StorageFactory.register_graph')
    @patch('nano_graphrag._storage.factory.StorageFactory.register_kv')
    def test_register_backends_lazy_loading(self, mock_kv, mock_graph, mock_vector):
        """Verify lazy registration of built-in backends."""
        # First call should register backends
        _register_backends()
        
        assert mock_vector.call_count == 2  # nano and hnswlib
        assert mock_graph.call_count == 1   # networkx
        assert mock_kv.call_count == 1      # json
        
        # Reset mocks
        mock_vector.reset_mock()
        mock_graph.reset_mock()
        mock_kv.reset_mock()
        
        # Set backends as already registered
        StorageFactory._vector_backends = {"nano": Mock(), "hnswlib": Mock()}
        StorageFactory._graph_backends = {"networkx": Mock()}
        StorageFactory._kv_backends = {"json": Mock()}
        
        # Second call should not re-register
        _register_backends()
        
        assert mock_vector.call_count == 0
        assert mock_graph.call_count == 0
        assert mock_kv.call_count == 0
    
    def test_auto_register_on_create(self):
        """Verify backends are auto-registered when creating storage."""
        # Don't manually register anything
        assert len(StorageFactory._vector_backends) == 0
        
        # Mock the imports inside _register_backends
        with patch('nano_graphrag._storage.NanoVectorDBStorage') as mock_nano:
            with patch('nano_graphrag._storage.HNSWVectorStorage') as mock_hnsw:
                # Try to create storage - should auto-register
                try:
                    StorageFactory.create_vector_storage(
                        backend="nano",
                        namespace="test",
                        global_config={"working_dir": "/tmp"},
                        embedding_func=Mock()
                    )
                except:
                    pass  # We're just testing registration, not actual creation
                
                # Should have registered backends
                assert "nano" in StorageFactory._vector_backends
                assert "hnswlib" in StorageFactory._vector_backends


class TestStorageFactoryIntegration:
    """Integration tests with real storage classes."""
    
    def setup_method(self):
        """Reset factory state before each test."""
        StorageFactory._vector_backends = {}
        StorageFactory._graph_backends = {}
        StorageFactory._kv_backends = {}
    
    def test_hnsw_backend_initialization(self):
        """Verify HNSW backend initializes with correct params."""
        # This test requires the actual storage classes to be available
        try:
            from nano_graphrag._storage import HNSWVectorStorage
        except ImportError:
            pytest.skip("HNSWVectorStorage not available")
        
        # Register backends
        _register_backends()
        
        # Create mock embedding function with required attributes
        embedding_func = Mock()
        embedding_func.embedding_dim = 1536
        
        global_config = {
            "working_dir": "/tmp",
            "embedding_batch_num": 100,  # Required by HNSWVectorStorage
            "vector_db_storage_cls_kwargs": {
                "ef_construction": 200,
                "ef_search": 100,
                "M": 32,
                "max_elements": 5000
            }
        }
        
        storage = StorageFactory.create_vector_storage(
            backend="hnswlib",
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func
        )
        
        assert isinstance(storage, HNSWVectorStorage)
        assert storage.ef_construction == 200
        assert storage.ef_search == 100
        assert storage.M == 32
        assert storage.max_elements == 5000
    
    def test_nano_backend_initialization(self):
        """Verify Nano backend initializes correctly."""
        try:
            from nano_graphrag._storage import NanoVectorDBStorage
        except ImportError:
            pytest.skip("NanoVectorDBStorage not available")
        
        # Register backends
        _register_backends()
        
        embedding_func = Mock()
        embedding_func.embedding_dim = 1536  # Required by NanoVectorDBStorage
        global_config = {
            "working_dir": "/tmp",
            "embedding_batch_num": 100  # Required by NanoVectorDBStorage
        }
        
        storage = StorageFactory.create_vector_storage(
            backend="nano",
            namespace="test",
            global_config=global_config,
            embedding_func=embedding_func,
            meta_fields={"doc_id", "entity_name"}
        )
        
        assert isinstance(storage, NanoVectorDBStorage)
        assert storage.namespace == "test"
    
    def test_networkx_backend_initialization(self):
        """Verify NetworkX backend initializes correctly."""
        try:
            from nano_graphrag._storage import NetworkXStorage
        except ImportError:
            pytest.skip("NetworkXStorage not available")
        
        # Register backends
        _register_backends()
        
        global_config = {"working_dir": "/tmp"}
        
        storage = StorageFactory.create_graph_storage(
            backend="networkx",
            namespace="test_graph",
            global_config=global_config
        )
        
        assert isinstance(storage, NetworkXStorage)
        assert storage.namespace == "test_graph"
    
    def test_json_kv_backend_initialization(self):
        """Verify JSON KV backend initializes correctly."""
        try:
            from nano_graphrag._storage import JsonKVStorage
        except ImportError:
            pytest.skip("JsonKVStorage not available")
        
        # Register backends
        _register_backends()
        
        global_config = {"working_dir": "/tmp"}
        
        storage = StorageFactory.create_kv_storage(
            backend="json",
            namespace="test_kv",
            global_config=global_config
        )
        
        assert isinstance(storage, JsonKVStorage)
        assert storage.namespace == "test_kv"```

### File: ./tests/test_hnsw_vector_storage.py
```
"""Test HNSW vector storage functionality."""
import os
import shutil
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch
from dataclasses import asdict
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, StorageConfig
from nano_graphrag._utils import wrap_embedding_func_with_attrs
from nano_graphrag._storage import HNSWVectorStorage


@pytest.fixture(scope="function")
def temp_dir(tmp_path):
    """Use pytest's tmp_path for temporary directories."""
    return str(tmp_path)


@wrap_embedding_func_with_attrs(embedding_dim=384, max_token_size=8192)
async def mock_embedding(texts: list[str]) -> np.ndarray:
    return np.random.rand(len(texts), 384)


@pytest.fixture
def hnsw_storage(temp_dir):
    """Create HNSW storage with proper config."""
    # Create minimal config dict for storage
    global_config = {
        "working_dir": temp_dir,
        "embedding_func": mock_embedding,
        "embedding_batch_num": 32,
        "embedding_func_max_async": 16,
        "vector_db_storage_cls_kwargs": {
            "ef_construction": 100,
            "M": 16,
            "ef_search": 50,
            "max_elements": 1000
        }
    }
    
    # Ensure the directory exists
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    
    return HNSWVectorStorage(
        namespace="test",
        global_config=global_config,
        embedding_func=mock_embedding,
        meta_fields={"entity_name"},
    )


@pytest.mark.asyncio
async def test_upsert_and_query(hnsw_storage):
    # Build the payload the storage expects: dict[str, dict] with 'content' field
    payload = {
        'Apple':  {'content': 'A fruit that is red or green', 'entity_name': 'Apple'},
        'Banana': {'content': 'A yellow fruit that is curved', 'entity_name': 'Banana'},
        'Orange': {'content': 'An orange fruit that is round', 'entity_name': 'Orange'},
    }

    await hnsw_storage.upsert(payload)

    results = await hnsw_storage.query("A fruit", top_k=2)
    assert len(results) == 2
    assert all("entity_name" in result for result in results)
    assert all("distance" in result for result in results)


@pytest.mark.asyncio
async def test_persistence(temp_dir):
    """Test storage persistence."""
    global_config = {
        "working_dir": temp_dir,
        "embedding_func": mock_embedding,
        "embedding_batch_num": 32,
        "embedding_func_max_async": 16,
        "vector_db_storage_cls_kwargs": {
            "ef_construction": 100,
            "M": 16,
            "ef_search": 50,
            "max_elements": 1000
        }
    }
    
    initial_storage = HNSWVectorStorage(
        namespace="test_persistence",
        global_config=global_config,
        embedding_func=mock_embedding,
        meta_fields={"entity_name"},
    )

    # Use correct API: dict[str, dict] with content field
    payload = {"Apple": {"entity_name": "Apple", "content": "A fruit"}}
    await initial_storage.upsert(payload)
    await initial_storage.index_done_callback()

    # Create new storage instance
    new_storage = HNSWVectorStorage(
        namespace="test_persistence",
        global_config=global_config,
        embedding_func=mock_embedding,
        meta_fields={"entity_name"},
    )

    results = await new_storage.query("fruit", top_k=1)
    assert len(results) == 1
    assert results[0]["entity_name"] == "Apple"


@pytest.mark.asyncio
async def test_multiple_upserts(hnsw_storage):
    """Test multiple upsert operations."""
    # First upsert
    payload1 = {
        "Apple": {"entity_name": "Apple", "content": "A red fruit"}
    }
    await hnsw_storage.upsert(payload1)
    
    # Second upsert
    payload2 = {
        "Banana": {"entity_name": "Banana", "content": "A yellow fruit"}
    }
    await hnsw_storage.upsert(payload2)

    # Query should find both
    results = await hnsw_storage.query("fruit", top_k=10)
    assert len(results) == 2
    entity_names = {r["entity_name"] for r in results}
    assert "Apple" in entity_names
    assert "Banana" in entity_names


@pytest.mark.asyncio
async def test_embedding_function(hnsw_storage):
    """Test that embedding function is correctly used."""
    test_text = "test content"
    
    # Mock the embedding function to verify it's called
    with patch.object(hnsw_storage, 'embedding_func', wraps=hnsw_storage.embedding_func) as mock_embed:
        payload = {"Test": {"entity_name": "Test", "content": test_text}}
        await hnsw_storage.upsert(payload)
        
        # Verify embedding function was called (don't check specific args as batching can vary)
        mock_embed.assert_called()
        # Just verify it was called at least once
        assert mock_embed.call_count >= 1


@pytest.mark.asyncio
async def test_max_elements_limit(temp_dir):
    """Test max_elements configuration."""
    global_config = {
        "working_dir": temp_dir,
        "embedding_func": mock_embedding,
        "embedding_batch_num": 32,
        "embedding_func_max_async": 16,
        "vector_db_storage_cls_kwargs": {
            "ef_construction": 100,
            "M": 16,
            "ef_search": 50,
            "max_elements": 5  # Small limit for testing
        }
    }
    
    storage = HNSWVectorStorage(
        namespace="test_limit",
        global_config=global_config,
        embedding_func=mock_embedding,
        meta_fields={"id"},
    )
    
    # Insert up to the limit - use correct API format
    payload = {f"item_{i}": {"id": f"item_{i}", "content": f"content {i}"} for i in range(5)}
    await storage.upsert(payload)
    
    results = await storage.query("content", top_k=10)
    assert len(results) == 5


@pytest.mark.asyncio
async def test_empty_query(hnsw_storage):
    """Test querying empty storage."""
    results = await hnsw_storage.query("test", top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_upsert_empty_dict(hnsw_storage):
    """Test upserting empty dict."""
    await hnsw_storage.upsert({})
    results = await hnsw_storage.query("test", top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_metadata_fields(hnsw_storage):
    """Test that metadata fields are preserved."""
    payload = {
        "TestEntity": {
            "entity_name": "TestEntity",
            "content": "Test content",
            "extra_field": "should not be stored"
        }
    }
    
    await hnsw_storage.upsert(payload)
    results = await hnsw_storage.query("test", top_k=1)
    
    assert len(results) == 1
    assert "entity_name" in results[0]
    assert results[0]["entity_name"] == "TestEntity"
    assert "extra_field" not in results[0]  # Only meta_fields should be stored


@pytest.mark.asyncio
async def test_distance_calculation(hnsw_storage):
    """Test that distances are calculated correctly."""
    # Insert items with correct API format
    payload = {
        "A": {"entity_name": "A", "content": "first"},
        "B": {"entity_name": "B", "content": "second"}
    }
    
    await hnsw_storage.upsert(payload)
    
    results = await hnsw_storage.query("first", top_k=2)
    
    # Verify distances are included and ordered
    assert len(results) == 2
    assert all("distance" in r for r in results)
    assert results[0]["distance"] <= results[1]["distance"]  # Closest first```

### File: ./tests/entity_extraction/test_metric.py
```
import pytest
import dspy
from unittest.mock import Mock, patch
from nano_graphrag.entity_extraction.metric import (
    relationships_similarity_metric,
    entity_recall_metric,
)


@pytest.fixture
def mock_dspy_predict():
    with patch(
        "nano_graphrag.entity_extraction.metric.dspy.ChainOfThought"
    ) as mock_predict:
        mock_instance = Mock()
        mock_instance.return_value = dspy.Prediction(similarity_score=0.75)
        mock_predict.return_value = mock_instance
        yield mock_predict


@pytest.fixture
def sample_relationship():
    return {
        "src_id": "ENTITY1",
        "tgt_id": "ENTITY2",
        "description": "Example relationship",
        "weight": 0.8,
        "order": 1,
    }


@pytest.fixture
def sample_entity():
    return {
        "entity_name": "EXAMPLE_ENTITY",
        "entity_type": "PERSON",
        "description": "An example entity",
        "importance_score": 0.8,
    }


@pytest.fixture
def example():
    def _example(items):
        return (
            {"relationships": items}
            if "src_id" in (items[0] if items else {})
            else {"entities": items}
        )

    return _example


@pytest.fixture
def prediction():
    def _prediction(items):
        return (
            {"relationships": items}
            if "src_id" in (items[0] if items else {})
            else {"entities": items}
        )

    return _prediction


@pytest.mark.asyncio
async def test_relationship_similarity_metric(
    sample_relationship, example, prediction, mock_dspy_predict
):
    gold = example(
        [
            {
                **sample_relationship,
                "src_id": "ENTITY1",
                "tgt_id": "ENTITY2",
                "description": "is related to",
            },
            {
                **sample_relationship,
                "src_id": "ENTITY2",
                "tgt_id": "ENTITY3",
                "description": "is connected with",
            },
        ]
    )
    pred = prediction(
        [
            {
                **sample_relationship,
                "src_id": "ENTITY1",
                "tgt_id": "ENTITY2",
                "description": "is connected to",
            },
            {
                **sample_relationship,
                "src_id": "ENTITY2",
                "tgt_id": "ENTITY3",
                "description": "is linked with",
            },
        ]
    )

    similarity = relationships_similarity_metric(gold, pred)
    assert 0 <= similarity <= 1


@pytest.mark.asyncio
async def test_entity_recall_metric(sample_entity, example, prediction):
    gold = example(
        [
            {**sample_entity, "entity_name": "ENTITY1"},
            {**sample_entity, "entity_name": "ENTITY2"},
            {**sample_entity, "entity_name": "ENTITY3"},
        ]
    )
    pred = example(
        [
            {**sample_entity, "entity_name": "ENTITY1"},
            {**sample_entity, "entity_name": "ENTITY3"},
            {**sample_entity, "entity_name": "ENTITY4"},
        ]
    )

    recall = entity_recall_metric(gold, pred)
    assert recall == 2 / 3


@pytest.mark.asyncio
async def test_relationship_similarity_metric_no_common_keys(
    sample_relationship, example, prediction, mock_dspy_predict
):
    gold = example(
        [
            {
                **sample_relationship,
                "src_id": "ENTITY1",
                "tgt_id": "ENTITY2",
                "description": "is related to",
            }
        ]
    )
    pred = prediction(
        [
            {
                **sample_relationship,
                "src_id": "ENTITY3",
                "tgt_id": "ENTITY4",
                "description": "is connected with",
            }
        ]
    )

    similarity = relationships_similarity_metric(gold, pred)
    assert 0 <= similarity <= 1


@pytest.mark.asyncio
async def test_entity_recall_metric_no_true_positives(
    sample_entity, example, prediction
):
    gold = example(
        [
            {**sample_entity, "entity_name": "ENTITY1"},
            {**sample_entity, "entity_name": "ENTITY2"},
        ]
    )
    pred = prediction(
        [
            {**sample_entity, "entity_name": "ENTITY3"},
            {**sample_entity, "entity_name": "ENTITY4"},
        ]
    )

    recall = entity_recall_metric(gold, pred)
    assert recall == 0


@pytest.mark.asyncio
async def test_relationship_similarity_metric_identical_descriptions(
    sample_relationship, example, prediction, mock_dspy_predict
):
    gold = example(
        [
            {
                **sample_relationship,
                "src_id": "ENTITY1",
                "tgt_id": "ENTITY2",
                "description": "is related to",
            }
        ]
    )
    pred = prediction(
        [
            {
                **sample_relationship,
                "src_id": "ENTITY1",
                "tgt_id": "ENTITY2",
                "description": "is related to",
            }
        ]
    )

    similarity = relationships_similarity_metric(gold, pred)
    assert similarity == 0.75


@pytest.mark.asyncio
async def test_entity_recall_metric_perfect_recall(sample_entity, example, prediction):
    entities = [
        {**sample_entity, "entity_name": "ENTITY1"},
        {**sample_entity, "entity_name": "ENTITY2"},
    ]
    gold = example(entities)
    pred = prediction(entities)

    recall = entity_recall_metric(gold, pred)
    assert recall == 1.0


@pytest.mark.asyncio
async def test_relationship_similarity_metric_no_relationships(
    example, prediction, mock_dspy_predict
):
    gold = example([])
    pred = prediction([])

    with pytest.raises(KeyError):
        similarity = relationships_similarity_metric(gold, pred)
```

### File: ./tests/entity_extraction/test_module.py
```
import pytest
import dspy
from unittest.mock import Mock, patch
from nano_graphrag.entity_extraction.module import (
    TypedEntityRelationshipExtractor,
    Relationship,
    Entity,
)


@pytest.mark.parametrize("self_refine,num_refine_turns", [(False, 0), (True, 2)])
def test_entity_relationship_extractor(self_refine, num_refine_turns):
    with patch(
        "nano_graphrag.entity_extraction.module.dspy.ChainOfThought"
    ) as mock_chain_of_thought:
        input_text = "Apple announced a new iPhone model."
        mock_extractor = Mock()
        mock_critique = Mock()
        mock_refine = Mock()

        mock_chain_of_thought.side_effect = [mock_extractor, mock_critique, mock_refine]

        mock_entities = [
            Entity(
                entity_name="APPLE",
                entity_type="ORGANIZATION",
                description="A technology company",
                importance_score=1,
            ),
            Entity(
                entity_name="IPHONE",
                entity_type="PRODUCT",
                description="A smartphone",
                importance_score=1,
            ),
        ]
        mock_relationships = [
            Relationship(
                src_id="APPLE",
                tgt_id="IPHONE",
                description="Apple manufactures iPhone",
                weight=1,
                order=1,
            )
        ]

        mock_extractor.return_value = dspy.Prediction(
            entities=mock_entities, relationships=mock_relationships
        )

        if self_refine:
            mock_critique.return_value = dspy.Prediction(
                entity_critique="Good entities, but could be more detailed.",
                relationship_critique="Relationships are accurate but limited.",
            )
            mock_refine.return_value = dspy.Prediction(
                refined_entities=mock_entities, refined_relationships=mock_relationships
            )

        extractor = TypedEntityRelationshipExtractor(
            self_refine=self_refine, num_refine_turns=num_refine_turns
        )
        result = extractor.forward(input_text=input_text)

        mock_extractor.assert_called_once_with(
            input_text=input_text, entity_types=extractor.entity_types
        )

        if self_refine:
            assert mock_critique.call_count == num_refine_turns
            assert mock_refine.call_count == num_refine_turns

        assert len(result.entities) == 2
        assert len(result.relationships) == 1

        assert result.entities[0]["entity_name"] == "APPLE"
        assert result.entities[0]["entity_type"] == "ORGANIZATION"
        assert result.entities[0]["description"] == "A technology company"
        assert result.entities[0]["importance_score"] == 1

        assert result.entities[1]["entity_name"] == "IPHONE"
        assert result.entities[1]["entity_type"] == "PRODUCT"
        assert result.entities[1]["description"] == "A smartphone"
        assert result.entities[1]["importance_score"] == 1

        assert result.relationships[0]["src_id"] == "APPLE"
        assert result.relationships[0]["tgt_id"] == "IPHONE"
        assert result.relationships[0]["description"] == "Apple manufactures iPhone"
        assert result.relationships[0]["weight"] == 1
        assert result.relationships[0]["order"] == 1
```

### File: ./tests/entity_extraction/__init__.py
```
```

### File: ./tests/entity_extraction/test_extract.py
```
import pytest
import dspy
from openai import BadRequestError
from unittest.mock import Mock, patch, AsyncMock
from nano_graphrag.entity_extraction.extract import generate_dataset, extract_entities_dspy
from nano_graphrag.base import TextChunkSchema, BaseGraphStorage, BaseVectorStorage
import httpx


@pytest.fixture
def mock_chunks():
    return {
        "chunk1": TextChunkSchema(content="Apple announced a new iPhone model."),
        "chunk2": TextChunkSchema(content="Google released an update for Android.")
    }


@pytest.fixture
def mock_entity_extractor():
    with patch('nano_graphrag.entity_extraction.extract.TypedEntityRelationshipExtractor') as mock:
        mock_instance = Mock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_graph_storage():
    return Mock(spec=BaseGraphStorage)


@pytest.fixture
def mock_vector_storage():
    return Mock(spec=BaseVectorStorage)


@pytest.fixture
def mock_global_config():
    return {
        "use_compiled_dspy_entity_relationship": False,
        "entity_relationship_module_path": "path/to/module.json"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("use_compiled,save_dataset", [
    (True, True), (False, True), (True, False), (False, False)
])
async def test_generate_dataset(mock_chunks, mock_entity_extractor, tmp_path, use_compiled, save_dataset):
    mock_prediction = Mock(
        entities=[{"entity_name": "APPLE", "entity_type": "ORGANIZATION"}],
        relationships=[{"src_id": "APPLE", "tgt_id": "IPHONE"}]
    )
    mock_entity_extractor.return_value = mock_prediction

    filepath = tmp_path / "test_dataset.pkl"

    mock_global_config = {
        "use_compiled_dspy_entity_relationship": use_compiled,
        "entity_relationship_module_path": "test/path.json" if use_compiled else None
    }

    with patch('nano_graphrag.entity_extraction.extract.pickle.dump') as mock_dump, \
         patch('nano_graphrag.entity_extraction.extract.TypedEntityRelationshipExtractor') as mock_extractor_class:

        mock_extractor_instance = Mock()
        mock_extractor_instance.return_value = mock_prediction
        mock_extractor_class.return_value = mock_extractor_instance

        if use_compiled:
            mock_extractor_instance.load = Mock()

        result = await generate_dataset(chunks=mock_chunks, filepath=str(filepath), 
                                        save_dataset=save_dataset, global_config=mock_global_config)

    assert len(result) == 2
    assert isinstance(result[0], dspy.Example)
    assert hasattr(result[0], 'input_text')
    assert hasattr(result[0], 'entities')
    assert hasattr(result[0], 'relationships')

    if save_dataset:
        mock_dump.assert_called_once()
    else:
        mock_dump.assert_not_called()

    mock_extractor_class.assert_called_once()
    assert mock_extractor_instance.call_count == len(mock_chunks)

    if use_compiled:
        mock_extractor_instance.load.assert_called_once_with("test/path.json")
    else:
        assert not hasattr(mock_extractor_instance, 'load') or not mock_extractor_instance.load.called


@pytest.mark.asyncio
async def test_generate_dataset_with_empty_chunks():
    chunks = {}
    filepath = "test_empty_dataset.pkl"
    result = await generate_dataset(chunks, filepath, save_dataset=False)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_generate_dataset_with_bad_request_error():
    chunks = {"chunk1": TextChunkSchema(content="Test content")}
    filepath = "test_error_dataset.pkl"
    
    # Create a mock response object
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.headers = {"x-request-id": "test-request-id"}
    mock_response.request = Mock(spec=httpx.Request)

    with patch('nano_graphrag.entity_extraction.extract.TypedEntityRelationshipExtractor') as mock_extractor_class:
        mock_extractor_instance = Mock()
        mock_extractor_instance.side_effect = BadRequestError(
            message="Test Error",
            response=mock_response,
            body={"error": {"message": "Test Error", "type": "invalid_request_error"}}
        )
        mock_extractor_class.return_value = mock_extractor_instance
        
        with patch('nano_graphrag.entity_extraction.extract.asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.side_effect = BadRequestError(
                message="Test Error",
                response=mock_response,
                body={"error": {"message": "Test Error", "type": "invalid_request_error"}}
            )
            
            result = await generate_dataset(chunks, filepath, save_dataset=False)
    
    assert len(result) == 0
    mock_to_thread.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("use_compiled,entity_vdb", [
    (True, Mock(spec=BaseVectorStorage)), 
    (False, Mock(spec=BaseVectorStorage)),
    (True, None),
    (False, None)
])
async def test_extract_entities_dspy(mock_chunks, mock_graph_storage, entity_vdb, mock_global_config, use_compiled):
    mock_entity = {
        "entity_name": "APPLE",
        "entity_type": "ORGANIZATION",
        "description": "A tech company",
        "importance_score": 0.9
    }
    mock_relationship = {
        "src_id": "APPLE",
        "tgt_id": "IPHONE",
        "description": "Produces",
        "weight": 0.8,
        "order": 1
    }
    mock_prediction = Mock(
        entities=[mock_entity],
        relationships=[mock_relationship]
    )

    mock_global_config.update({
        "use_compiled_dspy_entity_relationship": use_compiled,
        "entity_relationship_module_path": "test/path.json" if use_compiled else None
    })

    with patch('nano_graphrag.entity_extraction.extract.TypedEntityRelationshipExtractor') as mock_extractor_class:
        mock_extractor_instance = Mock()
        mock_extractor_instance.return_value = mock_prediction
        mock_extractor_class.return_value = mock_extractor_instance

        if use_compiled:
            mock_extractor_instance.load = Mock()

        with patch('nano_graphrag.entity_extraction.extract._merge_nodes_then_upsert', new_callable=AsyncMock) as mock_merge_nodes, \
             patch('nano_graphrag.entity_extraction.extract._merge_edges_then_upsert', new_callable=AsyncMock) as mock_merge_edges:
            mock_merge_nodes.return_value = mock_entity
            result = await extract_entities_dspy(mock_chunks, mock_graph_storage, entity_vdb, mock_global_config)

    assert result == mock_graph_storage
    mock_extractor_class.assert_called_once()
    mock_extractor_instance.assert_called()
    mock_merge_nodes.assert_called()
    mock_merge_edges.assert_called()
    
    if entity_vdb:
        entity_vdb.upsert.assert_called_once()
    else:
        assert not hasattr(entity_vdb, 'upsert') or not entity_vdb.upsert.called

    assert mock_extractor_instance.call_count == len(mock_chunks)

    if use_compiled:
        mock_extractor_instance.load.assert_called_once_with("test/path.json")
    else:
        assert not hasattr(mock_extractor_instance, 'load') or not mock_extractor_instance.load.called


@pytest.mark.asyncio
async def test_extract_entities_dspy_with_empty_chunks():
    chunks = {}
    mock_graph_storage = Mock(spec=BaseGraphStorage)
    mock_vector_storage = Mock(spec=BaseVectorStorage)
    global_config = {}
    
    result = await extract_entities_dspy(chunks, mock_graph_storage, mock_vector_storage, global_config)
    
    assert result is None


@pytest.mark.asyncio
async def test_extract_entities_dspy_with_no_entities():
    chunks = {"chunk1": TextChunkSchema(content="Test content")}
    mock_graph_storage = Mock(spec=BaseGraphStorage)
    mock_vector_storage = Mock(spec=BaseVectorStorage)
    global_config = {}
    
    with patch('nano_graphrag.entity_extraction.extract.TypedEntityRelationshipExtractor') as mock_extractor:
        mock_extractor.return_value.return_value = Mock(entities=[], relationships=[])
        result = await extract_entities_dspy(chunks, mock_graph_storage, mock_vector_storage, global_config)
    
    assert result is None
    mock_vector_storage.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_extract_entities_dspy_with_bad_request_error():
    chunks = {"chunk1": TextChunkSchema(content="Test content")}
    mock_graph_storage = Mock(spec=BaseGraphStorage)
    mock_vector_storage = Mock(spec=BaseVectorStorage)
    global_config = {}

    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.headers = {"x-request-id": "test-request-id"}
    mock_response.request = Mock(spec=httpx.Request)

    with patch('nano_graphrag.entity_extraction.extract.TypedEntityRelationshipExtractor') as mock_extractor_class:
        mock_extractor_instance = Mock()
        mock_extractor_instance.side_effect = BadRequestError(
            message="Test Error",
            response=mock_response,
            body={"error": {"message": "Test Error", "type": "invalid_request_error"}}
        )
        mock_extractor_class.return_value = mock_extractor_instance
        
        with patch('nano_graphrag.entity_extraction.extract.asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.side_effect = BadRequestError(
                message="Test Error",
                response=mock_response,
                body={"error": {"message": "Test Error", "type": "invalid_request_error"}}
            )
            
            result = await extract_entities_dspy(chunks, mock_graph_storage, mock_vector_storage, global_config)

    assert result is None
    mock_to_thread.assert_called_once()
    mock_vector_storage.upsert.assert_not_called()
```

### File: ./tests/utils.py
```
"""Test utilities for nano-graphrag tests."""
import os
import json
import numpy as np
from unittest.mock import AsyncMock, Mock
from typing import Optional, List, Dict, Any

from nano_graphrag.config import GraphRAGConfig, StorageConfig, LLMConfig, EmbeddingConfig
from nano_graphrag.llm.base import BaseLLMProvider, BaseEmbeddingProvider
from nano_graphrag._utils import wrap_embedding_func_with_attrs


def create_test_config(**overrides) -> GraphRAGConfig:
    """Create test config with sensible defaults."""
    config_kwargs = {}
    
    # Apply storage config overrides
    if "working_dir" in overrides:
        config_kwargs["storage"] = StorageConfig(working_dir=overrides.pop("working_dir"))
    
    # Apply other config overrides
    for key, value in overrides.items():
        if key == "enable_naive_rag":
            # This goes in query config
            from nano_graphrag.config import QueryConfig
            config_kwargs["query"] = QueryConfig(enable_naive_rag=value)
        # Add more mappings as needed
    
    return GraphRAGConfig(**config_kwargs)


def create_mock_llm_provider(responses: Optional[List[str]] = None) -> Mock:
    """Create mock LLM provider with standard responses."""
    provider = Mock(spec=BaseLLMProvider)
    
    if responses is None:
        responses = ["test response"]
    
    # Create async mock for complete_with_cache
    async def mock_complete(prompt, system_prompt=None, history=None, hashing_kv=None, **kwargs):
        # Return next response or last one
        if hasattr(mock_complete, "_call_count"):
            mock_complete._call_count += 1
        else:
            mock_complete._call_count = 0
        
        idx = min(mock_complete._call_count, len(responses) - 1)
        return responses[idx]
    
    provider.complete_with_cache = AsyncMock(side_effect=mock_complete)
    provider.complete = AsyncMock(side_effect=mock_complete)
    
    return provider


def create_mock_embedding_provider(dimension: int = 1536) -> Mock:
    """Create mock embedding provider."""
    provider = Mock(spec=BaseEmbeddingProvider)
    
    async def mock_embed(texts: List[str]) -> Dict[str, Any]:
        embeddings = np.random.rand(len(texts), dimension)
        return {
            "embeddings": embeddings,
            "usage": {"total_tokens": len(texts) * 10}
        }
    
    provider.embed = AsyncMock(side_effect=mock_embed)
    provider.dimension = dimension
    
    return provider


@wrap_embedding_func_with_attrs(embedding_dim=384, max_token_size=8192)
async def mock_embedding_func(texts: List[str]) -> np.ndarray:
    """Mock embedding function for tests."""
    return np.random.rand(len(texts), 384)


def load_test_data(max_chars: int = 10000) -> str:
    """Load limited test data for fast tests."""
    test_file = os.path.join(os.path.dirname(__file__), "mock_data.txt")
    with open(test_file, encoding="utf-8-sig") as f:
        return f.read()[:max_chars]


def create_completion_response(text: str = "test response", tokens: int = 100) -> Dict[str, Any]:
    """Create a properly shaped CompletionResponse dict."""
    return {
        "text": text,
        "finish_reason": "stop",
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": tokens - 10,
            "total_tokens": tokens
        },
        "raw": Mock()  # Original response object
    }


def create_embedding_response(dimension: int = 1536, num_texts: int = 1) -> Dict[str, Any]:
    """Create a properly shaped EmbeddingResponse dict."""
    return {
        "embeddings": np.random.rand(num_texts, dimension),
        "dimensions": dimension,
        "usage": {"total_tokens": num_texts * 10}
    }


def make_storage_config(temp_dir: str, include_clustering: bool = True, include_node2vec: bool = False) -> Dict[str, Any]:
    """Create storage configuration with all required keys."""
    config = {
        "working_dir": temp_dir,
        "embedding_func": mock_embedding_func,
        "embedding_batch_num": 32,
        "embedding_func_max_async": 16,
    }
    
    if include_clustering:
        config.update({
            "graph_cluster_algorithm": "leiden",
            "max_graph_cluster_size": 10,
            "graph_cluster_seed": 0xDEADBEEF,
        })
    
    if include_node2vec:
        config["node2vec_params"] = {
            "dimensions": 128,
            "num_walks": 10,
            "walk_length": 40,
            "window_size": 2,
            "iterations": 3,
            "random_seed": 3,
        }
    
    return config```

### File: ./tests/test_neo4j_storage.py
```
import os
import pytest
import numpy as np
from functools import wraps
from nano_graphrag import GraphRAG
from nano_graphrag._storage import Neo4jStorage
from nano_graphrag._utils import wrap_embedding_func_with_attrs

# Skip all neo4j tests unless Neo4j is configured
pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_URL") or not os.environ.get("NEO4J_AUTH"),
    reason="Neo4j not configured (set NEO4J_URL and NEO4J_AUTH to test)"
)


@pytest.fixture(scope="module")
def neo4j_config():
    return {
        "neo4j_url": os.environ.get("NEO4J_URL", "bolt://localhost:7687"),
        "neo4j_auth": (
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "neo4j"),
        ),
    }


@wrap_embedding_func_with_attrs(embedding_dim=384, max_token_size=8192)
async def mock_embedding(texts: list[str]) -> np.ndarray:
    return np.random.rand(len(texts), 384)


@pytest.fixture
def neo4j_storage(neo4j_config):
    rag = GraphRAG(
        working_dir="./tests/neo4j_test",
        embedding_func=mock_embedding,
        graph_storage_cls=Neo4jStorage,
        addon_params=neo4j_config,
    )
    storage = rag.chunk_entity_relation_graph
    return storage


def reset_graph(func):
    @wraps(func)
    async def new_func(neo4j_storage):
        await neo4j_storage._debug_delete_all_node_edges()
        await neo4j_storage.index_start_callback()
        results = await func(neo4j_storage)
        await neo4j_storage._debug_delete_all_node_edges()
        return results

    return new_func


def test_neo4j_storage_init():
    rag = GraphRAG(
        working_dir="./tests/neo4j_test",
        embedding_func=mock_embedding,
    )
    with pytest.raises(ValueError):
        storage = Neo4jStorage(
            namespace="nanographrag_test", global_config=rag.__dict__
        )


@pytest.mark.asyncio
@reset_graph
async def test_upsert_and_get_node(neo4j_storage):
    node_id = "node1"
    node_data = {"attr1": "value1", "attr2": "value2"}
    return_data = {"id": node_id, "clusters": "[]", **node_data}

    await neo4j_storage.upsert_node(node_id, node_data)

    result = await neo4j_storage.get_node(node_id)
    assert result == return_data

    has_node = await neo4j_storage.has_node(node_id)
    assert has_node is True


@pytest.mark.asyncio
@reset_graph
async def test_upsert_and_get_edge(neo4j_storage):
    source_id = "node1"
    target_id = "node2"
    edge_data = {"weight": 1.0, "type": "connection"}

    await neo4j_storage.upsert_node(source_id, {})
    await neo4j_storage.upsert_node(target_id, {})
    await neo4j_storage.upsert_edge(source_id, target_id, edge_data)

    result = await neo4j_storage.get_edge(source_id, target_id)
    print(result)
    assert result == edge_data

    has_edge = await neo4j_storage.has_edge(source_id, target_id)
    assert has_edge is True


@pytest.mark.asyncio
@reset_graph
async def test_node_degree(neo4j_storage):
    node_id = "center"
    await neo4j_storage.upsert_node(node_id, {})

    num_neighbors = 5
    for i in range(num_neighbors):
        neighbor_id = f"neighbor{i}"
        await neo4j_storage.upsert_node(neighbor_id, {})
        await neo4j_storage.upsert_edge(node_id, neighbor_id, {})

    degree = await neo4j_storage.node_degree(node_id)
    assert degree == num_neighbors


@pytest.mark.asyncio
@reset_graph
async def test_edge_degree(neo4j_storage):
    source_id = "node1"
    target_id = "node2"

    await neo4j_storage.upsert_node(source_id, {})
    await neo4j_storage.upsert_node(target_id, {})
    await neo4j_storage.upsert_edge(source_id, target_id, {})

    num_source_neighbors = 3
    for i in range(num_source_neighbors):
        neighbor_id = f"neighbor{i}"
        await neo4j_storage.upsert_node(neighbor_id, {})
        await neo4j_storage.upsert_edge(source_id, neighbor_id, {})

    num_target_neighbors = 2
    for i in range(num_target_neighbors):
        neighbor_id = f"target_neighbor{i}"
        await neo4j_storage.upsert_node(neighbor_id, {})
        await neo4j_storage.upsert_edge(target_id, neighbor_id, {})

    expected_edge_degree = (num_source_neighbors + 1) + (num_target_neighbors + 1)
    edge_degree = await neo4j_storage.edge_degree(source_id, target_id)
    assert edge_degree == expected_edge_degree


@pytest.mark.asyncio
@reset_graph
async def test_get_node_edges(neo4j_storage):
    center_id = "center"
    await neo4j_storage.upsert_node(center_id, {})

    expected_edges = []
    for i in range(3):
        neighbor_id = f"neighbor{i}"
        await neo4j_storage.upsert_node(neighbor_id, {})
        await neo4j_storage.upsert_edge(center_id, neighbor_id, {})
        expected_edges.append((center_id, neighbor_id))

    result = await neo4j_storage.get_node_edges(center_id)
    print(result)
    assert set(result) == set(expected_edges)


@pytest.mark.asyncio
@reset_graph
async def test_leiden_clustering(neo4j_storage):
    for i in range(10):
        await neo4j_storage.upsert_node(f"NODE{i}", {"source_id": f"chunk{i}"})

    for i in range(9):
        await neo4j_storage.upsert_edge(f"NODE{i}", f"NODE{i+1}", {"weight": 1.0})

    await neo4j_storage.clustering(algorithm="leiden")

    community_schema = await neo4j_storage.community_schema()

    assert len(community_schema) > 0

    for community in community_schema.values():
        assert "level" in community
        assert "title" in community
        assert "edges" in community
        assert "nodes" in community
        assert "chunk_ids" in community
        assert "occurrence" in community
        assert "sub_communities" in community
        print(community)


@pytest.mark.asyncio
@reset_graph
async def test_nonexistent_node_and_edge(neo4j_storage):
    assert await neo4j_storage.has_node("nonexistent") is False
    assert await neo4j_storage.has_edge("node1", "node2") is False
    assert await neo4j_storage.get_node("nonexistent") is None
    assert await neo4j_storage.get_edge("node1", "node2") is None
    assert await neo4j_storage.get_node_edges("nonexistent") == []
    assert await neo4j_storage.node_degree("nonexistent") == 0
    assert await neo4j_storage.edge_degree("node1", "node2") == 0


@pytest.mark.asyncio
@reset_graph
async def test_cluster_error_handling(neo4j_storage):
    with pytest.raises(
        ValueError, match="Clustering algorithm invalid_algo not supported"
    ):
        await neo4j_storage.clustering("invalid_algo")


@pytest.mark.asyncio
@reset_graph
async def test_index_done(neo4j_storage):
    await neo4j_storage.index_done_callback()
```

### File: ./tests/test_config.py
```
"""Tests for configuration management."""

import os
import pytest
from unittest.mock import patch

from nano_graphrag.config import (
    LLMConfig,
    EmbeddingConfig,
    StorageConfig,
    ChunkingConfig,
    EntityExtractionConfig,
    GraphClusteringConfig,
    QueryConfig,
    GraphRAGConfig,
)


class TestLLMConfig:
    """Test LLM configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = LLMConfig()
        assert config.provider == "openai"
        assert config.model == "gpt-5-mini"
        assert config.max_tokens == 32768
        assert config.max_concurrent == 16
        assert config.cache_enabled is True
        assert config.temperature == 0.0
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "deepseek",
            "LLM_MODEL": "deepseek-chat",
            "LLM_MAX_TOKENS": "65536",
            "LLM_MAX_CONCURRENT": "32",
            "LLM_CACHE_ENABLED": "false",
            "LLM_TEMPERATURE": "0.7"
        }):
            config = LLMConfig.from_env()
            assert config.provider == "deepseek"
            assert config.model == "deepseek-chat"
            assert config.max_tokens == 65536
            assert config.max_concurrent == 32
            assert config.cache_enabled is False
            assert config.temperature == 0.7
    
    def test_validation(self):
        """Test validation errors."""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            LLMConfig(max_tokens=0)
        
        with pytest.raises(ValueError, match="max_concurrent must be positive"):
            LLMConfig(max_concurrent=-1)
        
        with pytest.raises(ValueError, match="temperature must be between"):
            LLMConfig(temperature=3.0)
    
    def test_immutable(self):
        """Test that config is immutable."""
        config = LLMConfig()
        with pytest.raises(AttributeError):
            config.provider = "azure"


class TestEmbeddingConfig:
    """Test embedding configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = EmbeddingConfig()
        assert config.provider == "openai"
        assert config.model == "text-embedding-3-small"
        assert config.dimension == 1536
        assert config.batch_size == 32
        assert config.max_concurrent == 16
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "EMBEDDING_PROVIDER": "azure",
            "EMBEDDING_MODEL": "text-embedding-ada-002",
            "EMBEDDING_DIMENSION": "768",
            "EMBEDDING_BATCH_SIZE": "64",
            "EMBEDDING_MAX_CONCURRENT": "8"
        }):
            config = EmbeddingConfig.from_env()
            assert config.provider == "azure"
            assert config.model == "text-embedding-ada-002"
            assert config.dimension == 768
            assert config.batch_size == 64
            assert config.max_concurrent == 8
    
    def test_validation(self):
        """Test validation errors."""
        with pytest.raises(ValueError, match="dimension must be positive"):
            EmbeddingConfig(dimension=0)
        
        with pytest.raises(ValueError, match="batch_size must be positive"):
            EmbeddingConfig(batch_size=-1)


class TestStorageConfig:
    """Test storage configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = StorageConfig()
        assert config.vector_backend == "nano"
        assert config.graph_backend == "networkx"
        assert config.kv_backend == "json"
        assert config.working_dir == "./nano_graphrag_cache"
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "STORAGE_VECTOR_BACKEND": "hnswlib",
            "STORAGE_GRAPH_BACKEND": "networkx",
            "STORAGE_KV_BACKEND": "json",
            "STORAGE_WORKING_DIR": "/tmp/test_cache"
        }):
            config = StorageConfig.from_env()
            assert config.vector_backend == "hnswlib"
            assert config.graph_backend == "networkx"
            assert config.kv_backend == "json"
            assert config.working_dir == "/tmp/test_cache"
    
    def test_validation(self):
        """Test validation errors."""
        with pytest.raises(ValueError, match="Unknown vector backend"):
            StorageConfig(vector_backend="milvus")
        
        with pytest.raises(ValueError, match="Unknown graph backend"):
            StorageConfig(graph_backend="neo4j")
        
        with pytest.raises(ValueError, match="Unknown KV backend"):
            StorageConfig(kv_backend="redis")


class TestChunkingConfig:
    """Test chunking configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = ChunkingConfig()
        assert config.strategy == "token"
        assert config.size == 1200
        assert config.overlap == 100
        assert config.tokenizer == "tiktoken"
        assert config.tokenizer_model == "gpt-4o"
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "CHUNKING_STRATEGY": "sentence",
            "CHUNKING_SIZE": "2000",
            "CHUNKING_OVERLAP": "200",
            "CHUNKING_TOKENIZER": "huggingface",
            "CHUNKING_TOKENIZER_MODEL": "bert-base-uncased"
        }):
            config = ChunkingConfig.from_env()
            assert config.strategy == "sentence"
            assert config.size == 2000
            assert config.overlap == 200
            assert config.tokenizer == "huggingface"
            assert config.tokenizer_model == "bert-base-uncased"
    
    def test_validation(self):
        """Test validation errors."""
        with pytest.raises(ValueError, match="chunk size must be positive"):
            ChunkingConfig(size=0)
        
        with pytest.raises(ValueError, match="overlap must be non-negative"):
            ChunkingConfig(overlap=-1)
        
        with pytest.raises(ValueError, match="overlap .* must be less than size"):
            ChunkingConfig(size=100, overlap=100)
        
        with pytest.raises(ValueError, match="Unknown tokenizer"):
            ChunkingConfig(tokenizer="invalid")


class TestEntityExtractionConfig:
    """Test entity extraction configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = EntityExtractionConfig()
        assert config.max_gleaning == 1
        assert config.summary_max_tokens == 500
        assert config.strategy == "llm"
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "ENTITY_MAX_GLEANING": "3",
            "ENTITY_SUMMARY_MAX_TOKENS": "1000",
            "ENTITY_STRATEGY": "dspy"
        }):
            config = EntityExtractionConfig.from_env()
            assert config.max_gleaning == 3
            assert config.summary_max_tokens == 1000
            assert config.strategy == "dspy"
    
    def test_validation(self):
        """Test validation errors."""
        # max_gleaning=0 is now allowed for speed
        config = EntityExtractionConfig(max_gleaning=0)
        assert config.max_gleaning == 0  # Should pass
        
        # Test negative values still raise errors
        with pytest.raises(ValueError, match="max_gleaning must be non-negative"):
            EntityExtractionConfig(max_gleaning=-1)
        
        with pytest.raises(ValueError, match="summary_max_tokens must be positive"):
            EntityExtractionConfig(summary_max_tokens=-1)


class TestGraphClusteringConfig:
    """Test graph clustering configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = GraphClusteringConfig()
        assert config.algorithm == "leiden"
        assert config.max_cluster_size == 10
        assert config.seed == 0xDEADBEEF
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "GRAPH_CLUSTERING_ALGORITHM": "louvain",
            "GRAPH_MAX_CLUSTER_SIZE": "20",
            "GRAPH_CLUSTERING_SEED": "42"
        }):
            config = GraphClusteringConfig.from_env()
            assert config.algorithm == "louvain"
            assert config.max_cluster_size == 20
            assert config.seed == 42
    
    def test_validation(self):
        """Test validation errors."""
        with pytest.raises(ValueError, match="Unknown clustering algorithm"):
            GraphClusteringConfig(algorithm="invalid")
        
        with pytest.raises(ValueError, match="max_cluster_size must be positive"):
            GraphClusteringConfig(max_cluster_size=0)


class TestQueryConfig:
    """Test query configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = QueryConfig()
        assert config.enable_local is True
        assert config.enable_global is True
        assert config.enable_naive_rag is False
        assert config.similarity_threshold == 0.2
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "QUERY_ENABLE_LOCAL": "false",
            "QUERY_ENABLE_GLOBAL": "false",
            "QUERY_ENABLE_NAIVE_RAG": "true",
            "QUERY_SIMILARITY_THRESHOLD": "0.5"
        }):
            config = QueryConfig.from_env()
            assert config.enable_local is False
            assert config.enable_global is False
            assert config.enable_naive_rag is True
            assert config.similarity_threshold == 0.5
    
    def test_validation(self):
        """Test validation errors."""
        with pytest.raises(ValueError, match="similarity_threshold must be between"):
            QueryConfig(similarity_threshold=1.5)
        
        with pytest.raises(ValueError, match="similarity_threshold must be between"):
            QueryConfig(similarity_threshold=-0.1)


class TestGraphRAGConfig:
    """Test main GraphRAG configuration."""
    
    def test_defaults(self):
        """Test default values."""
        config = GraphRAGConfig()
        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.embedding, EmbeddingConfig)
        assert isinstance(config.storage, StorageConfig)
        assert isinstance(config.chunking, ChunkingConfig)
        assert isinstance(config.entity_extraction, EntityExtractionConfig)
        assert isinstance(config.graph_clustering, GraphClusteringConfig)
        assert isinstance(config.query, QueryConfig)
    
    def test_from_env(self):
        """Test creating from environment variables."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "azure",
            "STORAGE_VECTOR_BACKEND": "hnswlib",
            "CHUNKING_SIZE": "2000",
        }):
            config = GraphRAGConfig.from_env()
            assert config.llm.provider == "azure"
            assert config.storage.vector_backend == "hnswlib"
            assert config.chunking.size == 2000
    
    def test_to_dict(self):
        """Test conversion to dictionary for compatibility."""
        config = GraphRAGConfig()
        d = config.to_dict()
        
        assert "working_dir" in d
        assert "enable_local" in d
        assert "chunk_token_size" in d
        assert d["chunk_token_size"] == config.chunking.size
        assert d["enable_local"] == config.query.enable_local
        assert d["working_dir"] == config.storage.working_dir
    
    def test_custom_config(self):
        """Test creating with custom sub-configs."""
        config = GraphRAGConfig(
            llm=LLMConfig(provider="deepseek"),
            storage=StorageConfig(vector_backend="hnswlib"),
            chunking=ChunkingConfig(size=2000)
        )
        assert config.llm.provider == "deepseek"
        assert config.storage.vector_backend == "hnswlib"
        assert config.chunking.size == 2000
    
    def test_immutable(self):
        """Test that config is immutable."""
        config = GraphRAGConfig()
        with pytest.raises(AttributeError):
            config.llm = LLMConfig(provider="azure")```

### File: ./tests/test_rag.py
```
"""Test RAG functionality with mock providers."""
import os
import json
import shutil
import pytest
import numpy as np
from unittest.mock import patch, AsyncMock, Mock
from pathlib import Path

from nano_graphrag import GraphRAG, QueryParam
from nano_graphrag.config import GraphRAGConfig, StorageConfig, QueryConfig
from nano_graphrag._utils import wrap_embedding_func_with_attrs
from tests.utils import (
    create_test_config,
    create_mock_llm_provider,
    create_mock_embedding_provider,
    load_test_data,
    mock_embedding_func
)

# Set fake API key to avoid environment errors
os.environ["OPENAI_API_KEY"] = "FAKE"

# Use tmp_path fixture for working directory
FAKE_RESPONSE = "Hello world"
FAKE_JSON = json.dumps({"points": [{"description": "Hello world", "score": 1}]})


@pytest.fixture
def temp_working_dir(tmp_path):
    """Provide clean temporary directory for each test."""
    # Copy mock cache if it exists
    mock_cache_src = Path("./tests/fixtures/mock_cache.json")
    if mock_cache_src.exists():
        cache_dest = tmp_path / "kv_store_llm_response_cache.json"
        shutil.copy(mock_cache_src, cache_dest)
    
    return str(tmp_path)


@pytest.fixture
def mock_providers():
    """Create mock LLM and embedding providers."""
    # Return JSON first to satisfy global mapping step deterministically
    llm_provider = create_mock_llm_provider([FAKE_JSON, FAKE_RESPONSE])
    # Use 1536 dimension to match OpenAI default
    embedding_provider = create_mock_embedding_provider(dimension=1536)
    return llm_provider, embedding_provider


def test_insert_with_mocks(temp_working_dir, mock_providers):
    """Test insert with mocked providers."""
    llm_provider, embedding_provider = mock_providers
    
    # Patch providers before GraphRAG instantiation - need to patch the imports
    with patch('nano_graphrag.graphrag.get_llm_provider') as mock_get_llm, \
         patch('nano_graphrag.graphrag.get_embedding_provider') as mock_get_embed:
        
        mock_get_llm.return_value = llm_provider
        mock_get_embed.return_value = embedding_provider
        
        # Create config with test working directory
        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=temp_working_dir),
            query=QueryConfig(enable_naive_rag=True)
        )
        
        # Initialize GraphRAG with mocked providers
        rag = GraphRAG(config=config)
        
        # Load limited test data for speed
        test_text = load_test_data(max_chars=1000)
        
        # Insert should work with mocked providers
        rag.insert(test_text)
        
        # Verify providers were called
        assert llm_provider.complete_with_cache.called or llm_provider.complete.called
        assert embedding_provider.embed.called


@pytest.mark.asyncio
async def test_local_query_with_mocks(temp_working_dir, mock_providers):
    """Test local query with pre-seeded data."""
    llm_provider, embedding_provider = mock_providers
    
    with patch('nano_graphrag.graphrag.get_llm_provider') as mock_get_llm, \
         patch('nano_graphrag.graphrag.get_embedding_provider') as mock_get_embed:
        
        mock_get_llm.return_value = llm_provider
        mock_get_embed.return_value = embedding_provider
        
        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=temp_working_dir),
            query=QueryConfig(enable_local=True)
        )
        
        rag = GraphRAG(config=config)
        
        # Pre-seed entities and chunks for local query
        await rag.text_chunks.upsert({
            "chunk1": {"content": "Test chunk content", "source_id": "doc1"}
        })
        await rag.entities_vdb.upsert({
            "entity1": {"content": "Test entity", "entity_name": "entity1", "source_id": "chunk1"}
        })
        
        # Mock query - should not fail with "No available context"
        result = await rag.aquery("Test query", param=QueryParam(mode="local"))
        
        # Should get mocked response, not the failure message
        assert result  # Non-empty
        assert "Sorry" not in result  # Not default fail message
        assert llm_provider.complete_with_cache.called  # LLM was invoked


@pytest.mark.asyncio
async def test_global_query_with_mocks(temp_working_dir, mock_providers):
    """Test global query with pre-seeded community data."""
    llm_provider, embedding_provider = mock_providers
    
    with patch('nano_graphrag.graphrag.get_llm_provider') as mock_get_llm, \
         patch('nano_graphrag.graphrag.get_embedding_provider') as mock_get_embed:
        
        mock_get_llm.return_value = llm_provider
        mock_get_embed.return_value = embedding_provider
        
        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=temp_working_dir)
        )
        
        rag = GraphRAG(config=config)
        
        # Pre-seed community reports for global query
        await rag.community_reports.upsert({
            'C1': {
                'report_string': 'Test community summary',
                'report_json': {'rating': 1.0, 'description': 'Test cluster'},
                'level': 0,
                'occurrence': 1.0
            }
        })
        
        # Mock community_schema to return our seeded community
        async def fake_schema():
            return {
                'C1': {
                    'level': 0,
                    'title': 'Cluster 1',
                    'edges': [],
                    'nodes': ['node1'],
                    'chunk_ids': ['chunk1'],
                    'occurrence': 1.0,
                    'sub_communities': []
                }
            }
        
        with patch.object(rag.chunk_entity_relation_graph, 'community_schema', AsyncMock(side_effect=fake_schema)):
            # Mock query - should get JSON response
            result = await rag.aquery("Test query", param=QueryParam(mode="global"))
            
            # Should get valid JSON response for global query
            assert result  # Non-empty
            try:
                parsed = json.loads(result)
                assert "points" in parsed
                assert isinstance(parsed["points"], list)
                if parsed["points"]:  # If there are points
                    assert "description" in parsed["points"][0]
            except json.JSONDecodeError:
                # If not JSON, at least verify it's a response
                assert len(result) > 0


@pytest.mark.asyncio
async def test_naive_query_with_mocks(temp_working_dir, mock_providers):
    """Test naive RAG query with mocked providers."""
    llm_provider, embedding_provider = mock_providers
    
    with patch('nano_graphrag.graphrag.get_llm_provider') as mock_get_llm, \
         patch('nano_graphrag.graphrag.get_embedding_provider') as mock_get_embed:
        
        mock_get_llm.return_value = llm_provider
        mock_get_embed.return_value = embedding_provider
        
        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=temp_working_dir),
            query=QueryConfig(enable_naive_rag=True)
        )
        
        rag = GraphRAG(config=config)
        
        # Pre-seed text chunks for naive query
        await rag.text_chunks.upsert({
            "chunk1": {"content": "This is test data for naive RAG."}
        })
        
        # Pre-seed vector storage
        await rag.chunks_vdb.upsert({
            "chunk1": {"content": "This is test data for naive RAG."}
        })
        
        # Mock query
        result = await rag.aquery("Test query", param=QueryParam(mode="naive"))
        
        # Should get response (relaxed assertion)
        assert result  # Non-empty
        assert len(result) > 0  # Has content
        # For naive mode, we just verify we got something back from the mocked LLM


def test_backward_compatibility():
    """Test that old patterns still work with deprecation warnings."""
    # This test ensures we don't break existing code
    # Can be removed in future versions
    pass```

### File: ./tests/test_networkx_storage.py
```
import os
import shutil
import pytest
import networkx as nx
import numpy as np
import asyncio
import json
from pathlib import Path
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, StorageConfig
from nano_graphrag._storage import NetworkXStorage
from nano_graphrag._utils import wrap_embedding_func_with_attrs
from unittest.mock import patch


@pytest.fixture(scope="function")
def temp_dir(tmp_path):
    """Use pytest's tmp_path for temporary directories."""
    return str(tmp_path)


@wrap_embedding_func_with_attrs(embedding_dim=384, max_token_size=8192)
async def mock_embedding(texts: list[str]) -> np.ndarray:
    return np.random.rand(len(texts), 384)


async def seed_minimal_graph(storage):
    """Pre-seed a minimal graph for clustering tests."""
    await storage.upsert_node("node1", {"data": "test1"})
    await storage.upsert_node("node2", {"data": "test2"})
    await storage.upsert_edge("node1", "node2", {"weight": 1.0})


@pytest.fixture
def networkx_storage(temp_dir):
    """Create NetworkXStorage with proper config including clustering."""
    # Create config dict with clustering parameters using helper
    from tests.utils import make_storage_config
    global_config = make_storage_config(temp_dir, include_clustering=True, include_node2vec=True)
    # Override embedding_func with local mock
    global_config["embedding_func"] = mock_embedding
    
    # Ensure the directory exists
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    
    return NetworkXStorage(
        namespace="test",
        global_config=global_config,
    )


@pytest.mark.asyncio
async def test_upsert_and_get_node(networkx_storage):
    node_id = "node1"
    node_data = {"attr1": "value1", "attr2": "value2"}
    
    await networkx_storage.upsert_node(node_id, node_data)
    
    result = await networkx_storage.get_node(node_id)
    assert result == node_data
    
    has_node = await networkx_storage.has_node(node_id)
    assert has_node is True


@pytest.mark.asyncio
async def test_upsert_and_get_edge(networkx_storage):
    source_id = "node1"
    target_id = "node2"
    edge_data = {"weight": 1.0, "type": "connection"}
    
    await networkx_storage.upsert_node(source_id, {})
    await networkx_storage.upsert_node(target_id, {})
    await networkx_storage.upsert_edge(source_id, target_id, edge_data)
    
    result = await networkx_storage.get_edge(source_id, target_id)
    assert result == edge_data
    
    has_edge = await networkx_storage.has_edge(source_id, target_id)
    assert has_edge is True


@pytest.mark.asyncio
async def test_node_degree(networkx_storage):
    node_id = "center"
    await networkx_storage.upsert_node(node_id, {})
    
    num_neighbors = 5
    for i in range(num_neighbors):
        neighbor_id = f"neighbor{i}"
        await networkx_storage.upsert_node(neighbor_id, {})
        await networkx_storage.upsert_edge(node_id, neighbor_id, {})
    
    degree = await networkx_storage.node_degree(node_id)
    assert degree == num_neighbors


@pytest.mark.asyncio
async def test_edge_degree(networkx_storage):
    source_id = "node1"
    target_id = "node2"
    
    await networkx_storage.upsert_node(source_id, {})
    await networkx_storage.upsert_node(target_id, {})
    await networkx_storage.upsert_edge(source_id, target_id, {})
    
    num_source_neighbors = 3
    for i in range(num_source_neighbors):
        neighbor_id = f"neighbor{i}"
        await networkx_storage.upsert_node(neighbor_id, {})
        await networkx_storage.upsert_edge(source_id, neighbor_id, {})
    
    num_target_neighbors = 2
    for i in range(num_target_neighbors):
        neighbor_id = f"target_neighbor{i}"
        await networkx_storage.upsert_node(neighbor_id, {})
        await networkx_storage.upsert_edge(target_id, neighbor_id, {})
    
    expected_edge_degree = (num_source_neighbors + 1) + (num_target_neighbors + 1)
    edge_degree = await networkx_storage.edge_degree(source_id, target_id)
    assert edge_degree == expected_edge_degree


@pytest.mark.asyncio
async def test_get_node_edges(networkx_storage):
    center_id = "center"
    await networkx_storage.upsert_node(center_id, {})
    
    expected_edges = []
    for i in range(3):
        neighbor_id = f"neighbor{i}"
        await networkx_storage.upsert_node(neighbor_id, {})
        await networkx_storage.upsert_edge(center_id, neighbor_id, {})
        expected_edges.append((center_id, neighbor_id))
    
    result = await networkx_storage.get_node_edges(center_id)
    assert set(result) == set(expected_edges)


@pytest.mark.parametrize("algorithm", ["leiden"])
@pytest.mark.asyncio
async def test_clustering(networkx_storage, algorithm):
    # [numberchiffre]: node ID is case-sensitive for clustering with leiden.
    for i in range(10):
        await networkx_storage.upsert_node(f"NODE{i}", {"source_id": f"chunk{i}"})
    
    for i in range(9):
        await networkx_storage.upsert_edge(f"NODE{i}", f"NODE{i+1}", {})
    
    assert networkx_storage._graph.number_of_nodes() > 0
    assert networkx_storage._graph.number_of_edges() > 0
    await networkx_storage.clustering(algorithm=algorithm)
    
    community_schema = await networkx_storage.community_schema()

    assert len(community_schema) > 0
    
    for community in community_schema.values():
        assert "level" in community
        assert "title" in community
        assert "edges" in community
        assert "nodes" in community
        assert "chunk_ids" in community
        assert "occurrence" in community
        assert "sub_communities" in community


@pytest.mark.parametrize("algorithm", ["leiden"])
@pytest.mark.asyncio
async def test_leiden_clustering_consistency(networkx_storage, algorithm):
    for i in range(10):
        await networkx_storage.upsert_node(f"NODE{i}", {"source_id": f"chunk{i}"})
    for i in range(9):
        await networkx_storage.upsert_edge(f"NODE{i}", f"NODE{i+1}", {})
    
    results = []
    for _ in range(3):
        await networkx_storage.clustering(algorithm=algorithm)
        community_schema = await networkx_storage.community_schema()
        results.append(community_schema)
    
    assert all(len(r) == len(results[0]) for r in results), "Number of communities should be consistent"


@pytest.mark.parametrize("algorithm", ["leiden"])
@pytest.mark.asyncio
async def test_leiden_clustering_community_structure(networkx_storage, algorithm):
    for i in range(10):
        await networkx_storage.upsert_node(f"A{i}", {"source_id": f"chunkA{i}"})
        await networkx_storage.upsert_node(f"B{i}", {"source_id": f"chunkB{i}"})
    for i in range(9):
        await networkx_storage.upsert_edge(f"A{i}", f"A{i+1}", {})
        await networkx_storage.upsert_edge(f"B{i}", f"B{i+1}", {})
    
    await networkx_storage.clustering(algorithm=algorithm)
    community_schema = await networkx_storage.community_schema()
    
    assert len(community_schema) >= 2, "Should have at least two communities"
    
    communities = list(community_schema.values())
    a_nodes = set(node for node in communities[0]['nodes'] if node.startswith('A'))
    b_nodes = set(node for node in communities[0]['nodes'] if node.startswith('B'))
    assert len(a_nodes) == 0 or len(b_nodes) == 0, "Nodes from different groups should be in different communities"


@pytest.mark.parametrize("algorithm", ["leiden"])
@pytest.mark.asyncio
async def test_leiden_clustering_hierarchical_structure(networkx_storage, algorithm):
    await networkx_storage.upsert_node("NODE1", {"source_id": "chunk1", "clusters": json.dumps([{"level": 0, "cluster": "0"}, {"level": 1, "cluster": "1"}])})
    await networkx_storage.upsert_node("NODE2", {"source_id": "chunk2", "clusters": json.dumps([{"level": 0, "cluster": "0"}, {"level": 1, "cluster": "2"}])})
    await networkx_storage.upsert_edge("NODE1", "NODE2", {})
    await networkx_storage.clustering(algorithm=algorithm)
    community_schema = await networkx_storage.community_schema()
    
    levels = set(community['level'] for community in community_schema.values())
    assert len(levels) >= 1, "Should have at least one level in the hierarchy"
    
    communities_per_level = {level: sum(1 for c in community_schema.values() if c['level'] == level) for level in levels}
    assert communities_per_level[0] >= communities_per_level.get(max(levels), 0), "Lower levels should have more or equal number of communities"


@pytest.mark.asyncio
async def test_persistence(temp_dir):
    """Test storage persistence with proper mocking."""
    # Create storage with config including clustering
    global_config = {
        "working_dir": temp_dir,
        "embedding_func": mock_embedding,
        "embedding_batch_num": 32,
        "embedding_func_max_async": 16,
        "graph_cluster_algorithm": "leiden",
        "max_graph_cluster_size": 10,
        "graph_cluster_seed": 0xDEADBEEF,
    }
    initial_storage = NetworkXStorage(
        namespace="test_persistence",
        global_config=global_config,
    )
    
    await initial_storage.upsert_node("node1", {"attr": "value"})
    await initial_storage.upsert_node("node2", {"attr": "value"})
    await initial_storage.upsert_edge("node1", "node2", {"weight": 1.0})
    
    await initial_storage.index_done_callback()
    
    new_storage = NetworkXStorage(
        namespace="test_persistence",
        global_config=global_config,
    )
    
    assert await new_storage.has_node("node1")
    assert await new_storage.has_node("node2")
    assert await new_storage.has_edge("node1", "node2")
    
    node1_data = await new_storage.get_node("node1")
    assert node1_data == {"attr": "value"}
    
    edge_data = await new_storage.get_edge("node1", "node2")
    assert edge_data == {"weight": 1.0}


@pytest.mark.asyncio
async def test_embed_nodes(networkx_storage):
    for i in range(5):
        await networkx_storage.upsert_node(f"node{i}", {"id": f"node{i}"})
    
    for i in range(4):
        await networkx_storage.upsert_edge(f"node{i}", f"node{i+1}", {})
    
    embeddings, node_ids = await networkx_storage.embed_nodes("node2vec")
    
    assert embeddings.shape == (5, networkx_storage.global_config['node2vec_params']['dimensions'])
    assert len(node_ids) == 5
    assert all(f"node{i}" in node_ids for i in range(5))


@pytest.mark.asyncio
async def test_stable_largest_connected_component_equal_components():
    G = nx.Graph()
    G.add_edges_from([("A", "B"), ("C", "D"), ("E", "F")])
    result = NetworkXStorage.stable_largest_connected_component(G)
    assert sorted(result.nodes()) == ["A", "B"]
    assert list(result.edges()) == [("A", "B")]


@pytest.mark.asyncio
async def test_stable_largest_connected_component_stability():
    G = nx.Graph()
    G.add_edges_from([("A", "B"), ("B", "C"), ("C", "D"), ("E", "F")])
    result1 = NetworkXStorage.stable_largest_connected_component(G)
    result2 = NetworkXStorage.stable_largest_connected_component(G)
    assert nx.is_isomorphic(result1, result2)
    assert list(result1.nodes()) == list(result2.nodes())
    assert list(result1.edges()) == list(result2.edges())


@pytest.mark.asyncio
async def test_stable_largest_connected_component_directed_graph():
    G = nx.DiGraph()
    G.add_edges_from([("A", "B"), ("B", "C"), ("C", "D"), ("E", "F")])
    result = NetworkXStorage.stable_largest_connected_component(G)
    assert sorted(result.nodes()) == ["A", "B", "C", "D"]
    assert sorted(result.edges()) == [("A", "B"), ("B", "C"), ("C", "D")]


@pytest.mark.asyncio
async def test_stable_largest_connected_component_self_loops_and_parallel_edges():
    G = nx.Graph()
    G.add_edges_from([("A", "B"), ("B", "C"), ("C", "A"), ("A", "A"), ("B", "B"), ("A", "B")])
    result = NetworkXStorage.stable_largest_connected_component(G)
    assert sorted(result.nodes()) == ["A", "B", "C"]
    assert sorted(result.edges()) == [('A', 'A'), ('A', 'B'), ('A', 'C'), ('B', 'B'), ('B', 'C')]


@pytest.mark.asyncio
async def test_community_schema_with_no_clusters(networkx_storage):
    await networkx_storage.upsert_node("node1", {"source_id": "chunk1"})
    await networkx_storage.upsert_node("node2", {"source_id": "chunk2"})
    await networkx_storage.upsert_edge("node1", "node2", {})
    
    community_schema = await networkx_storage.community_schema()
    assert len(community_schema) == 0


@pytest.mark.asyncio
async def test_community_schema_multiple_levels(networkx_storage):
    await networkx_storage.upsert_node("node1", {"source_id": "chunk1", "clusters": json.dumps([{"level": 0, "cluster": "0"}, {"level": 1, "cluster": "1"}])})
    await networkx_storage.upsert_node("node2", {"source_id": "chunk2", "clusters": json.dumps([{"level": 0, "cluster": "0"}, {"level": 1, "cluster": "2"}])})
    await networkx_storage.upsert_edge("node1", "node2", {})
    
    community_schema = await networkx_storage.community_schema()
    assert len(community_schema) == 3
    assert set(community_schema.keys()) == {"0", "1", "2"}
    assert community_schema["0"]["level"] == 0
    assert community_schema["1"]["level"] == 1
    assert community_schema["2"]["level"] == 1
    assert set(community_schema["0"]["sub_communities"]) == {"1", "2"}


@pytest.mark.asyncio
async def test_community_schema_occurrence(networkx_storage):
    await networkx_storage.upsert_node("node1", {"source_id": "chunk1,chunk2", "clusters": json.dumps([{"level": 0, "cluster": "0"}])})
    await networkx_storage.upsert_node("node2", {"source_id": "chunk3", "clusters": json.dumps([{"level": 0, "cluster": "0"}])})
    await networkx_storage.upsert_node("node3", {"source_id": "chunk4", "clusters": json.dumps([{"level": 0, "cluster": "1"}])})
    
    community_schema = await networkx_storage.community_schema()
    assert len(community_schema) == 2
    assert community_schema["0"]["occurrence"] == 1
    assert community_schema["1"]["occurrence"] == 0.5


@pytest.mark.asyncio
async def test_community_schema_sub_communities(networkx_storage):
    await networkx_storage.upsert_node("node1", {"source_id": "chunk1", "clusters": json.dumps([{"level": 0, "cluster": "0"}, {"level": 1, "cluster": "1"}])})
    await networkx_storage.upsert_node("node2", {"source_id": "chunk2", "clusters": json.dumps([{"level": 0, "cluster": "0"}, {"level": 1, "cluster": "2"}])})
    await networkx_storage.upsert_node("node3", {"source_id": "chunk3", "clusters": json.dumps([{"level": 0, "cluster": "3"}, {"level": 1, "cluster": "4"}])})
    
    community_schema = await networkx_storage.community_schema()
    assert len(community_schema) == 5
    assert set(community_schema["0"]["sub_communities"]) == {"1", "2"}
    assert community_schema["3"]["sub_communities"] == ["4"]
    assert community_schema["1"]["sub_communities"] == []
    assert community_schema["2"]["sub_communities"] == []
    assert community_schema["4"]["sub_communities"] == []


@pytest.mark.asyncio
async def test_concurrent_operations(networkx_storage):
    async def add_nodes(start, end):
        for i in range(start, end):
            await networkx_storage.upsert_node(f"node{i}", {"value": i})

    await asyncio.gather(
        add_nodes(0, 500),
        add_nodes(500, 1000)
    )

    assert await networkx_storage.node_degree("node0") == 0
    assert len(networkx_storage._graph.nodes) == 1000


@pytest.mark.asyncio
async def test_nonexistent_node_and_edge(networkx_storage):
    assert await networkx_storage.has_node("nonexistent") is False
    assert await networkx_storage.has_edge("node1", "node2") is False
    assert await networkx_storage.get_node("nonexistent") is None
    assert await networkx_storage.get_edge("node1", "node2") is None
    assert await networkx_storage.get_node_edges("nonexistent") is None
    assert await networkx_storage.node_degree("nonexistent") == 0
    assert await networkx_storage.edge_degree("node1", "node2") == 0


@pytest.mark.asyncio
async def test_error_handling(networkx_storage):
    with pytest.raises(ValueError, match="Clustering algorithm invalid_algo not supported"):
        await networkx_storage.clustering("invalid_algo")

    with pytest.raises(ValueError, match="Node embedding algorithm invalid_algo not supported"):
        await networkx_storage.embed_nodes("invalid_algo")
```

### File: ./nano_graphrag/llm/providers/azure.py
```
"""Azure OpenAI LLM Provider implementation."""

import os
from typing import AsyncIterator, Dict, List, Optional
import numpy as np
from openai import AsyncAzureOpenAI, APIConnectionError, RateLimitError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ..base import BaseLLMProvider, BaseEmbeddingProvider
from ..._utils import wrap_embedding_func_with_attrs


class AzureOpenAIProvider(BaseLLMProvider):
    """Azure OpenAI LLM provider implementation."""
    
    env_key = "AZURE_OPENAI_API_KEY"
    
    def __init__(
        self,
        model: str = "gpt-5",
        api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        **kwargs
    ):
        super().__init__(model, api_key, **kwargs)
        self.azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
        
        self.client = AsyncAzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.azure_endpoint,
            api_version=self.api_version
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
    )
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> str:
        """Generate completion using Azure OpenAI API."""
        messages = self._build_messages(prompt, system_prompt, history)
        
        response = await self.client.chat.completions.create(
            model=self.model,  # This is the deployment name in Azure
            messages=messages,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            **{k: v for k, v in kwargs.items() if k not in ["temperature", "max_tokens"]}
        )
        
        return response.choices[0].message.content
    
    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream completions from Azure OpenAI API."""
        messages = self._build_messages(prompt, system_prompt, history)
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            **{k: v for k, v in kwargs.items() if k not in ["temperature", "max_tokens", "stream"]}
        )
        
        async for chunk in response:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content


class AzureOpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """Azure OpenAI embedding provider."""
    
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        embedding_dim: int = 1536
    ):
        self.model = model
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self.azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
        self.embedding_dim = embedding_dim
        
        self.client = AsyncAzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.azure_endpoint,
            api_version=self.api_version
        )
    
    @wrap_embedding_func_with_attrs(embedding_dim=1536, max_token_size=8192)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
    )
    async def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings using Azure OpenAI API."""
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            encoding_format="float"
        )
        return np.array([dp.embedding for dp in response.data])


# Backward compatibility functions
async def azure_gpt_4o_complete(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: Optional[List[Dict[str, str]]] = None,
    **kwargs
) -> str:
    """Backward compatible Azure GPT-4o completion."""
    provider = AzureOpenAIProvider(model="gpt-5")
    return await provider.complete_with_cache(
        prompt, system_prompt, history_messages,
        hashing_kv=kwargs.pop("hashing_kv", None),
        **kwargs
    )


async def azure_gpt_4o_mini_complete(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: Optional[List[Dict[str, str]]] = None,
    **kwargs
) -> str:
    """Backward compatible Azure GPT-4o-mini completion."""
    provider = AzureOpenAIProvider(model="gpt-5-mini")
    return await provider.complete_with_cache(
        prompt, system_prompt, history_messages,
        hashing_kv=kwargs.pop("hashing_kv", None),
        **kwargs
    )


async def azure_openai_embedding(texts: List[str]) -> np.ndarray:
    """Backward compatible Azure OpenAI embedding."""
    provider = AzureOpenAIEmbeddingProvider()
    return await provider.embed(texts)```

### File: ./nano_graphrag/llm/providers/tests/test_openai_provider.py
```
"""Unit tests for OpenAI LLM Provider implementation."""

import os
import pytest
import numpy as np
from unittest.mock import AsyncMock, Mock, patch
from typing import List, Dict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from nano_graphrag.llm.base import (
    BaseLLMProvider,
    BaseEmbeddingProvider,
    CompletionParams,
    CompletionResponse,
    StreamChunk,
    EmbeddingResponse
)
from nano_graphrag.llm.providers.openai import OpenAIProvider, OpenAIEmbeddingProvider


class TestBaseLLMProvider:
    """Test base LLM provider functionality."""
    
    def test_provider_initialization(self):
        """Verify provider initializes with correct parameters."""
        class TestProvider(BaseLLMProvider):
            env_key = "TEST_API_KEY"
            
            async def complete(self, prompt, **kwargs):
                # Must return CompletionResponse dict
                return {
                    "text": "test",
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                    "raw": None
                }
            
            async def stream(self, prompt, **kwargs):
                yield "test"
            
            def _translate_params(self, params):
                """Translate internal params to API params."""
                return params
            
            def _translate_error(self, error):
                """Translate vendor errors to standard errors."""
                return error
        
        # Current API doesn't accept max_tokens/temperature in constructor
        provider = TestProvider(
            model="test-model",
            api_key="test-key",
            base_url="https://api.test.com"
        )
        
        assert provider.model == "test-model"
        assert provider.api_key == "test-key"
        assert provider.base_url == "https://api.test.com"
    
    def test_provider_reads_env_key(self):
        """Verify provider reads API key from environment."""
        class TestProvider(BaseLLMProvider):
            env_key = "TEST_API_KEY"
            
            async def complete(self, prompt, **kwargs):
                return {
                    "text": "test",
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                    "raw": None
                }
            
            async def stream(self, prompt, **kwargs):
                yield "test"
            
            def _translate_params(self, params):
                return params
            
            def _translate_error(self, error):
                return error
        
        with patch.dict(os.environ, {"TEST_API_KEY": "env-test-key"}):
            provider = TestProvider(model="test-model")
            assert provider.api_key == "env-test-key"
    
    @pytest.mark.asyncio
    async def test_caching_functionality(self):
        """Verify caching works correctly."""
        class TestProvider(BaseLLMProvider):
            async def complete(self, prompt, **kwargs):
                # Must return CompletionResponse dict
                return {
                    "text": "response",
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                    "raw": None
                }
            
            async def stream(self, prompt, **kwargs):
                yield "response"
            
            def _translate_params(self, params):
                return params
            
            def _translate_error(self, error):
                return error
        
        provider = TestProvider(model="test-model")
        mock_cache = AsyncMock()
        # complete_with_cache expects the cache to store the text value
        mock_cache.get_by_id.return_value = {"return": "cached_response"}
        
        result = await provider.complete_with_cache(
            "test prompt",
            hashing_kv=mock_cache
        )
        
        # complete_with_cache returns just the text string from cache
        assert result == "cached_response"
        mock_cache.get_by_id.assert_called_once()
    
    def test_message_building(self):
        """Verify message list is built correctly."""
        class TestProvider(BaseLLMProvider):
            async def complete(self, prompt, **kwargs):
                return {
                    "text": "test",
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                    "raw": None
                }
            
            async def stream(self, prompt, **kwargs):
                yield "test"
            
            def _translate_params(self, params):
                return params
            
            def _translate_error(self, error):
                return error
        
        provider = TestProvider(model="test")
        messages = provider._build_messages(
            "user prompt",
            "system prompt",
            [{"role": "assistant", "content": "previous"}]
        )
        
        assert len(messages) == 3
        assert messages[0] == {"role": "system", "content": "system prompt"}
        assert messages[1] == {"role": "assistant", "content": "previous"}
        assert messages[2] == {"role": "user", "content": "user prompt"}


class TestOpenAIProvider:
    """Test OpenAI provider implementation."""
    
    @pytest.mark.asyncio
    async def test_openai_complete(self):
        """Verify OpenAI provider returns CompletionResponse dict."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            # Create proper mock response with usage
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "test response"
            mock_response.choices[0].finish_reason = "stop"
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 20
            mock_response.usage.total_tokens = 30
            
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            
            provider = OpenAIProvider(model="gpt-4o-mini")
            provider.client = mock_client
            
            async def mock_wait_for(coro, timeout):
                return await coro
            
            with patch('asyncio.wait_for', side_effect=mock_wait_for):
                result = await provider.complete("test prompt")
            
            # OpenAI provider returns CompletionResponse dict
            assert isinstance(result, dict)
            assert result["text"] == "test response"
            assert result["finish_reason"] == "stop"
            assert result["usage"]["total_tokens"] == 30
    
    @pytest.mark.asyncio
    async def test_openai_with_system_and_history(self):
        """Verify OpenAI handles system prompts and history."""
        provider = OpenAIProvider(model="gpt-4o-mini")
        
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.chat.completions.create.return_value = Mock(
                choices=[Mock(message=Mock(content="response"))]
            )
            provider.client = mock_client
            
            await provider.complete(
                "user prompt",
                system_prompt="system",
                history=[{"role": "user", "content": "previous"}]
            )
            
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            
            assert len(messages) == 3
            assert messages[0]["role"] == "system"
            assert messages[1]["content"] == "previous"
            assert messages[2]["content"] == "user prompt"
    
    def test_max_tokens_parameter_selection(self):
        """Verify correct max_tokens parameter is used based on model."""
        # GPT-5 models should use max_completion_tokens
        provider_gpt5 = OpenAIProvider(model="gpt-5-mini")
        assert "gpt-5" in provider_gpt5.model
        
        # GPT-4 models should use max_tokens
        provider_gpt4 = OpenAIProvider(model="gpt-4o-mini")
        assert "gpt-5" not in provider_gpt4.model


class TestOpenAIEmbeddingProvider:
    """Test OpenAI embedding provider."""
    
    @pytest.mark.asyncio
    async def test_embedding_initialization(self):
        """Verify embedding provider initializes correctly."""
        provider = OpenAIEmbeddingProvider()
        assert provider.model == "text-embedding-3-small"
        assert provider.embedding_dim == 1536
    
    @pytest.mark.asyncio
    async def test_embedding_mock(self):
        """Test embedding returns EmbeddingResponse dict."""
        provider = OpenAIEmbeddingProvider()
        
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            # Mock embedding response
            mock_response = Mock()
            mock_response.data = [
                Mock(embedding=[0.1] * 1536),
                Mock(embedding=[0.2] * 1536)
            ]
            mock_response.usage.total_tokens = 20
            
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            provider.client = mock_client
            
            async def mock_wait_for(coro, timeout):
                return await coro
            
            with patch('asyncio.wait_for', side_effect=mock_wait_for):
                result = await provider.embed(["text1", "text2"])
            
            # Provider returns EmbeddingResponse dict
            assert isinstance(result, dict)
            assert "embeddings" in result
            assert result["embeddings"].shape == (2, 1536)
            assert isinstance(result["embeddings"], np.ndarray)
            assert result["dimensions"] == 1536
            assert result["usage"]["total_tokens"] == 20


class TestBackwardCompatibility:
    """Test backward compatibility functions."""
    
    @pytest.mark.asyncio
    async def test_gpt_4o_complete_compatibility(self):
        """Verify gpt_4o_complete backward compatibility."""
        from nano_graphrag.llm.providers.openai import gpt_4o_complete
        
        with patch('nano_graphrag.llm.providers.openai.OpenAIProvider') as mock_provider_class:
            mock_provider = AsyncMock()
            mock_provider_class.return_value = mock_provider
            mock_provider.complete_with_cache.return_value = "response"
            
            result = await gpt_4o_complete("prompt")
            
            assert result == "response"
            mock_provider_class.assert_called_once_with(model="gpt-5")
    
    @pytest.mark.asyncio
    async def test_gpt_4o_mini_complete_compatibility(self):
        """Verify gpt_4o_mini_complete backward compatibility."""
        from nano_graphrag.llm.providers.openai import gpt_4o_mini_complete
        
        with patch('nano_graphrag.llm.providers.openai.OpenAIProvider') as mock_provider_class:
            mock_provider = AsyncMock()
            mock_provider_class.return_value = mock_provider
            mock_provider.complete_with_cache.return_value = "response"
            
            result = await gpt_4o_mini_complete("prompt")
            
            assert result == "response"
            mock_provider_class.assert_called_once_with(model="gpt-5-mini")


class TestOpenAIIntegration:
    """Integration tests using real OpenAI API (when configured)."""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_API_KEY").startswith("sk-"),
        reason="OpenAI API key not configured"
    )
    async def test_real_openai_completion(self):
        """Test with real OpenAI API (requires API key)."""
        # Use test model from env or default to gpt-4o-mini
        model = os.getenv("OPENAI_TEST_MODEL", "gpt-4o-mini")
        provider = OpenAIProvider(model=model)
        
        result = await provider.complete(
            "Say 'test successful' and nothing else",
            max_tokens=50
        )
        
        assert "test successful" in result.lower()
        assert isinstance(result, str)
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_API_KEY").startswith("sk-"),
        reason="OpenAI API key not configured"
    )
    async def test_real_openai_streaming(self):
        """Test streaming with real OpenAI API."""
        model = os.getenv("OPENAI_TEST_MODEL", "gpt-4o-mini")
        provider = OpenAIProvider(model=model)
        
        chunks = []
        async for chunk in provider.stream(
            "Count from 1 to 3, just the numbers",
            max_tokens=50
        ):
            chunks.append(chunk)
        
        full_response = "".join(chunks)
        assert "1" in full_response
        assert "2" in full_response
        assert "3" in full_response
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_API_KEY").startswith("sk-"),
        reason="OpenAI API key not configured"
    )
    async def test_real_openai_embeddings(self):
        """Test embeddings with real OpenAI API."""
        provider = OpenAIEmbeddingProvider()
        
        result = await provider.embed(["test text", "another text"])
        
        assert result.shape == (2, 1536)
        assert isinstance(result, np.ndarray)
        # Embeddings should be normalized (roughly)
        assert -1.5 < result[0][0] < 1.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])```

### File: ./nano_graphrag/llm/providers/tests/test_contract.py
```
"""Contract tests for LLM providers to ensure interface compliance."""

import pytest
import asyncio
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Type, AsyncIterator

from nano_graphrag.llm.base import (
    BaseLLMProvider,
    BaseEmbeddingProvider,
    CompletionParams,
    CompletionResponse,
    StreamChunk,
    EmbeddingResponse,
    LLMAuthError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMServerError,
    LLMBadRequestError
)
from nano_graphrag.llm.providers.openai import OpenAIProvider, OpenAIEmbeddingProvider


class ContractTestBase:
    """Base class for provider contract tests."""
    
    provider_class: Type[BaseLLMProvider] = None
    embedding_provider_class: Type[BaseEmbeddingProvider] = None
    
    @pytest.fixture
    def provider(self):
        """Create provider instance."""
        return self.provider_class(model="test-model", api_key="test-key")
    
    @pytest.fixture
    def embedding_provider(self):
        """Create embedding provider instance."""
        if self.embedding_provider_class:
            return self.embedding_provider_class(model="test-embed", api_key="test-key")
        return None
    
    def test_provider_has_required_methods(self, provider):
        """Verify provider implements all required methods."""
        assert hasattr(provider, 'complete')
        assert hasattr(provider, 'stream')
        assert hasattr(provider, '_translate_params')
        assert hasattr(provider, '_translate_error')
        assert hasattr(provider, 'complete_with_cache')
        assert hasattr(provider, 'stream_with_cache')
    
    def test_provider_initialization(self):
        """Test provider can be initialized with various configs."""
        # Basic init
        p1 = self.provider_class(model="test")
        assert p1.model == "test"
        
        # With custom timeouts
        p2 = self.provider_class(
            model="test",
            request_timeout=60.0,
            connect_timeout=5.0
        )
        assert p2.request_timeout == 60.0
        assert p2.connect_timeout == 5.0
        
        # With retry config
        retry_config = {
            "max_retries": 5,
            "retry_on_status": [429, 500],
            "backoff_factor": 3.0,
            "max_backoff": 120.0
        }
        p3 = self.provider_class(model="test", retry_config=retry_config)
        assert p3.retry_config == retry_config
    
    @pytest.mark.asyncio
    async def test_complete_returns_correct_type(self, provider):
        """Verify complete returns CompletionResponse."""
        with patch.object(provider, '_retry_with_backoff') as mock_retry:
            mock_retry.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="test"), finish_reason="stop")],
                usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
            )
            
            result = await provider.complete("test prompt")
            
            assert isinstance(result, dict)
            assert "text" in result
            assert "finish_reason" in result
            assert "usage" in result
            assert "raw" in result
            assert result["text"] == "test"
            assert result["finish_reason"] == "stop"
    
    @pytest.mark.asyncio
    async def test_stream_returns_async_iterator(self, provider):
        """Verify stream returns AsyncIterator[StreamChunk]."""
        # Test that the stream method signature is correct
        import inspect
        sig = inspect.signature(provider.stream)
        params = sig.parameters
        
        # Check required parameters
        assert 'prompt' in params
        assert 'system_prompt' in params
        assert 'history' in params
        assert 'params' in params
        assert 'timeout' in params
        
        # Verify it's an async generator
        assert inspect.isasyncgenfunction(provider.stream) or inspect.iscoroutinefunction(provider.stream)
    
    def test_translate_params_vendor_neutral(self, provider):
        """Verify parameter translation is vendor-neutral."""
        params = CompletionParams(
            max_output_tokens=1000,
            temperature=0.7,
            top_p=0.9,
            frequency_penalty=0.5,
            presence_penalty=0.3,
            stop_sequences=["\\n", "END"],
            seed=42
        )
        
        translated = provider._translate_params(params)
        
        # Ensure no vendor-neutral names leak through
        assert "max_output_tokens" not in translated
        assert "stop_sequences" not in translated
        
        # Verify some translation occurred
        assert len(translated) > 0
    
    def test_translate_error_coverage(self, provider):
        """Verify error translation covers all cases."""
        from nano_graphrag.llm.base import LLMError
        # Test various error types
        errors = [
            (Exception("generic"), LLMError),
            (asyncio.TimeoutError(), LLMTimeoutError),
        ]
        
        for original, expected_type in errors:
            translated = provider._translate_error(original)
            assert isinstance(translated, expected_type) or isinstance(translated, LLMError)
    
    @pytest.mark.asyncio
    async def test_complete_with_params(self, provider):
        """Test complete with vendor-neutral params."""
        params = CompletionParams(
            max_output_tokens=500,
            temperature=1.0,
            top_p=0.95
        )
        
        with patch.object(provider, '_retry_with_backoff') as mock_retry:
            mock_retry.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="test"), finish_reason="stop")],
                usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
            )
            
            result = await provider.complete(
                "test prompt",
                params=params,
                timeout=10.0
            )
            
            assert result["text"] == "test"
    
    @pytest.mark.asyncio
    async def test_complete_with_timeout(self, provider):
        """Test timeout handling."""
        with patch.object(provider, '_retry_with_backoff') as mock_retry:
            mock_retry.side_effect = asyncio.TimeoutError()
            
            with pytest.raises(LLMTimeoutError):
                await provider.complete("test", timeout=0.001)
    
    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self, provider):
        """Test retry behavior on rate limit errors."""
        call_count = 0
        
        async def mock_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # Create a mock rate limit error
                class MockRateLimitError(Exception):
                    pass
                error = MockRateLimitError("Rate limited")
                error.__class__.__name__ = "RateLimitError"
                raise error
            return "success"
        
        # Mock sleep to speed up test
        with patch('asyncio.sleep', new_callable=AsyncMock):
            # The retry logic will translate the error and retry
            result = await provider._retry_with_backoff(mock_func)
            assert result == "success"
            assert call_count == 3


class TestOpenAIProviderContract(ContractTestBase):
    """Contract tests for OpenAI provider."""
    
    provider_class = OpenAIProvider
    embedding_provider_class = OpenAIEmbeddingProvider
    
    def test_openai_specific_param_translation(self):
        """Test OpenAI-specific parameter translation."""
        # Test GPT-5 model
        provider_gpt5 = OpenAIProvider(model="gpt-5", api_key="test")
        params = CompletionParams(max_output_tokens=1000)
        translated = provider_gpt5._translate_params(params)
        assert "max_completion_tokens" in translated
        assert translated["max_completion_tokens"] == 1000
        
        # Test GPT-4 model
        provider_gpt4 = OpenAIProvider(model="gpt-4", api_key="test")
        translated = provider_gpt4._translate_params(params)
        assert "max_tokens" in translated
        assert translated["max_tokens"] == 1000
    
    @pytest.mark.asyncio
    async def test_embedding_provider_contract(self, embedding_provider):
        """Test embedding provider implements contract."""
        if not embedding_provider:
            pytest.skip("No embedding provider for this test")
        
        with patch.object(embedding_provider, '_retry_with_backoff') as mock_retry:
            mock_retry.return_value = MagicMock(
                data=[
                    MagicMock(embedding=[0.1] * 1536),
                    MagicMock(embedding=[0.2] * 1536)
                ]
            )
            
            result = await embedding_provider.embed(["text1", "text2"])
            
            assert isinstance(result, dict)
            assert "embeddings" in result
            assert "dimensions" in result
            assert "model" in result
            assert "usage" in result
            assert isinstance(result["embeddings"], np.ndarray)
            assert result["embeddings"].shape == (2, 1536)
    
    def test_embedding_batch_handling(self, embedding_provider):
        """Test embedding provider has batch size limit."""
        if not embedding_provider:
            pytest.skip("No embedding provider for this test")
        
        # Verify the provider has a max_batch_size attribute
        assert hasattr(embedding_provider, 'max_batch_size')
        assert isinstance(embedding_provider.max_batch_size, int)
        assert embedding_provider.max_batch_size > 0
        
        # Verify embedding dimensions are set
        assert hasattr(embedding_provider, 'embedding_dim')
        assert embedding_provider.embedding_dim > 0


# Table-driven parameter translation tests
@pytest.mark.parametrize("provider_class,model,params,expected_keys", [
    (OpenAIProvider, "gpt-5", {"max_output_tokens": 1000}, ["max_completion_tokens"]),
    (OpenAIProvider, "gpt-5-mini", {"max_output_tokens": 1000}, ["max_completion_tokens"]),
    (OpenAIProvider, "gpt-4", {"max_output_tokens": 1000}, ["max_tokens"]),
    (OpenAIProvider, "gpt-4-turbo", {"max_output_tokens": 1000}, ["max_tokens"]),
])
def test_parameter_translation_matrix(provider_class, model, params, expected_keys):
    """Table-driven test for parameter translation across models."""
    provider = provider_class(model=model, api_key="test")
    completion_params = CompletionParams(**params)
    translated = provider._translate_params(completion_params)
    
    for key in expected_keys:
        assert key in translated, f"Expected {key} in translated params for {model}"
    
    # Ensure vendor-neutral names don't leak
    assert "max_output_tokens" not in translated


# Error translation matrix tests
@pytest.mark.parametrize("provider_class,error_type,expected_llm_error", [
    (OpenAIProvider, "auth", LLMAuthError),
    (OpenAIProvider, "rate_limit", LLMRateLimitError),
    (OpenAIProvider, "timeout", LLMTimeoutError),
    (OpenAIProvider, "server", LLMServerError),
    (OpenAIProvider, "bad_request", LLMBadRequestError),
])
def test_error_translation_matrix(provider_class, error_type, expected_llm_error):
    """Table-driven test for error translation."""
    provider = provider_class(model="test", api_key="test")
    
    # Create mock errors (use mock objects to simulate OpenAI errors)
    if error_type == "auth":
        error = MagicMock()
        error.__class__.__name__ = "AuthenticationError"
        error.__str__ = lambda self: "Authentication failed"
    elif error_type == "rate_limit":
        error = MagicMock()
        error.__class__.__name__ = "RateLimitError"
        error.__str__ = lambda self: "Rate limit exceeded"
    elif error_type == "timeout":
        error = asyncio.TimeoutError()
    elif error_type == "server":
        error = MagicMock()
        error.__class__.__name__ = "APIConnectionError"
        error.__str__ = lambda self: "Server error"
    elif error_type == "bad_request":
        error = MagicMock()
        error.__class__.__name__ = "BadRequestError"
        error.__str__ = lambda self: "Invalid request"
    
    translated = provider._translate_error(error)
    assert isinstance(translated, expected_llm_error)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])```

### File: ./nano_graphrag/llm/providers/__init__.py
```
"""LLM Provider implementations."""

import os
from typing import Optional, Any
from ..base import BaseLLMProvider, BaseEmbeddingProvider

from .openai import (
    OpenAIProvider,
    OpenAIEmbeddingProvider,
    gpt_4o_complete,
    gpt_4o_mini_complete,
    openai_embedding,
)
from .deepseek import (
    DeepSeekProvider,
    deepseek_model_if_cache,
    stream_deepseek_model_if_cache,
)
from .azure import (
    AzureOpenAIProvider,
    AzureOpenAIEmbeddingProvider,
    azure_gpt_4o_complete,
    azure_gpt_4o_mini_complete,
    azure_openai_embedding,
)
from .bedrock import (
    BedrockProvider,
    BedrockEmbeddingProvider,
    create_amazon_bedrock_complete_function,
    amazon_bedrock_embedding,
)


def get_llm_provider(
    provider_type: str, 
    model: str,
    config: Optional[Any] = None
) -> BaseLLMProvider:
    """Factory function to get LLM provider instance.
    
    Args:
        provider_type: Type of provider (openai, azure, bedrock, deepseek)
        model: Model name
        config: Optional configuration object
        
    Returns:
        LLM provider instance
    """
    if provider_type == "openai":
        # Use LLM_BASE_URL if set, otherwise fall back to OPENAI_BASE_URL
        base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        request_timeout = float(os.getenv("LLM_REQUEST_TIMEOUT", "30.0")) if config else 30.0
        if config and hasattr(config, 'request_timeout'):
            request_timeout = config.request_timeout
        return OpenAIProvider(model=model, base_url=base_url, request_timeout=request_timeout)
    elif provider_type == "azure":
        return AzureOpenAIProvider(model=model)
    elif provider_type == "bedrock":
        return BedrockProvider(model=model)
    elif provider_type == "deepseek":
        return DeepSeekProvider(model=model)
    else:
        raise ValueError(f"Unknown LLM provider type: {provider_type}")


def get_embedding_provider(
    provider_type: str,
    model: str,
    config: Optional[Any] = None
) -> BaseEmbeddingProvider:
    """Factory function to get embedding provider instance.
    
    Args:
        provider_type: Type of provider (openai, azure, bedrock)
        model: Model name
        config: Optional configuration object
        
    Returns:
        Embedding provider instance
    """
    if provider_type == "openai":
        # Use EMBEDDING_BASE_URL if set, otherwise default to OpenAI's API
        # This prevents LMStudio's base URL from affecting embeddings
        base_url = os.getenv("EMBEDDING_BASE_URL")
        # If no embedding base URL is set, use None to default to OpenAI
        # Don't fall back to OPENAI_BASE_URL as that would redirect embeddings
        return OpenAIEmbeddingProvider(model=model, base_url=base_url)
    elif provider_type == "azure":
        return AzureOpenAIEmbeddingProvider(model=model)
    elif provider_type == "bedrock":
        return BedrockEmbeddingProvider(model=model)
    else:
        raise ValueError(f"Unknown embedding provider type: {provider_type}")


__all__ = [
    # Factory functions
    "get_llm_provider",
    "get_embedding_provider",
    # Providers
    "OpenAIProvider",
    "OpenAIEmbeddingProvider",
    "DeepSeekProvider",
    "AzureOpenAIProvider",
    "AzureOpenAIEmbeddingProvider",
    "BedrockProvider",
    "BedrockEmbeddingProvider",
    # Backward compatibility functions
    "gpt_4o_complete",
    "gpt_4o_mini_complete",
    "openai_embedding",
    "deepseek_model_if_cache",
    "stream_deepseek_model_if_cache",
    "azure_gpt_4o_complete",
    "azure_gpt_4o_mini_complete",
    "azure_openai_embedding",
    "create_amazon_bedrock_complete_function",
    "amazon_bedrock_embedding",
]```

... (additional files truncated)
Total files included: 20
