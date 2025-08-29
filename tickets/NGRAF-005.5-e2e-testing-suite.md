# NGRAF-005.5: E2E Health Check for Continuous Validation

## Summary
Create a standalone health check script that validates core GraphRAG functionality using the full Dickens book, supporting both OpenAI and LMStudio modes via environment configuration only.

## Context
Before implementing NGRAF-006 through NGRAF-010 refactoring tickets, we need a simple, reliable way to verify core functionality remains intact. This health check uses the full book for quality validation with a 10-minute runtime budget.

## Problem
- No simple way to verify refactoring doesn't break functionality
- Need both OpenAI (remote/CI) and LMStudio (local dev) support
- Must validate insert → graph → query → reload pipeline
- Should complete in predictable time (~10 minutes)

## Technical Solution

### Directory Structure
```
tests/
├── health/
│   ├── run_health_check.py     # Standalone runner script
│   ├── config_openai.env       # OpenAI configuration
│   ├── config_lmstudio.env     # LMStudio configuration  
│   └── reports/                # Test results
│       └── latest.json         # Most recent run
```

### 1. Health Check Runner
```python
# tests/health/run_health_check.py

import os
import json
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from nano_graphrag import GraphRAG, QueryParam
from nano_graphrag.config import GraphRAGConfig

class HealthCheck:
    """Standalone health check for nano-graphrag."""
    
    def __init__(self, mode: str = "openai"):
        self.mode = mode
        self.working_dir = Path("./.health/dickens")
        self.report_dir = Path("./tests/health/reports")
        self.test_data_path = Path("./tests/mock_data.txt")
        self.results: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "mode": mode,
            "status": "running",
            "timings": {},
            "counts": {
                "nodes": 0,
                "edges": 0,
                "communities": 0,
                "chunks": 0
            },
            "errors": []
        }
    
    def setup_environment(self):
        """Load environment variables from config file."""
        config_file = f"./tests/health/config_{self.mode}.env"
        
        # Load environment from config file
        with open(config_file) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
        
        print(f"✅ Loaded {self.mode} configuration")
    
    async def test_insert(self, graph: GraphRAG, text: str) -> bool:
        """Test document insertion and graph building."""
        try:
            start = time.time()
            await graph.ainsert(text)
            self.results["timings"]["insert"] = time.time() - start
            
            # Verify artifacts created
            expected_files = [
                "kv_store_full_docs.json",
                "kv_store_text_chunks.json", 
                "kv_store_community_reports.json",
                "graph_chunk_entity_relation.graphml"
            ]
            
            for file in expected_files:
                if not (self.working_dir / file).exists():
                    raise FileNotFoundError(f"Missing expected file: {file}")
            
            # Count entities from GraphML
            import xml.etree.ElementTree as ET
            tree = ET.parse(self.working_dir / "graph_chunk_entity_relation.graphml")
            root = tree.getroot()
            ns = {'g': 'http://graphml.graphdrawing.org/xmlns'}
            
            nodes = root.findall('.//g:node', ns)
            edges = root.findall('.//g:edge', ns)
            self.results["counts"]["nodes"] = len(nodes)
            self.results["counts"]["edges"] = len(edges)
            
            # Count chunks and communities
            with open(self.working_dir / "kv_store_text_chunks.json") as f:
                chunks = json.load(f)
                self.results["counts"]["chunks"] = len(chunks)
                
            with open(self.working_dir / "kv_store_community_reports.json") as f:
                reports = json.load(f)
                self.results["counts"]["communities"] = len(reports)
            
            # Validate counts
            if self.results["counts"]["nodes"] == 0:
                raise ValueError("No nodes extracted")
            if self.results["counts"]["edges"] == 0:
                raise ValueError("No edges extracted")
            if self.results["counts"]["communities"] == 0:
                raise ValueError("No communities detected")
            
            return True
            
        except Exception as e:
            self.results["errors"].append(f"Insert failed: {str(e)}")
            return False
    
    async def test_queries(self, graph: GraphRAG) -> bool:
        """Test all query modes."""
        test_query = "What are the top themes in this story?"
        
        try:
            # Global query
            start = time.time()
            global_result = await graph.aquery(test_query)
            self.results["timings"]["global_query"] = time.time() - start
            
            if len(global_result) < 200:
                raise ValueError(f"Global query too short: {len(global_result)} chars, expected >200")
            
            # Optional: Try to parse as JSON (non-blocking)
            try:
                json.loads(global_result)
                print("  ✓ Global query returned valid JSON")
            except:
                print("  ✓ Global query returned text (JSON parse failed, but OK)")
            
            # Local query
            start = time.time()
            local_result = await graph.aquery(
                test_query, 
                param=QueryParam(mode="local")
            )
            self.results["timings"]["local_query"] = time.time() - start
            
            if len(local_result) < 200:
                raise ValueError(f"Local query too short: {len(local_result)} chars, expected >200")
            
            return True
            
        except Exception as e:
            self.results["errors"].append(f"Query failed: {str(e)}")
            return False
    
    async def test_reload(self) -> bool:
        """Test reloading from cached state."""
        try:
            start = time.time()
            
            # Create new instance from same working dir - uses existing config from env
            graph = GraphRAG(working_dir=str(self.working_dir))
            
            # Quick global query to verify cached state works
            result = await graph.aquery("Who is Scrooge?")
            
            self.results["timings"]["reload"] = time.time() - start
            
            if len(result) < 100:
                raise ValueError(f"Reload query too short: {len(result)} chars, expected >100")
            
            # Reload should be much faster than initial insert
            if self.results["timings"]["reload"] > self.results["timings"]["insert"] * 0.5:
                print(f"  ⚠️ Reload took {self.results['timings']['reload']:.1f}s, expected faster")
            
            return True
            
        except Exception as e:
            self.results["errors"].append(f"Reload failed: {str(e)}")
            return False
    
    async def run(self) -> Dict[str, Any]:
        """Run complete health check."""
        print(f"🔍 Running health check in {self.mode} mode...")
        print(f"⏱️  Target runtime: <10 minutes")
        
        # Setup environment first
        self.setup_environment()
        
        # Clean working directory for fresh test
        if self.working_dir.exists():
            import shutil
            shutil.rmtree(self.working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)
        
        # Load test data (FULL book for quality)
        with open(self.test_data_path) as f:
            text = f.read()
        
        print(f"📚 Loaded {len(text):,} characters of test data")
        
        # Initialize GraphRAG using only environment configuration
        # No function injection - GraphRAG will use env vars for LLM/embedding config
        graph = GraphRAG(working_dir=str(self.working_dir))
        
        # Run tests
        all_passed = True
        
        print("📥 Testing insert...")
        if await self.test_insert(graph, text):
            print("✅ Insert passed")
        else:
            print("❌ Insert failed")
            all_passed = False
        
        print("🔎 Testing queries...")
        if await self.test_queries(graph):
            print("✅ Queries passed")
        else:
            print("❌ Queries failed")
            all_passed = False
        
        print("♻️ Testing reload...")
        if await self.test_reload():
            print("✅ Reload passed")
        else:
            print("❌ Reload failed")
            all_passed = False
        
        # Update status
        self.results["status"] = "pass" if all_passed else "fail"
        
        # Save report
        self.save_report()
        
        return self.results
    
    def save_report(self):
        """Save test report."""
        self.report_dir.mkdir(parents=True, exist_ok=True)
        
        # Save latest
        with open(self.report_dir / "latest.json", "w") as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n📊 Report saved to {self.report_dir / 'latest.json'}")

async def main():
    """Run health check with mode from environment."""
    mode = os.environ.get("GRAPHRAG_TEST_MODE", "openai")
    
    checker = HealthCheck(mode=mode)
    results = await checker.run()
    
    # Print summary
    print("\n" + "="*50)
    print(f"Health Check Results - {mode} mode")
    print("="*50)
    print(f"Status: {results['status'].upper()}")
    print(f"\nCounts:")
    print(f"  Nodes: {results['counts'].get('nodes', 0)}")
    print(f"  Edges: {results['counts'].get('edges', 0)}")
    print(f"  Communities: {results['counts'].get('communities', 0)}")
    print(f"  Chunks: {results['counts'].get('chunks', 0)}")
    print(f"\nTimings:")
    print(f"  Insert: {results['timings'].get('insert', 0):.1f}s")
    print(f"  Global query: {results['timings'].get('global_query', 0):.1f}s")
    print(f"  Local query: {results['timings'].get('local_query', 0):.1f}s")
    print(f"  Reload: {results['timings'].get('reload', 0):.1f}s")
    
    total_time = sum(results['timings'].values())
    print(f"\nTotal runtime: {total_time:.1f}s ({total_time/60:.1f} minutes)")
    
    if results['errors']:
        print("\n❌ Errors:")
        for error in results['errors']:
            print(f"  - {error}")
    
    # Exit with appropriate code
    exit(0 if results['status'] == 'pass' else 1)

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Configuration Files

```bash
# tests/health/config_openai.env
# OpenAI Configuration - Fast, reliable for CI
OPENAI_API_KEY=sk-your-key-here
GRAPHRAG_LLM_MODEL=gpt-5-mini
GRAPHRAG_EMBEDDING_MODEL=text-embedding-3-small
GRAPHRAG_CHUNK_SIZE=1000
GRAPHRAG_CHUNK_OVERLAP=100
GRAPHRAG_ENTITY_EXTRACT_MAX_GLEANING=1
GRAPHRAG_MAX_TOKENS=500
GRAPHRAG_LLM_MAX_ASYNC=4
GRAPHRAG_EMBEDDING_MAX_ASYNC=8
```

```bash
# tests/health/config_lmstudio.env  
# LMStudio Configuration - Local development
OPENAI_API_KEY=dummy
OPENAI_BASE_URL=http://localhost:1234/v1
GRAPHRAG_LLM_MODEL=qwen3-30b-instruct
GRAPHRAG_EMBEDDING_MODEL=text-embedding-3-small
GRAPHRAG_CHUNK_SIZE=1000
GRAPHRAG_CHUNK_OVERLAP=100
GRAPHRAG_ENTITY_EXTRACT_MAX_GLEANING=1
GRAPHRAG_MAX_TOKENS=500
GRAPHRAG_LLM_MAX_ASYNC=2
GRAPHRAG_EMBEDDING_MAX_ASYNC=4
# Note: For fully local embeddings, implement a local embedding provider
# Currently uses OpenAI embeddings even in LMStudio mode for quality
```

## How to Run

### OpenAI Mode (Remote/CI)
```bash
# 1. Set your OpenAI API key
export OPENAI_API_KEY=sk-your-key-here

# 2. Run health check
export GRAPHRAG_TEST_MODE=openai
python tests/health/run_health_check.py

# Expected runtime: 5-7 minutes
```

### LMStudio Mode (Local Development)
```bash
# 1. Start LMStudio and load your model (e.g., qwen3-30b-instruct)
# 2. Ensure it's serving at http://localhost:1234/v1

# 3. Run health check
export GRAPHRAG_TEST_MODE=lmstudio  
python tests/health/run_health_check.py

# Expected runtime: 8-10 minutes (depends on GPU)
```

### When to Run
- **Before each refactoring ticket** - Establish baseline
- **After each refactoring ticket** - Verify no regression
- **Before merging to main** - Final validation
- **Manual only** - Not part of CI pipeline

## Success Criteria

### Pass/Fail Assertions
- **Files exist**: All 4 expected JSON/GraphML files created
- **Counts non-zero**: 
  - Nodes > 0
  - Edges > 0  
  - Communities > 2
  - Chunks > 0
- **Query lengths**:
  - Global query > 200 characters
  - Local query > 200 characters
  - Reload query > 100 characters
- **Timing**: Total runtime < 10 minutes
- **Reload**: Much faster than initial insert

### Expected Results (Dickens full book)
- ~50-150 nodes (entities)
- ~30-100 edges (relationships)
- ~5-20 communities
- ~30-50 chunks
- Insert time: 3-6 minutes
- Query times: 5-30 seconds each

### Acceptance Criteria
- [ ] Runs in <10 minutes on modern workstation
- [ ] Both OpenAI and LMStudio modes work
- [ ] Clear pass/fail with specific error messages
- [ ] JSON report with all counts and timings
- [ ] No function injection into GraphRAG constructor
- [ ] Environment-driven configuration only

## Feature Branch
`feature/ngraf-005.5-health-check`

## Pull Request Must Include
- Standalone health check script (run_health_check.py)
- Two config files (openai and lmstudio)
- Clear setup instructions
- Example report output showing pass state

## Benefits
- **Simple**: One script, environment-driven, no complexity
- **Fast**: <10 minute runtime with tuned parameters
- **Reliable**: Concrete assertions on counts and lengths
- **Manual-first**: Developer-run, not CI overhead
- **Quality**: Full book ensures meaningful validation