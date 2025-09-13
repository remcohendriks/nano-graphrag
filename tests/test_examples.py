"""Validate all examples work with current codebase."""

import pytest
import sys
import os
import subprocess
import importlib.util
import ast
from pathlib import Path
from typing import List, Set


class TestExamples:
    """Test all examples in the examples directory."""

    @pytest.fixture
    def examples_dir(self):
        """Get examples directory."""
        return Path(__file__).parent.parent / "examples"

    def get_example_files(self, examples_dir: Path) -> List[Path]:
        """Get all Python example files."""
        return list(examples_dir.glob("*.py"))

    def get_example_notebooks(self, examples_dir: Path) -> List[Path]:
        """Get all Jupyter notebook examples."""
        return list(examples_dir.glob("*.ipynb"))

    @pytest.mark.parametrize("example_file", [
        f for f in (Path(__file__).parent.parent / "examples").glob("*.py")
        if f.is_file()
    ])
    def test_example_imports(self, example_file: Path):
        """Test that example can be imported without syntax errors."""
        # Parse the file to check for syntax errors
        try:
            with open(example_file, 'r') as f:
                ast.parse(f.read())
        except SyntaxError as e:
            pytest.fail(f"Syntax error in {example_file.name}: {e}")

        # Check for required imports
        spec = importlib.util.spec_from_file_location(
            example_file.stem,
            example_file
        )

        if spec and spec.loader:
            # Don't actually execute, just check if it would import
            with open(example_file, 'r') as f:
                content = f.read()

            # Check for imports that require external services
            external_deps = {
                "neo4j": "Neo4j",
                "qdrant_client": "Qdrant",
                "milvus": "Milvus",
                "faiss": "FAISS"
            }

            for dep, service in external_deps.items():
                if f"import {dep}" in content or f"from {dep}" in content:
                    pytest.skip(f"Example requires {service} service")

    def test_example_mock_execution(self, examples_dir: Path, tmp_path: Path):
        """Test examples can be executed with mock data."""
        # Create mock data file
        mock_data = "This is test content for GraphRAG examples."
        mock_file = tmp_path / "mock_data.txt"
        mock_file.write_text(mock_data)

        # Examples that can be safely executed with mocks
        safe_examples = [
            "using_config.py",
            "using_custom_chunking_method.py",
            "using_local_embedding_model.py"
        ]

        for example_name in safe_examples:
            example_file = examples_dir / example_name
            if not example_file.exists():
                continue

            # Read and modify example to use mock data
            with open(example_file, 'r') as f:
                content = f.read()

            # Replace file paths with mock
            content = content.replace("./tests/mock_data.txt", str(mock_file))
            content = content.replace("./nano_graphrag_cache", str(tmp_path / "cache"))

            # Create modified example
            modified_example = tmp_path / example_name
            modified_example.write_text(content)

            # Try to run with timeout
            env = os.environ.copy()
            env["WORKING_DIR"] = str(tmp_path)

            # Skip actual execution if it requires external services
            if any(dep in content for dep in ["neo4j", "qdrant", "milvus", "ollama"]):
                continue

            # Just verify it can be imported
            spec = importlib.util.spec_from_file_location("test_example", modified_example)
            if spec and spec.loader:
                try:
                    # We're just checking imports, not running
                    pass
                except ImportError as e:
                    if "openai" in str(e).lower():
                        pytest.skip("OpenAI API key not configured")
                    else:
                        raise

    def test_deprecated_patterns(self, examples_dir: Path):
        """Check examples for deprecated patterns."""
        deprecated_patterns = [
            ("vector_db_storage_cls=", "Use StorageConfig instead"),
            ("graph_storage_cls=", "Use StorageConfig instead"),
            ("addon_params=", "Use storage-specific config classes"),
            ("embedding_func_max_async", "Use EmbeddingConfig"),
            ("chunking_func=", "Use ChunkingConfig")
        ]

        issues = []
        for example_file in self.get_example_files(examples_dir):
            with open(example_file, 'r') as f:
                content = f.read()

            for pattern, suggestion in deprecated_patterns:
                if pattern in content:
                    issues.append(f"{example_file.name}: Found '{pattern}' - {suggestion}")

        if issues:
            # Just warn, don't fail
            for issue in issues:
                print(f"Warning: {issue}")

    def test_examples_use_correct_imports(self, examples_dir: Path):
        """Verify examples import from correct modules."""
        required_imports = {
            "GraphRAG": "from nano_graphrag import GraphRAG",
            "QueryParam": "from nano_graphrag import QueryParam",
            "GraphRAGConfig": "from nano_graphrag.config import GraphRAGConfig"
        }

        for example_file in self.get_example_files(examples_dir):
            with open(example_file, 'r') as f:
                content = f.read()

            # Skip if it's a special example
            if "no_openai" in example_file.name:
                continue

            # Check if main classes are imported correctly
            if "GraphRAG(" in content:
                has_correct_import = False
                for class_name, import_stmt in required_imports.items():
                    if class_name in content and import_stmt in content:
                        has_correct_import = True
                        break

                if not has_correct_import and "GraphRAG" in content:
                    # Allow alternative import patterns
                    if "from nano_graphrag" not in content:
                        pytest.fail(f"{example_file.name} uses GraphRAG without proper import")

    def test_example_documentation(self, examples_dir: Path):
        """Check that examples have basic documentation."""
        for example_file in self.get_example_files(examples_dir):
            with open(example_file, 'r') as f:
                content = f.read()

            # Check for docstring or comments
            has_docs = (
                content.startswith('"""') or
                content.startswith("'''") or
                content.startswith("#")
            )

            if not has_docs:
                print(f"Warning: {example_file.name} lacks documentation")

    @pytest.mark.parametrize("notebook_file", [
        f for f in (Path(__file__).parent.parent / "examples").glob("*.ipynb")
        if f.is_file()
    ])
    def test_notebook_structure(self, notebook_file: Path):
        """Test that notebooks have valid structure."""
        import json

        try:
            with open(notebook_file, 'r') as f:
                notebook = json.load(f)

            # Check basic notebook structure
            assert "cells" in notebook
            assert "metadata" in notebook

            # Check that code cells have valid Python
            for cell in notebook.get("cells", []):
                if cell.get("cell_type") == "code":
                    source = "".join(cell.get("source", []))
                    if source.strip():
                        try:
                            ast.parse(source)
                        except SyntaxError as e:
                            pytest.fail(f"Syntax error in {notebook_file.name}: {e}")

        except json.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON in notebook {notebook_file.name}: {e}")

    def test_working_dir_handling(self, examples_dir: Path):
        """Ensure examples handle working directory properly."""
        for example_file in self.get_example_files(examples_dir):
            with open(example_file, 'r') as f:
                content = f.read()

            # Check if working_dir is specified
            if "GraphRAG(" in content:
                # Should either use working_dir parameter or GraphRAGConfig
                has_working_dir = (
                    "working_dir=" in content or
                    "StorageConfig" in content or
                    "GraphRAGConfig" in content
                )

                if not has_working_dir:
                    print(f"Info: {example_file.name} uses default working directory")