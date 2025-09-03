# NGRAF-001: Abstract LLM Provider Interface

## Summary
Refactor scattered LLM integration code into a unified provider interface with proper typing and minimal complexity.

## Problem
- LLM functions spread across `_llm.py` and `deepseek.py` with duplicate retry/caching logic
- Model names hardcoded inside functions (`gpt_4o_mini_complete` uses "gpt-4.1-mini")
- GraphRAG uses function pointers making provider switching complex
- No consistent typing for LLM responses

## Technical Solution

```python
# nano_graphrag/llm/base.py
from typing import AsyncIterator, Optional, List, Dict
import numpy as np

class BaseLLMProvider:
    def __init__(self, model: str, api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or os.getenv(self.env_key)
    
    async def complete(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> str:
        raise NotImplementedError
    
    async def embed(self, texts: List[str]) -> np.ndarray:
        raise NotImplementedError
```

## Code Changes

### New Files
- `nano_graphrag/llm/base.py` - Base provider with typing
- `nano_graphrag/llm/providers/openai.py` - Extract from `_llm.py:50-175`
- `nano_graphrag/llm/providers/deepseek.py` - Extract from `deepseek.py`

### Modified Files
- `nano_graphrag/graphrag.py` - Replace `best_model_func: callable` with `llm_provider: BaseLLMProvider`
- `app.py:86-119` - Use provider instance instead of function references

## Definition of Done

### Unit Tests Required
```python
# tests/llm/test_providers.py
import pytest
import numpy as np
from unittest.mock import AsyncMock, patch

class TestLLMProviders:
    @pytest.mark.asyncio
    async def test_openai_provider_complete(self):
        """Verify OpenAI provider returns string completion"""
        provider = OpenAIProvider(model="gpt-4o-mini")
        with patch('openai.AsyncOpenAI') as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=Mock(choices=[Mock(message=Mock(content="test"))])
            )
            result = await provider.complete("test prompt")
            assert isinstance(result, str)
            assert result == "test"
    
    @pytest.mark.asyncio
    async def test_deepseek_provider_caching(self):
        """Verify DeepSeek provider uses cache correctly"""
        provider = DeepSeekProvider(model="deepseek-chat")
        mock_cache = AsyncMock()
        mock_cache.get_by_id.return_value = {"return": "cached_response"}
        
        result = await provider.complete("test", hashing_kv=mock_cache)
        assert result == "cached_response"
        mock_cache.get_by_id.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_provider_embedding_dimensions(self):
        """Verify embeddings return correct dimensions"""
        provider = OpenAIProvider(model="gpt-4o")
        with patch('openai.AsyncOpenAI') as mock_client:
            mock_embedding = np.random.rand(2, 1536)
            mock_client.return_value.embeddings.create = AsyncMock(
                return_value=Mock(data=[Mock(embedding=e) for e in mock_embedding])
            )
            result = await provider.embed(["text1", "text2"])
            assert result.shape == (2, 1536)
            assert isinstance(result, np.ndarray)
    
    def test_provider_initialization_from_env(self):
        """Verify provider reads API key from environment"""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            provider = OpenAIProvider(model="gpt-4o")
            assert provider.api_key == 'test-key'
```

### Additional Test Coverage
- Test retry logic triggers on rate limits
- Test streaming returns AsyncIterator[str]
- Test all providers implement base interface
- Test provider switching in GraphRAG

## Feature Branch
`feature/ngraf-001-llm-provider-abstraction`

## Pull Request Must Include
- All existing retry/caching logic preserved
- Type hints on all methods and returns
- No hardcoded model names
- Comments only for complex retry/caching logic
- All tests passing with >90% coverage