# Storage Backend Testing Guide

## Overview

This guide explains how to test storage backends in nano-graphrag using the unified testing framework introduced in NGRAF-013.

## Architecture

The testing framework consists of:

1. **Base Test Suites** - Abstract test classes that define contracts all storage implementations must fulfill
2. **Contract Classes** - Define capabilities and limitations of each storage backend
3. **Integration Tests** - Test external services like Neo4j and Qdrant when available
4. **Example Validation** - Ensure all examples work with the current codebase

## Adding a New Storage Backend

### Step 1: Implement the Storage Interface

Your storage class must inherit from the appropriate base class:
- `BaseVectorStorage` for vector databases
- `BaseGraphStorage` for graph databases
- `BaseKVStorage` for key-value stores

### Step 2: Create Contract Tests

Create a test file that inherits from the appropriate base test suite:

```python
# tests/storage/test_mystorage_contract.py
import pytest
from tests.storage.base import BaseVectorStorageTestSuite, VectorStorageContract
from my_module import MyVectorStorage

class TestMyStorageContract(BaseVectorStorageTestSuite):
    @pytest.fixture
    async def storage(self, temp_storage_dir):
        """Provide storage instance for testing."""
        config = {
            "working_dir": str(temp_storage_dir),
            # Add your config here
        }
        return MyVectorStorage(
            namespace="test",
            global_config=config
        )

    @pytest.fixture
    def contract(self):
        """Define storage capabilities."""
        return VectorStorageContract(
            supports_metadata=True,
            supports_filtering=False,
            supports_batch_upsert=True,
            # Define capabilities
        )
```

### Step 3: Run Contract Tests

```bash
# Run your specific contract tests
pytest tests/storage/test_mystorage_contract.py -v

# Run all storage tests
python tests/storage/run_tests.py
```

## Contract Compliance Checklist

### Vector Storage

- [ ] Implements `upsert()` for adding/updating vectors
- [ ] Implements `query()` for similarity search
- [ ] Returns results with `content` and distance/score fields
- [ ] Handles metadata if `supports_metadata=True`
- [ ] Supports batch operations if `supports_batch_upsert=True`
- [ ] Handles concurrent operations safely
- [ ] Persists data if `supports_persistence=True`

### Graph Storage

- [ ] Implements node CRUD operations
- [ ] Implements edge CRUD operations
- [ ] Supports batch operations for nodes and edges
- [ ] Calculates node/edge degrees
- [ ] Implements clustering if `supports_clustering=True`
- [ ] Handles concurrent modifications safely
- [ ] Uses consistent namespace handling

### KV Storage

- [ ] Implements `get_by_id()` and `get_by_ids()`
- [ ] Implements `upsert()` for batch updates
- [ ] Implements `filter_keys()` to find non-existent keys
- [ ] Implements `all_keys()` to list all keys
- [ ] Implements `drop()` to clear all data
- [ ] Handles persistence callbacks if supported
- [ ] Thread-safe for concurrent access

## Running Tests

### Quick Test Commands

```bash
# Run all unit tests (excludes integration tests)
pytest tests/ -v

# Run all contract tests
pytest tests/storage/ -k contract -v

# Run specific storage backend tests
pytest tests/storage/test_neo4j_basic.py -v
pytest tests/storage/test_qdrant_storage.py -v

# Run integration tests (requires services to be running)
RUN_NEO4J_TESTS=1 pytest tests/storage/test_neo4j_basic.py::test_neo4j_connection -v
RUN_QDRANT_TESTS=1 pytest tests/storage/test_qdrant_storage.py::TestQdrantIntegration -v

# Run both Neo4j and Qdrant integration tests
RUN_NEO4J_TESTS=1 RUN_QDRANT_TESTS=1 pytest tests/storage/ -k "integration or test_neo4j_connection" -v

# Run OpenAI integration tests (requires valid API key in .env)
pytest nano_graphrag/llm/providers/tests/test_openai_provider.py::TestOpenAIIntegration -v
```

### Environment Variables for Integration Tests

Integration tests are disabled by default and must be explicitly enabled:

```bash
# Enable Neo4j integration tests
export RUN_NEO4J_TESTS=1

# Enable Qdrant integration tests
export RUN_QDRANT_TESTS=1

# OpenAI API configuration (in .env file)
OPENAI_API_KEY=sk-your-actual-api-key
OPENAI_TEST_MODEL=gpt-5-mini  # Optional, defaults to gpt-5-mini
```

### Neo4j Configuration

For Neo4j tests to work:
1. Neo4j must be running on `localhost:7687`
2. Authentication: username `neo4j`, password `your-secure-password-change-me`
3. Tests use `bolt://` protocol with `neo4j_encrypted: False` for local testing

### Qdrant Configuration

For Qdrant tests to work:
1. Qdrant must be running on `localhost:6333`
2. No authentication required for local testing

## Test Organization

```
tests/
├── conftest.py                 # Global fixtures
├── storage/
│   ├── base/                   # Base test suites
│   │   ├── __init__.py
│   │   ├── vector_suite.py     # Vector storage tests
│   │   ├── graph_suite.py      # Graph storage tests
│   │   ├── kv_suite.py         # KV storage tests
│   │   └── fixtures.py         # Shared test data
│   ├── integration/            # External service tests
│   │   ├── test_neo4j_integration.py
│   │   └── test_qdrant_integration.py
│   ├── test_*_contract.py     # Contract tests for each backend
│   └── run_tests.py           # Simple test runner
└── test_examples.py           # Example validation
```

## Writing Deterministic Tests

Use the deterministic embedding function for reproducible tests:

```python
from tests.storage.base.fixtures import deterministic_embedding_func

# Generates same embedding for same text every time
embedding = await deterministic_embedding_func(["test text"])
```

## Skipping Tests

Tests automatically skip when dependencies are missing:

```python
@pytest.mark.skipif(
    not os.environ.get("NEO4J_URL"),
    reason="Neo4j not configured"
)
def test_neo4j_specific_feature():
    pass
```

## Common Issues and Solutions

### Issue: Import errors in tests
**Solution**: Ensure all dependencies are installed or tests will skip automatically

### Issue: Tests fail with external services
**Solution**: Check environment variables and service availability

### Issue: Flaky concurrent tests
**Solution**: Use deterministic fixtures and proper async handling

### Issue: Storage not cleaning up
**Solution**: Use temp_storage_dir fixture for automatic cleanup

## Best Practices

1. **Use Base Test Suites** - Don't duplicate test logic
2. **Define Accurate Contracts** - Be honest about capabilities
3. **Test Edge Cases** - Empty storage, special characters, concurrency
4. **Clean Up Resources** - Use fixtures for automatic cleanup
5. **Document Limitations** - Note in contract what's not supported