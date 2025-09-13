# Entity Extraction Strategies

## Overview

nano-graphrag supports multiple entity extraction strategies to suit different needs:

1. **LLM-based** (Default): Simple, direct LLM prompts with gleaning
2. **DSPy-based**: Advanced, optimizable extraction with DSPy framework
3. **Custom**: Bring your own extraction logic

## Strategy Comparison

| Strategy | Pros | Cons | Best For |
|----------|------|------|----------|
| LLM | Simple, no extra dependencies, fast setup | Less sophisticated, depends on LLM quality | Quick prototypes, general domains |
| DSPy | Optimizable, self-improving, structured output | Requires DSPy dependency, more complex | Production systems, complex domains |
| Custom | Full control, domain-specific logic | Requires implementation effort | Specialized domains, custom requirements |

## Configuration

### LLM-based Extraction (Default)

```python
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, EntityExtractionConfig

config = GraphRAGConfig(
    entity_extraction=EntityExtractionConfig(
        strategy="llm",
        max_gleaning=1,  # Number of extraction refinement iterations
        summary_max_tokens=500
    )
)

rag = GraphRAG(config)
```

### DSPy-based Extraction

First install DSPy:
```bash
pip install dspy-ai
```

Then configure:
```python
config = GraphRAGConfig(
    entity_extraction=EntityExtractionConfig(
        strategy="dspy",
        max_gleaning=0  # DSPy has its own refinement
    )
)

rag = GraphRAG(config)
```

### Custom Extraction

Implement your own extractor by inheriting from `BaseEntityExtractor`:

```python
from nano_graphrag.entity_extraction.base import BaseEntityExtractor, ExtractionResult

class MyCustomExtractor(BaseEntityExtractor):
    async def _initialize_impl(self):
        # Load models, resources, etc.
        pass

    async def extract_single(self, text: str, chunk_id: str = None):
        # Your extraction logic
        nodes = {}  # Extract entities
        edges = []  # Extract relationships
        return ExtractionResult(nodes=nodes, edges=edges)

    async def extract(self, chunks, storage=None):
        # Extract from multiple chunks
        results = []
        for chunk_id, chunk_data in chunks.items():
            result = await self.extract_single(chunk_data["content"], chunk_id)
            results.append(result)
        return self.deduplicate_entities(results)
```

Then use it via the factory:
```python
from nano_graphrag.entity_extraction.factory import create_extractor

extractor = create_extractor(
    strategy="custom",
    custom_extractor_class="mymodule.MyCustomExtractor"
)
```

## Performance Tuning

### LLM Strategy
- Adjust `max_gleaning` for accuracy vs speed tradeoff (0-3 recommended)
- Set `summary_max_tokens` based on your domain complexity
- The model function's rate limiting will control concurrency

### DSPy Strategy
- DSPy automatically optimizes extraction through its framework
- Consider providing training data for better results
- Monitor extraction quality and retrain as needed

### Custom Strategy
- Implement batch processing in your `extract` method
- Use `asyncio.gather` for parallel processing
- Consider caching frequently extracted patterns

## Migration from Direct Function Calls

If you were previously using direct extraction functions:

```python
# Old way
from nano_graphrag.entity_extraction.extract import extract_entities_dspy

rag = GraphRAG(
    entity_extraction_func=extract_entities_dspy
)
```

Migrate to configuration-based approach:

```python
# New way
config = GraphRAGConfig(
    entity_extraction=EntityExtractionConfig(strategy="dspy")
)
rag = GraphRAG(config)
```

## Advanced Configuration

### Entity Types

Configure which entity types to extract:

```python
config = GraphRAGConfig(
    entity_extraction=EntityExtractionConfig(
        strategy="llm",
        # Default types are: PERSON, ORGANIZATION, LOCATION, EVENT, CONCEPT
        # These are passed to the extraction prompts
    )
)
```

### Extraction Limits

The system validates extraction results to ensure quality:

- Maximum entities per chunk: 20 (default)
- Maximum relationships per chunk: 30 (default)

Results exceeding these limits will be clamped with a warning.

## Troubleshooting

### DSPy Import Error
If you see "dspy-ai is required for DSPy extraction", install it:
```bash
pip install dspy-ai
```

### Empty Extraction Results
- Check your LLM is responding correctly
- Verify your text chunks contain extractable entities
- Enable debug logging to see extraction prompts and responses

### Performance Issues
- For LLM strategy: Extraction is now parallelized across chunks
- For DSPy strategy: Ensure DSPy is properly configured
- Consider reducing `max_gleaning` for faster extraction

## Implementation Details

The extraction system uses a clean abstraction pattern:

1. **BaseEntityExtractor**: Abstract base class defining the interface
2. **LLMEntityExtractor**: Uses prompt-based extraction with gleaning
3. **DSPyEntityExtractor**: Wraps DSPy's TypedEntityRelationshipExtractor
4. **Factory Pattern**: `create_extractor()` handles strategy selection

All extractors return `ExtractionResult` objects with:
- `nodes`: Dictionary of entity_id -> entity_data
- `edges`: List of (source, target, edge_data) tuples
- `metadata`: Additional extraction metadata

The results are automatically deduplicated and validated before storage.