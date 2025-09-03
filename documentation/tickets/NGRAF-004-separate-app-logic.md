# NGRAF-004: [WON'T DO] Separate Application Logic from Core Library

## Status: WON'T DO

### Reason for Closure
This ticket was based on an incorrect understanding of the codebase structure. The ticket references:
- `app.py` with FastAPI application logic
- `deepseek.py` with DeepSeek integration and executive order parsing
- Federal Register API logic embedded in core files
- Redis caching tied to application layer

However, after thorough investigation:
1. **These files do not exist** in the current nano-graphrag repository
2. The repository is already a **clean library-only implementation**
3. There is no app logic to separate - the separation already exists
4. The confusion arose from reviewing a different fork or modified version

The current codebase properly maintains library boundaries and does not mix application concerns with library code. Therefore, this ticket is invalid and marked as WON'T DO.

---

## Original Summary (Invalid)
Extract FastAPI application and executive order logic from core nano-graphrag, creating clear separation between library and application.

## Problem
- `app.py` mixes web framework code with GraphRAG logic
- `deepseek.py` contains both provider code and executive order parsing
- Federal Register API logic embedded in core files
- Redis caching tied to application layer but used by library

## Technical Solution

```python
# nano_graphrag/core.py - Pure library interface
from typing import AsyncIterator, List, Dict, Optional

class NanoGraphRAG:
    def __init__(self, config: GraphRAGConfig):
        self.config = config
        self._init_storage()
        self._init_llm()
    
    async def insert(self, documents: List[str]) -> None:
        """Insert documents into knowledge graph"""
        pass
    
    async def query(
        self, 
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
        stream: bool = False
    ) -> AsyncIterator[str] | str:
        """Query the knowledge graph"""
        pass

# app/main.py - Application layer
from fastapi import FastAPI
from nano_graphrag import NanoGraphRAG

app = FastAPI()
graphrag = NanoGraphRAG(config)

@app.post("/stream")
async def stream_query(query: str, history: list = None):
    async for chunk in graphrag.query(query, history, stream=True):
        yield chunk
```

## Code Changes

### New Structure
```
nano-graphrag/
├── nano_graphrag/        # Core library only
│   ├── core.py           # Main interface
│   ├── llm/              # LLM providers
│   ├── storage/          # Storage backends
│   └── config.py         # Configuration
├── app/                  # Application layer
│   ├── main.py           # FastAPI app
│   ├── services/         # Business logic
│   │   ├── federal.py    # Federal Register integration
│   │   └── cache.py      # Redis caching
│   └── models.py         # Pydantic models
└── tests/
    ├── core/             # Library tests
    └── app/              # Application tests
```

### Files to Move/Refactor
- `app.py` → Split into `app/main.py` and `nano_graphrag/core.py`
- `deepseek.py:38-52` (executive order parsing) → `app/services/federal.py`
- Redis logic from `app.py` → `app/services/cache.py`

## Definition of Done

### Unit Tests Required
```python
# tests/core/test_core.py
import pytest
from unittest.mock import AsyncMock, Mock
from nano_graphrag.core import NanoGraphRAG

class TestNanoGraphRAG:
    @pytest.mark.asyncio
    async def test_insert_documents(self):
        """Verify document insertion without application layer"""
        config = Mock()
        rag = NanoGraphRAG(config)
        rag._storage = AsyncMock()
        
        await rag.insert(["doc1", "doc2"])
        rag._storage.insert.assert_called_once_with(["doc1", "doc2"])
    
    @pytest.mark.asyncio
    async def test_query_without_streaming(self):
        """Verify non-streaming query returns string"""
        config = Mock()
        rag = NanoGraphRAG(config)
        rag._llm = AsyncMock(return_value="response")
        
        result = await rag.query("test query", stream=False)
        assert isinstance(result, str)
        assert result == "response"
    
    @pytest.mark.asyncio
    async def test_query_with_streaming(self):
        """Verify streaming query returns AsyncIterator"""
        config = Mock()
        rag = NanoGraphRAG(config)
        
        async def mock_stream():
            for chunk in ["chunk1", "chunk2"]:
                yield chunk
        
        rag._llm = Mock(stream=mock_stream)
        
        chunks = []
        async for chunk in await rag.query("test", stream=True):
            chunks.append(chunk)
        assert chunks == ["chunk1", "chunk2"]

# tests/app/test_federal_service.py
class TestFederalService:
    @pytest.mark.asyncio
    async def test_parse_executive_orders(self):
        """Verify EO parsing separated from core"""
        from app.services.federal import parse_executive_orders
        
        mock_docs = [{"title": "EO 1", "number": "2025-001"}]
        result = parse_executive_orders(mock_docs)
        assert len(result) == 1
        assert result[0]["number"] == "2025-001"
    
    @pytest.mark.asyncio
    async def test_fetch_federal_register(self):
        """Verify Federal Register API integration"""
        from app.services.federal import fetch_latest_orders
        
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_get.return_value.json.return_value = {"results": []}
            orders = await fetch_latest_orders()
            assert orders == []
```

### Additional Test Coverage
- Test core library works without FastAPI
- Test application layer uses core properly
- Test separation of concerns maintained
- Test no circular dependencies

## Feature Branch
`feature/ngraf-004-separate-app-logic`

## Pull Request Must Include
- Clear separation between library and application
- Core library usable without FastAPI
- All application logic in `app/` directory
- Proper typing for public interfaces
- All tests passing with >90% coverage