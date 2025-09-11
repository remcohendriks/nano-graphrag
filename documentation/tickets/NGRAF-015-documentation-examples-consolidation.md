# NGRAF-015: Documentation and Examples Consolidation

## Overview
Comprehensive overhaul of documentation and examples to align with the new GraphRAGConfig pattern, remove all legacy patterns, create interactive tutorials, and establish a documentation testing framework.

## Current State
- README still shows legacy constructor patterns in Quick Start
- Many examples use deprecated `GraphRAG(kwargs)` pattern
- `CLAUDE.md` contains mixed legacy and new patterns
- Documentation scattered across README, docs/, and inline comments
- No unified documentation site or structure
- Examples not tested in CI leading to drift
- No clear migration path for users on old versions

## Proposed Implementation

### Phase 1: Documentation Structure Overhaul

#### Create `docs/` directory structure
```
docs/
├── getting-started/
│   ├── installation.md
│   ├── quick-start.md
│   ├── configuration.md
│   └── first-rag.md
├── guides/
│   ├── storage-backends.md
│   ├── llm-providers.md
│   ├── entity-extraction.md
│   ├── query-modes.md
│   └── performance-tuning.md
├── reference/
│   ├── config-api.md
│   ├── storage-api.md
│   ├── extraction-api.md
│   └── query-api.md
├── tutorials/
│   ├── 01-basic-rag.md
│   ├── 02-custom-storage.md
│   ├── 03-advanced-extraction.md
│   ├── 04-production-deployment.md
│   └── 05-performance-optimization.md
├── migration/
│   ├── from-0.x.md
│   ├── from-legacy-constructor.md
│   └── breaking-changes.md
└── api/
    └── (auto-generated from docstrings)
```

#### Update `README.md`
```markdown
# nano-graphrag

A simple, configurable, and extensible GraphRAG implementation.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)]()
[![Tests](https://github.com/gusye1234/nano-graphrag/actions/workflows/test.yml/badge.svg)]()

## Features

- 🚀 **Simple**: Get started with just a few lines of code
- 🔧 **Configurable**: Extensive configuration options via `GraphRAGConfig`
- 🔌 **Extensible**: Pluggable storage, LLM, and extraction strategies
- ⚡ **Fast**: Async operations and optimized storage backends
- 🏭 **Production-Ready**: Battle-tested with comprehensive test coverage

## Quick Start

```python
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig

# Simple initialization with defaults
config = GraphRAGConfig()
rag = GraphRAG(config)

# Insert documents
await rag.ainsert("Paris is the capital of France.")

# Query
result = await rag.aquery("What is the capital of France?")
print(result)
```

## Installation

```bash
# Basic installation
pip install nano-graphrag

# With specific storage backend
pip install nano-graphrag[qdrant]  # For Qdrant vector store
pip install nano-graphrag[neo4j]   # For Neo4j graph store

# All optional dependencies
pip install nano-graphrag[all]
```

## Configuration

nano-graphrag uses a configuration-first approach:

```python
from nano_graphrag.config import (
    GraphRAGConfig,
    LLMConfig,
    StorageConfig,
    ExtractionConfig
)

config = GraphRAGConfig(
    llm=LLMConfig(
        provider="openai",
        best_model="gpt-4",
        cheap_model="gpt-3.5-turbo"
    ),
    storage=StorageConfig(
        vector_backend="qdrant",
        graph_backend="neo4j"
    ),
    extraction=ExtractionConfig(
        strategy="prompt",  # or "dspy" for advanced extraction
        entity_types=["Person", "Organization", "Location"]
    )
)

rag = GraphRAG(config)
```

## Documentation

- [Getting Started Guide](docs/getting-started/quick-start.md)
- [Configuration Reference](docs/reference/config-api.md)
- [Storage Backends](docs/guides/storage-backends.md)
- [API Reference](https://nano-graphrag.readthedocs.io)

## Examples

See the [examples/](examples/) directory for:
- Basic usage patterns
- Storage backend configurations
- Custom extractors
- Production deployments

## Migration from Legacy Versions

If you're using the old constructor pattern, see our [Migration Guide](docs/migration/from-legacy-constructor.md).

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.
```

### Phase 2: Update All Examples

#### Create `examples/README.md`
```markdown
# nano-graphrag Examples

All examples use the modern `GraphRAGConfig` pattern introduced in v1.0.

## Basic Examples

- [basic_usage.py](basic_usage.py) - Simple GraphRAG usage
- [configuration.py](configuration.py) - Configuration options
- [async_operations.py](async_operations.py) - Async operations

## Storage Backends

- [storage_qdrant.py](storage_qdrant.py) - Qdrant vector storage
- [storage_neo4j.py](storage_neo4j.py) - Neo4j graph storage
- [storage_hnswlib.py](storage_hnswlib.py) - HNSW vector storage

## LLM Providers

- [llm_openai.py](llm_openai.py) - OpenAI models
- [llm_azure.py](llm_azure.py) - Azure OpenAI
- [llm_bedrock.py](llm_bedrock.py) - AWS Bedrock
- [llm_custom.py](llm_custom.py) - Custom LLM integration

## Advanced

- [extraction_strategies.py](extraction_strategies.py) - Entity extraction
- [custom_storage.py](custom_storage.py) - Custom storage backend
- [production_setup.py](production_setup.py) - Production configuration
- [performance_tuning.py](performance_tuning.py) - Performance optimization

## Running Examples

```bash
# Install dependencies
pip install nano-graphrag[all]

# Set environment variables
export OPENAI_API_KEY="your-key"

# Run example
python examples/basic_usage.py
```
```

#### Rewrite all examples to use GraphRAGConfig

Example template for each file:
```python
"""
Example: [Description]

This example demonstrates [what it does].

Requirements:
- [Required packages]
- [Required environment variables]
"""

import asyncio
import os
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, StorageConfig

# Load from environment or use defaults
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

async def main():
    """Main example function."""
    
    # Configure GraphRAG
    config = GraphRAGConfig(
        # Your configuration here
        storage=StorageConfig(
            vector_backend="nano",  # or "qdrant", "hnswlib"
            graph_backend="networkx"  # or "neo4j"
        )
    )
    
    # Initialize
    rag = GraphRAG(config)
    
    # Example usage
    documents = [
        "Your example documents here"
    ]
    
    # Insert documents
    for doc in documents:
        await rag.ainsert(doc)
    
    # Query
    questions = [
        "Your example questions"
    ]
    
    for question in questions:
        print(f"\nQuestion: {question}")
        answer = await rag.aquery(question, mode="local")
        print(f"Answer: {answer}")

if __name__ == "__main__":
    # Check requirements
    if not OPENAI_API_KEY:
        print("Please set OPENAI_API_KEY environment variable")
        exit(1)
    
    # Run example
    asyncio.run(main())
```

### Phase 3: Interactive Tutorials

#### Create `tutorials/interactive/setup.py`
```python
"""Interactive tutorial setup utilities."""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import json

class TutorialEnvironment:
    """Manages tutorial environment and progress."""
    
    def __init__(self, tutorial_name: str):
        self.tutorial_name = tutorial_name
        self.progress_file = Path.home() / ".nano_graphrag_tutorials" / f"{tutorial_name}.json"
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        self.progress = self.load_progress()
    
    def load_progress(self) -> Dict[str, Any]:
        """Load tutorial progress."""
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                return json.load(f)
        return {"completed_steps": [], "current_step": 0}
    
    def save_progress(self):
        """Save tutorial progress."""
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f)
    
    def mark_step_complete(self, step: int):
        """Mark a step as complete."""
        if step not in self.progress["completed_steps"]:
            self.progress["completed_steps"].append(step)
        self.progress["current_step"] = step + 1
        self.save_progress()
    
    def reset(self):
        """Reset tutorial progress."""
        self.progress = {"completed_steps": [], "current_step": 0}
        self.save_progress()

class InteractiveTutorial:
    """Base class for interactive tutorials."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.env = TutorialEnvironment(name)
        self.steps = []
    
    def add_step(self, title: str, content: str, exercise: Optional[str] = None):
        """Add a tutorial step."""
        self.steps.append({
            "title": title,
            "content": content,
            "exercise": exercise
        })
    
    def run(self):
        """Run the interactive tutorial."""
        print(f"\n{'='*60}")
        print(f"Tutorial: {self.name}")
        print(f"{'='*60}")
        print(f"\n{self.description}\n")
        
        # Resume or start
        start_step = self.env.progress["current_step"]
        if start_step > 0:
            resume = input(f"Resume from step {start_step}? (y/n): ")
            if resume.lower() != 'y':
                start_step = 0
                self.env.reset()
        
        # Run steps
        for i in range(start_step, len(self.steps)):
            self.run_step(i)
        
        print("\n🎉 Tutorial complete!")
    
    def run_step(self, step_num: int):
        """Run a single tutorial step."""
        step = self.steps[step_num]
        
        print(f"\n{'─'*60}")
        print(f"Step {step_num + 1}/{len(self.steps)}: {step['title']}")
        print(f"{'─'*60}\n")
        
        print(step['content'])
        
        if step['exercise']:
            print(f"\n📝 Exercise:\n{step['exercise']}\n")
            
            # Wait for user to complete
            while True:
                action = input("Enter 'done' when complete, 'skip' to skip, or 'quit' to exit: ")
                if action.lower() == 'done':
                    print("✅ Great job!")
                    self.env.mark_step_complete(step_num)
                    break
                elif action.lower() == 'skip':
                    print("⏭️ Skipping...")
                    break
                elif action.lower() == 'quit':
                    print("👋 See you later!")
                    sys.exit(0)
        else:
            input("\nPress Enter to continue...")
            self.env.mark_step_complete(step_num)
```

#### Create `tutorials/01_getting_started.py`
```python
#!/usr/bin/env python3
"""Interactive Tutorial: Getting Started with nano-graphrag"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from interactive.setup import InteractiveTutorial

tutorial = InteractiveTutorial(
    name="getting_started",
    description="Learn the basics of nano-graphrag in this interactive tutorial."
)

# Step 1: Installation
tutorial.add_step(
    title="Installation",
    content="""
First, let's install nano-graphrag. You have several options:

1. Basic installation:
   pip install nano-graphrag

2. With specific backends:
   pip install nano-graphrag[qdrant]  # For Qdrant vector store
   pip install nano-graphrag[neo4j]   # For Neo4j graph store

3. All optional dependencies:
   pip install nano-graphrag[all]
""",
    exercise="Install nano-graphrag with at least the basic package."
)

# Step 2: Configuration
tutorial.add_step(
    title="Understanding Configuration",
    content="""
nano-graphrag uses a configuration-first approach with GraphRAGConfig.

The configuration is organized into sections:
- LLMConfig: Language model settings
- StorageConfig: Storage backend settings  
- ExtractionConfig: Entity extraction settings
- ChunkingConfig: Document chunking settings

Here's a simple configuration:

```python
from nano_graphrag.config import GraphRAGConfig

config = GraphRAGConfig()  # Uses all defaults
```

And here's a more detailed one:

```python
from nano_graphrag.config import (
    GraphRAGConfig,
    LLMConfig,
    StorageConfig
)

config = GraphRAGConfig(
    llm=LLMConfig(
        provider="openai",
        best_model="gpt-4"
    ),
    storage=StorageConfig(
        vector_backend="hnswlib"
    )
)
```
""",
    exercise="""
Create a Python file called 'my_config.py' with:
1. Import GraphRAGConfig
2. Create a config with custom working_dir
3. Print the config

Run it to verify it works.
"""
)

# Step 3: First RAG
tutorial.add_step(
    title="Your First GraphRAG",
    content="""
Now let's create your first GraphRAG application!

```python
import asyncio
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig

async def main():
    # Create configuration
    config = GraphRAGConfig()
    
    # Initialize GraphRAG
    rag = GraphRAG(config)
    
    # Insert some data
    await rag.ainsert("Paris is the capital of France.")
    await rag.ainsert("London is the capital of the United Kingdom.")
    
    # Query the data
    result = await rag.aquery("What is the capital of France?")
    print(f"Answer: {result}")

if __name__ == "__main__":
    asyncio.run(main())
```

Key points:
- GraphRAG is async by default (use ainsert, aquery)
- Configuration is passed to GraphRAG constructor
- Documents are automatically processed into knowledge graph
""",
    exercise="""
Create 'first_rag.py' with the code above.
Add one more country-capital pair.
Add a query asking about that country.
Run it and verify you get correct answers.
"""
)

# Step 4: Query Modes
tutorial.add_step(
    title="Understanding Query Modes",
    content="""
nano-graphrag supports three query modes:

1. **Local Query** (default):
   - Searches within specific graph communities
   - Best for detailed, specific questions
   - Example: "What projects did John work on?"

2. **Global Query**:
   - Searches across all community reports
   - Best for high-level, thematic questions
   - Example: "What are the main themes in the documents?"

3. **Naive Query**:
   - Simple vector similarity search
   - No graph structure utilization
   - Example: Quick keyword matching

Usage:
```python
# Local query (default)
answer = await rag.aquery("Specific question", mode="local")

# Global query
answer = await rag.aquery("Broad question", mode="global")

# Naive query
answer = await rag.aquery("Keyword search", mode="naive")
```
""",
    exercise="""
Modify your first_rag.py to:
1. Add more related documents (5-10 sentences)
2. Try all three query modes with the same question
3. Compare the results
"""
)

# Step 5: Next Steps
tutorial.add_step(
    title="Next Steps",
    content="""
Congratulations! You've learned the basics of nano-graphrag.

Here's what to explore next:

1. **Storage Backends**:
   - Try different vector stores (Qdrant, HNSW)
   - Experiment with Neo4j for graph storage

2. **Entity Extraction**:
   - Customize entity types
   - Try DSPy-based extraction for better results

3. **Production Setup**:
   - Configure for your LLM provider
   - Set up persistent storage
   - Optimize performance settings

Resources:
- Examples: examples/ directory
- Full docs: docs/ directory
- API reference: docs/api/

Happy building! 🚀
"""
)

if __name__ == "__main__":
    tutorial.run()
```

### Phase 4: Documentation Testing Framework

#### Create `tests/test_documentation.py`
```python
"""Test documentation code examples and ensure they work."""

import pytest
import ast
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import asyncio

class DocStringExtractor(ast.NodeVisitor):
    """Extract code examples from docstrings."""
    
    def __init__(self):
        self.examples = []
    
    def visit_FunctionDef(self, node):
        self._extract_from_docstring(node)
        self.generic_visit(node)
    
    def visit_ClassDef(self, node):
        self._extract_from_docstring(node)
        self.generic_visit(node)
    
    def _extract_from_docstring(self, node):
        docstring = ast.get_docstring(node)
        if docstring:
            # Extract code blocks from docstring
            code_blocks = re.findall(
                r'```python\n(.*?)```',
                docstring,
                re.DOTALL
            )
            for code in code_blocks:
                self.examples.append({
                    'name': node.name,
                    'code': code,
                    'source': f"{node.lineno}"
                })

class TestDocumentation:
    """Test all documentation examples."""
    
    @pytest.fixture
    def docs_dir(self):
        """Get documentation directory."""
        return Path(__file__).parent.parent / "docs"
    
    @pytest.fixture
    def examples_dir(self):
        """Get examples directory."""
        return Path(__file__).parent.parent / "examples"
    
    def extract_code_from_markdown(self, md_file: Path) -> list:
        """Extract Python code blocks from markdown."""
        content = md_file.read_text()
        
        # Find all python code blocks
        pattern = r'```python\n(.*?)```'
        code_blocks = re.findall(pattern, content, re.DOTALL)
        
        return [
            {
                'file': str(md_file),
                'code': code,
                'line': content[:content.find(code)].count('\n')
            }
            for code in code_blocks
        ]
    
    def test_readme_examples(self):
        """Test code examples in README."""
        readme = Path(__file__).parent.parent / "README.md"
        
        if not readme.exists():
            pytest.skip("README.md not found")
        
        code_blocks = self.extract_code_from_markdown(readme)
        
        for block in code_blocks:
            # Skip import-only blocks
            if block['code'].strip().startswith('pip install'):
                continue
            
            # Test that code is valid Python
            try:
                ast.parse(block['code'])
            except SyntaxError as e:
                pytest.fail(
                    f"Invalid Python in README.md line {block['line']}: {e}"
                )
    
    def test_docs_examples(self, docs_dir):
        """Test code examples in documentation."""
        if not docs_dir.exists():
            pytest.skip("docs/ directory not found")
        
        # Find all markdown files
        md_files = list(docs_dir.rglob("*.md"))
        
        for md_file in md_files:
            code_blocks = self.extract_code_from_markdown(md_file)
            
            for block in code_blocks:
                # Skip shell commands
                if block['code'].strip().startswith(('$', '#', 'pip', 'git')):
                    continue
                
                # Test Python syntax
                try:
                    ast.parse(block['code'])
                except SyntaxError as e:
                    pytest.fail(
                        f"Invalid Python in {md_file} line {block['line']}: {e}"
                    )
    
    def test_examples_run(self, examples_dir):
        """Test that example files can be imported."""
        if not examples_dir.exists():
            pytest.skip("examples/ directory not found")
        
        # Get all Python files
        py_files = list(examples_dir.glob("*.py"))
        
        for py_file in py_files:
            # Skip files that require external services
            skip_patterns = ['neo4j', 'qdrant', 'milvus']
            if any(pattern in py_file.name for pattern in skip_patterns):
                continue
            
            # Try to parse the file
            try:
                with open(py_file) as f:
                    ast.parse(f.read())
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {py_file}: {e}")
    
    def test_no_legacy_patterns(self, examples_dir, docs_dir):
        """Ensure no legacy patterns in documentation."""
        legacy_patterns = [
            r'GraphRAG\([^)]*vector_db_storage_cls=',
            r'GraphRAG\([^)]*graph_storage_cls=',
            r'GraphRAG\([^)]*addon_params=',
            r'GraphRAG\([^)]*best_model_func=',
            r'GraphRAG\([^)]*cheap_model_func='
        ]
        
        # Check examples
        if examples_dir.exists():
            for py_file in examples_dir.glob("*.py"):
                content = py_file.read_text()
                for pattern in legacy_patterns:
                    if re.search(pattern, content):
                        pytest.fail(
                            f"Legacy pattern found in {py_file}: {pattern}"
                        )
        
        # Check docs
        if docs_dir.exists():
            for md_file in docs_dir.rglob("*.md"):
                content = md_file.read_text()
                for pattern in legacy_patterns:
                    if re.search(pattern, content):
                        pytest.fail(
                            f"Legacy pattern found in {md_file}: {pattern}"
                        )
    
    @pytest.mark.asyncio
    async def test_config_examples(self):
        """Test configuration examples work."""
        from nano_graphrag.config import GraphRAGConfig, StorageConfig
        
        # Test default config
        config = GraphRAGConfig()
        assert config is not None
        
        # Test with storage config
        config = GraphRAGConfig(
            storage=StorageConfig(
                vector_backend="nano",
                graph_backend="networkx"
            )
        )
        assert config.storage.vector_backend == "nano"
        
        # Test config serialization
        config_dict = config.to_dict()
        assert isinstance(config_dict, dict)
        
        # Test from_env
        import os
        os.environ["GRAPHRAG_WORKING_DIR"] = "/tmp/test"
        config = GraphRAGConfig.from_env()
        assert config.working_dir == "/tmp/test"
```

### Phase 5: Migration Documentation

#### Create `docs/migration/from-legacy-constructor.md`
```markdown
# Migration Guide: From Legacy Constructor to GraphRAGConfig

This guide helps you migrate from the old constructor-based initialization to the new configuration-based approach.

## Overview of Changes

The legacy constructor pattern with keyword arguments has been replaced with a configuration-first approach using `GraphRAGConfig`.

## Migration Examples

### Basic Migration

**Old Way:**
```python
from nano_graphrag import GraphRAG

rag = GraphRAG(
    working_dir="./cache",
    enable_local=True,
    enable_global=False
)
```

**New Way:**
```python
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig

config = GraphRAGConfig(
    working_dir="./cache",
    enable_local_query=True,
    enable_global_query=False
)
rag = GraphRAG(config)
```

### Storage Configuration

**Old Way:**
```python
from nano_graphrag import GraphRAG
from nano_graphrag._storage import HNSWVectorStorage

rag = GraphRAG(
    vector_db_storage_cls=HNSWVectorStorage,
    graph_storage_cls=NetworkXStorage,
    vector_db_storage_cls_kwargs={"max_elements": 100000}
)
```

**New Way:**
```python
from nano_graphrag.config import GraphRAGConfig, StorageConfig

config = GraphRAGConfig(
    storage=StorageConfig(
        vector_backend="hnswlib",
        graph_backend="networkx",
        vector_db_storage_cls_kwargs={"max_elements": 100000}
    )
)
rag = GraphRAG(config)
```

### LLM Configuration

**Old Way:**
```python
async def my_llm_func(prompt, **kwargs):
    # Custom LLM implementation
    return response

rag = GraphRAG(
    best_model_func=my_llm_func,
    cheap_model_func=my_llm_func,
    best_model_max_token_size=8000
)
```

**New Way:**
```python
from nano_graphrag.config import GraphRAGConfig, LLMConfig

config = GraphRAGConfig(
    llm=LLMConfig(
        best_model_func=my_llm_func,
        cheap_model_func=my_llm_func,
        best_model_max_token_size=8000
    )
)
rag = GraphRAG(config)
```

### Neo4j Configuration

**Old Way:**
```python
from nano_graphrag._storage import Neo4jStorage

rag = GraphRAG(
    graph_storage_cls=Neo4jStorage,
    addon_params={
        "neo4j_url": "neo4j://localhost:7687",
        "neo4j_auth": ("neo4j", "password")
    }
)
```

**New Way:**
```python
from nano_graphrag.config import GraphRAGConfig, StorageConfig

config = GraphRAGConfig(
    storage=StorageConfig(
        graph_backend="neo4j",
        neo4j_url="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="password"
    )
)
rag = GraphRAG(config)
```

## Complete Migration Mapping

| Old Parameter | New Configuration Path | Notes |
|--------------|------------------------|-------|
| `working_dir` | `config.working_dir` | Direct mapping |
| `enable_local` | `config.enable_local_query` | Renamed |
| `enable_global` | `config.enable_global_query` | Renamed |
| `vector_db_storage_cls` | `config.storage.vector_backend` | Use string name |
| `graph_storage_cls` | `config.storage.graph_backend` | Use string name |
| `best_model_func` | `config.llm.best_model_func` | Under LLM config |
| `cheap_model_func` | `config.llm.cheap_model_func` | Under LLM config |
| `embedding_func` | `config.embedding.func` | Under embedding config |
| `addon_params` | Various config fields | Split into specific fields |
| `chunk_size` | `config.chunking.chunk_size` | Under chunking config |
| `chunk_overlap` | `config.chunking.chunk_overlap` | Under chunking config |

## Environment Variables

The new configuration supports environment variables:

```bash
export GRAPHRAG_WORKING_DIR=/path/to/cache
export STORAGE_VECTOR_BACKEND=qdrant
export STORAGE_GRAPH_BACKEND=neo4j
export NEO4J_URL=neo4j://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
```

Then load in Python:
```python
config = GraphRAGConfig.from_env()
rag = GraphRAG(config)
```

## Backward Compatibility

The old constructor is deprecated and will be removed in v2.0. A deprecation warning is shown when using the old pattern.

## Need Help?

- See [Configuration Reference](../reference/config-api.md) for all options
- Check [Examples](../../examples/) for working code
- Open an issue if you encounter problems
```

## Definition of Done

- [ ] Documentation structure created:
  - [ ] All directories and placeholder files
  - [ ] README.md fully updated to GraphRAGConfig
  - [ ] CLAUDE.md updated with current patterns
- [ ] All examples updated:
  - [ ] No legacy constructor patterns
  - [ ] All use GraphRAGConfig
  - [ ] Examples README with clear instructions
  - [ ] Each example is runnable
- [ ] Interactive tutorials:
  - [ ] Tutorial framework created
  - [ ] At least 3 interactive tutorials
  - [ ] Progress tracking system
  - [ ] Exercise validation
- [ ] Documentation testing:
  - [ ] Code extraction from markdown
  - [ ] Syntax validation for all examples
  - [ ] No legacy patterns check
  - [ ] CI integration for doc tests
- [ ] Migration guides:
  - [ ] Complete mapping table
  - [ ] Multiple migration examples
  - [ ] Environment variable guide
  - [ ] Breaking changes documented
- [ ] API documentation:
  - [ ] Auto-generation setup (Sphinx/MkDocs)
  - [ ] All public APIs documented
  - [ ] Docstring examples tested

## Feature Branch
`feature/ngraf-015-docs-consolidation`

## Pull Request Requirements
- All documentation examples pass syntax check
- No legacy patterns found in any docs/examples
- Interactive tutorials tested by team member
- Migration guide reviewed by user who used old version
- CI passes all documentation tests

## Technical Considerations
- Use MkDocs or Sphinx for documentation site
- Consider versioned documentation for future
- Ensure examples work offline (mock LLM calls)
- Add example output/screenshots where helpful
- Consider video tutorials for complex topics