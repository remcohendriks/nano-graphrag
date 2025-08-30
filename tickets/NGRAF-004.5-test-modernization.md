# NGRAF-004.5: Test Suite Modernization and Fixes

## Summary
Update and fix the existing test suite to work with the refactored codebase, ensuring all core tests pass with mock-based, network-free implementations.

## Context
After NGRAF-001/002/003 refactoring, several tests are broken due to API changes. Tests need updating to match new patterns while maintaining fast, deterministic, network-free execution.

## Problem
- `test_rag.py` uses old `working_dir` parameter and function injection
- `test_config.py` expects validation that was removed (gleaning >= 0 now allowed)
- `test_openai.py` tests deprecated `_llm.py` functions instead of providers
- Tests make real network calls, causing slow/flaky execution
- Missing coverage for new provider and factory patterns

## Technical Solution (Minimal Complexity)

### Test Categories

#### Core Tests to Fix (Required)
```python
# These directly test current functionality
tests/test_config.py          # Update validation logic
tests/test_rag.py             # Migrate to new API
tests/test_splitter.py        # Verify still works
tests/test_json_parsing.py    # Keep as-is
tests/storage/test_factory.py # Already passing
tests/test_networkx_storage.py # Verify graph operations
tests/test_hnsw_vector_storage.py # Verify vector operations
tests/entity_extraction/*.py  # Already passing
```

#### Optional/Skip Tests
```python
# tests/test_neo4j_storage.py
import pytest
import os

# Skip unless Neo4j is actually configured
@pytest.mark.skipif(
    not os.environ.get("NEO4J_URL") or not os.environ.get("NEO4J_AUTH"),
    reason="Neo4j not configured (set NEO4J_URL and NEO4J_AUTH to test)"
)
class TestNeo4jStorage:
    # Or mock the driver entirely:
    @patch('neo4j.AsyncGraphDatabase')
    async def test_neo4j_operations(self, mock_driver):
        # Test with mocked driver
        pass

# Any test that would hit the network
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="API key not set for integration test"
)
async def test_real_api_integration():
    # Only runs with real credentials
    pass
```

### Specific Fixes

#### 1. Fix test_rag.py
```python
# OLD (broken)
rag = GraphRAG(working_dir=WORKING_DIR, embedding_func=local_embedding)

# NEW (correct) - patch providers BEFORE instantiation
from nano_graphrag.config import GraphRAGConfig
from nano_graphrag import GraphRAG

# Patch providers before GraphRAG.__init__ runs
with patch('nano_graphrag.llm.providers.get_llm_provider') as mock_llm, \
     patch('nano_graphrag.llm.providers.get_embedding_provider') as mock_embed:
    
    mock_llm.return_value = create_mock_llm_provider()
    mock_embed.return_value = create_mock_embedding_provider()
    
    config = GraphRAGConfig(
        storage=StorageConfig(working_dir=tmp_path),  # Use tmp_path fixture
    )
    rag = GraphRAG(config=config)
    # ... test code

# Limit mock_data.txt for speed
def load_test_data(max_chars=10000):
    """Load limited test data for fast tests."""
    with open("tests/mock_data.txt") as f:
        return f.read()[:max_chars]
```

#### 2. Fix test_config.py validation
```python
# Remove this test or update expectation
def test_validation(self):
    # max_gleaning=0 is now allowed for speed
    config = EntityExtractionConfig(max_gleaning=0)
    assert config.max_gleaning == 0  # Should pass
```

#### 3. Modernize test_openai.py → test_providers.py
```python
# Test providers, not deprecated functions
from nano_graphrag.llm.providers import OpenAIProvider, get_llm_provider, get_embedding_provider
from unittest.mock import AsyncMock, patch

async def test_openai_provider_gpt5_params():
    """Test GPT-5 specific parameter mapping."""
    with patch('openai.AsyncOpenAI') as mock_client:
        provider = OpenAIProvider(model="gpt-5-mini")
        mock_create = AsyncMock()
        mock_client.return_value.chat.completions.create = mock_create
        
        # Test max_tokens → max_completion_tokens mapping
        await provider.complete("test", max_tokens=1000)
        call_kwargs = mock_create.call_args.kwargs
        assert "max_completion_tokens" in call_kwargs
        assert call_kwargs["max_completion_tokens"] == 1000
        assert call_kwargs.get("reasoning_effort") == "minimal"

async def test_provider_none_content_guard():
    """Test handling of None content from GPT-5."""
    with patch('openai.AsyncOpenAI') as mock_client:
        provider = OpenAIProvider(model="gpt-5")
        mock_response = Mock()
        mock_response.choices[0].message.content = None
        mock_client.return_value.chat.completions.create = AsyncMock(
            return_value=mock_response
        )
        result = await provider.complete("test")
        assert result.text == ""  # Should default to empty string

async def test_base_url_separation():
    """Test LLM_BASE_URL vs EMBEDDING_BASE_URL separation."""
    with patch.dict(os.environ, {
        "LLM_BASE_URL": "http://localhost:1234/v1",
        "EMBEDDING_BASE_URL": "https://api.openai.com/v1"
    }):
        llm_provider = get_llm_provider("openai", "test-model")
        embed_provider = get_embedding_provider("openai", "text-embedding-3-small")
        
        assert llm_provider.base_url == "http://localhost:1234/v1"
        assert embed_provider.base_url == "https://api.openai.com/v1"

async def test_complete_with_cache():
    """Test caching behavior with mock KV storage."""
    from nano_graphrag.llm.base import BaseLLMProvider
    from nano_graphrag.base import BaseKVStorage
    
    mock_kv = AsyncMock(spec=BaseKVStorage)
    mock_kv.get_by_id.return_value = {"return": "cached_result"}
    
    provider = Mock(spec=BaseLLMProvider)
    # Test cache hit path
    result = await provider.complete_with_cache(
        "prompt", hashing_kv=mock_kv
    )
    assert result == "cached_result"
    mock_kv.get_by_id.assert_called_once()

async def test_request_timeout_config():
    """Test request timeout is properly configured."""
    with patch.dict(os.environ, {"LLM_REQUEST_TIMEOUT": "60.0"}):
        from nano_graphrag.config import LLMConfig
        config = LLMConfig.from_env()
        assert config.request_timeout == 60.0
```

### Testing Principles

#### 1. Mock All External Dependencies
```python
# Mock file I/O
@patch('builtins.open', mock_open(read_data='test data'))
@patch('pathlib.Path.exists', return_value=True)

# Mock API clients
@patch('openai.AsyncOpenAI')
@patch('neo4j.AsyncGraphDatabase')

# Mock embeddings
async def mock_embedding(texts):
    return np.random.rand(len(texts), 1536)
```

#### 2. Use Fixtures for Common Setup
```python
@pytest.fixture
def mock_config():
    return GraphRAGConfig(
        llm=LLMConfig(provider="openai", model="gpt-5-mini"),
        storage=StorageConfig(working_dir="/tmp/test"),
    )

@pytest.fixture
def mock_llm_provider():
    provider = AsyncMock(spec=BaseLLMProvider)
    provider.complete.return_value = CompletionResponse(
        text="test response",
        usage={"total_tokens": 100}
    )
    return provider
```

#### 3. Test Isolation
```python
# Each test gets fresh state
@pytest.fixture(autouse=True)
def cleanup():
    yield
    # Clean storage factory state properly
    from nano_graphrag.storage.factory import StorageFactory
    StorageFactory._vector_backends = {}
    StorageFactory._graph_backends = {}
    StorageFactory._kv_backends = {}
    # Or rely on idempotent registration

# Use tmp_path fixture for working directories
@pytest.fixture
def temp_working_dir(tmp_path):
    """Provide clean temporary directory for each test."""
    os.environ["STORAGE_WORKING_DIR"] = str(tmp_path)
    return tmp_path
```

## Definition of Done

### Required Tests Pass
```bash
# Core functionality tests
pytest tests/test_config.py -xvs
pytest tests/test_rag.py -xvs  
pytest tests/test_splitter.py -xvs
pytest tests/test_json_parsing.py -xvs
pytest tests/storage/test_factory.py -xvs
pytest tests/test_networkx_storage.py -xvs
pytest tests/test_hnsw_vector_storage.py -xvs
pytest tests/entity_extraction/ -xvs

# All should pass without network access
# All should complete in < 10 seconds total
```

### Test Coverage Metrics
```python
# Run with coverage
pytest --cov=nano_graphrag --cov-report=term-missing

# Target coverage for core modules:
# - config.py: > 90%
# - storage/factory.py: > 90%  
# - llm/providers/__init__.py: > 80% (especially base URL selection logic)
# - llm/base.py: > 80% (especially caching paths)
# - llm/providers/openai.py: > 75% (GPT-5 params, None guards)
# - graphrag.py: > 70%
```

### What NOT to Test
- ❌ Real API calls (use mocks)
- ❌ Real file system writes (use tmp_path fixture)
- ❌ Neo4j integration (not implemented yet)
- ❌ Performance/timing (separate benchmark suite)
- ❌ Examples directory (those are integration examples)

## Implementation Approach

1. **Fix one test file at a time**
   - Start with test_config.py (simplest)
   - Then test_rag.py (most important)
   - Finally provider tests

2. **Create shared test utilities**
   ```python
   # tests/utils.py
   def create_mock_provider():
       """Create mock LLM provider with standard responses."""
   
   def create_test_config(**overrides):
       """Create test config with sensible defaults."""
   ```

3. **Document test patterns**
   ```python
   # tests/README.md
   ## Testing Guidelines
   - Always use mocks for external services
   - Use pytest fixtures for setup
   - Keep tests under 100ms each
   - Test behavior, not implementation
   ```

## Feature Branch
`feature/ngraf-004.5-test-modernization`

## Pull Request Must Include
- All core tests passing
- No network calls in tests
- Test execution < 10 seconds
- Coverage report showing improvements
- Updated test documentation

## Benefits
- **Fast CI/CD**: Tests run in seconds, not minutes
- **Reliable**: No flaky network-dependent tests
- **Maintainable**: Clear patterns for future tests
- **Safe Refactoring**: Comprehensive coverage enables confident changes