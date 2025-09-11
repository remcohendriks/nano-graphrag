# NGRAF-014: Entity Extraction Abstraction Layer

## Overview
Create a pluggable entity extraction system that allows users to choose between different extraction strategies (DSPy-based, prompt-based, custom), improving flexibility and reducing barriers to entry while maintaining backward compatibility.

## Current State
- Entity extraction tightly coupled to DSPy implementation in `nano_graphrag/entity_extraction/extract.py`
- DSPy is complex and has heavy dependencies
- No way to switch extraction strategies
- GraphRAG class has no configuration for extraction method
- High barrier to entry for users unfamiliar with DSPy
- No simple prompt-based alternative

## Proposed Implementation

### Phase 1: Define Extraction Interface

#### Create `nano_graphrag/entity_extraction/base.py`
```python
"""Base interface for entity extraction strategies."""

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field
import asyncio

from nano_graphrag._storage import BaseKVStorage
from nano_graphrag._utils import logger

@dataclass
class ExtractionResult:
    """Result of entity extraction."""
    
    nodes: Dict[str, Dict[str, Any]]  # node_id -> node_data
    edges: List[Tuple[str, str, Dict[str, Any]]]  # (source, target, edge_data)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def merge(self, other: "ExtractionResult") -> "ExtractionResult":
        """Merge with another extraction result."""
        merged_nodes = {**self.nodes, **other.nodes}
        merged_edges = self.edges + other.edges
        merged_metadata = {**self.metadata, **other.metadata}
        
        return ExtractionResult(
            nodes=merged_nodes,
            edges=merged_edges,
            metadata=merged_metadata
        )

@dataclass
class ExtractorConfig:
    """Configuration for entity extractors."""
    
    # Common configuration
    entity_types: List[str] = field(default_factory=lambda: [
        "Person", "Organization", "Location", "Event", "Concept"
    ])
    max_entities_per_chunk: int = 20
    max_relationships_per_chunk: int = 30
    include_entity_descriptions: bool = True
    include_relationship_descriptions: bool = True
    
    # Model configuration
    model_func: Optional[Any] = None  # LLM function
    model_name: Optional[str] = None
    max_retries: int = 3
    
    # Strategy-specific config
    strategy_params: Dict[str, Any] = field(default_factory=dict)

class BaseEntityExtractor(ABC):
    """Abstract base class for entity extraction strategies."""
    
    def __init__(self, config: ExtractorConfig):
        """Initialize extractor with configuration."""
        self.config = config
        self._initialized = False
    
    async def initialize(self):
        """Initialize the extractor (load models, etc)."""
        if not self._initialized:
            await self._initialize_impl()
            self._initialized = True
    
    @abstractmethod
    async def _initialize_impl(self):
        """Implementation-specific initialization."""
        pass
    
    @abstractmethod
    async def extract(
        self,
        chunks: Dict[str, Any],
        storage: Optional[BaseKVStorage] = None
    ) -> ExtractionResult:
        """Extract entities and relationships from text chunks.
        
        Args:
            chunks: Dictionary of chunk_id -> chunk_data
            storage: Optional storage for caching
            
        Returns:
            ExtractionResult containing nodes and edges
        """
        pass
    
    @abstractmethod
    async def extract_single(
        self,
        text: str,
        chunk_id: Optional[str] = None
    ) -> ExtractionResult:
        """Extract from a single text chunk.
        
        Args:
            text: Text to extract from
            chunk_id: Optional chunk identifier
            
        Returns:
            ExtractionResult for this chunk
        """
        pass
    
    async def batch_extract(
        self,
        texts: List[str],
        batch_size: int = 10
    ) -> List[ExtractionResult]:
        """Batch extraction for multiple texts.
        
        Args:
            texts: List of texts to process
            batch_size: Number of texts to process concurrently
            
        Returns:
            List of extraction results
        """
        results = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_tasks = [
                self.extract_single(text, chunk_id=f"batch_{i+j}")
                for j, text in enumerate(batch)
            ]
            batch_results = await asyncio.gather(*batch_tasks)
            results.extend(batch_results)
        
        return results
    
    def validate_result(self, result: ExtractionResult) -> bool:
        """Validate extraction result meets requirements.
        
        Args:
            result: Extraction result to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Check entity count limits
        if len(result.nodes) > self.config.max_entities_per_chunk:
            logger.warning(f"Too many entities: {len(result.nodes)}")
            return False
        
        # Check relationship count limits
        if len(result.edges) > self.config.max_relationships_per_chunk:
            logger.warning(f"Too many relationships: {len(result.edges)}")
            return False
        
        # Validate entity types
        for node_id, node_data in result.nodes.items():
            if "type" in node_data:
                if node_data["type"] not in self.config.entity_types:
                    logger.warning(f"Invalid entity type: {node_data['type']}")
                    return False
        
        return True
    
    @staticmethod
    def deduplicate_entities(
        results: List[ExtractionResult],
        similarity_threshold: float = 0.9
    ) -> ExtractionResult:
        """Deduplicate entities across multiple extraction results.
        
        Args:
            results: List of extraction results
            similarity_threshold: Threshold for considering entities duplicates
            
        Returns:
            Merged and deduplicated result
        """
        # Simple deduplication based on entity names
        merged_nodes = {}
        merged_edges = []
        
        for result in results:
            for node_id, node_data in result.nodes.items():
                # Simple dedup by name
                if node_id not in merged_nodes:
                    merged_nodes[node_id] = node_data
                else:
                    # Merge data
                    for key, value in node_data.items():
                        if key not in merged_nodes[node_id]:
                            merged_nodes[node_id][key] = value
            
            merged_edges.extend(result.edges)
        
        # Deduplicate edges
        unique_edges = []
        seen_edges = set()
        
        for edge in merged_edges:
            edge_key = (edge[0], edge[1], edge[2].get("relation", ""))
            if edge_key not in seen_edges:
                unique_edges.append(edge)
                seen_edges.add(edge_key)
        
        return ExtractionResult(nodes=merged_nodes, edges=unique_edges)
```

### Phase 2: DSPy-based Extractor (Refactored)

#### Update `nano_graphrag/entity_extraction/dspy_extractor.py`
```python
"""DSPy-based entity extraction strategy."""

from typing import Dict, Any, Optional, List
import asyncio

from .base import BaseEntityExtractor, ExtractorConfig, ExtractionResult
from nano_graphrag._utils import logger

class DSPyEntityExtractor(BaseEntityExtractor):
    """Entity extraction using DSPy framework."""
    
    def __init__(self, config: ExtractorConfig):
        """Initialize DSPy extractor."""
        super().__init__(config)
        self._extractor_module = None
        self._dspy = None
    
    async def _initialize_impl(self):
        """Initialize DSPy components."""
        # Lazy import DSPy
        try:
            import dspy
            self._dspy = dspy
        except ImportError:
            raise ImportError(
                "dspy-ai is required for DSPy extraction. "
                "Install with: pip install dspy-ai"
            )
        
        # Initialize DSPy with model
        if self.config.model_func:
            # Use provided model
            lm = self._create_dspy_model(self.config.model_func)
        else:
            # Use default
            lm = self._dspy.OpenAI(
                model=self.config.model_name or "gpt-4",
                max_tokens=4000
            )
        
        self._dspy.settings.configure(lm=lm)
        
        # Create extractor module
        from .typed_entity_extraction import TypedEntityRelationshipExtractor
        
        self._extractor_module = TypedEntityRelationshipExtractor(
            entity_types=self.config.entity_types,
            **self.config.strategy_params
        )
        
        # Compile if dataset provided
        if "training_data" in self.config.strategy_params:
            self._compile_extractor()
    
    def _create_dspy_model(self, model_func):
        """Create DSPy model wrapper from function."""
        class CustomDSPyModel:
            def __init__(self, func):
                self.func = func
            
            def __call__(self, prompt, **kwargs):
                return self.func(prompt, **kwargs)
        
        return CustomDSPyModel(model_func)
    
    def _compile_extractor(self):
        """Compile DSPy module with training data."""
        training_data = self.config.strategy_params.get("training_data", [])
        
        if not training_data:
            return
        
        # Create optimizer
        optimizer = self._dspy.BootstrapFewShot(
            metric=self._extraction_metric,
            max_bootstrapped_demos=4,
            max_labeled_demos=4
        )
        
        # Compile
        self._extractor_module = optimizer.compile(
            self._extractor_module,
            trainset=training_data
        )
        
        logger.info("DSPy extractor compiled with training data")
    
    def _extraction_metric(self, example, prediction, trace=None):
        """Metric for DSPy optimization."""
        # Check if extraction produced valid entities
        if not prediction.entities:
            return 0.0
        
        # Check entity quality
        valid_entities = 0
        for entity in prediction.entities:
            if entity.entity_type in self.config.entity_types:
                valid_entities += 1
        
        # Check relationships
        valid_relationships = len(prediction.relationships) > 0
        
        # Combined score
        entity_score = valid_entities / max(len(prediction.entities), 1)
        relationship_score = 1.0 if valid_relationships else 0.5
        
        return entity_score * relationship_score
    
    async def extract(
        self,
        chunks: Dict[str, Any],
        storage: Optional[Any] = None
    ) -> ExtractionResult:
        """Extract entities from chunks using DSPy."""
        all_results = []
        
        for chunk_id, chunk_data in chunks.items():
            text = chunk_data.get("content", "")
            result = await self.extract_single(text, chunk_id)
            all_results.append(result)
        
        # Deduplicate and merge
        return self.deduplicate_entities(all_results)
    
    async def extract_single(
        self,
        text: str,
        chunk_id: Optional[str] = None
    ) -> ExtractionResult:
        """Extract from single text using DSPy."""
        try:
            # Run extraction
            prediction = self._extractor_module(
                input_text=text,
                entity_types=self.config.entity_types
            )
            
            # Convert to standard format
            nodes = {}
            edges = []
            
            for entity in prediction.entities:
                node_id = entity.entity_name
                nodes[node_id] = {
                    "type": entity.entity_type,
                    "description": entity.entity_description,
                    "source_chunk": chunk_id
                }
            
            for rel in prediction.relationships:
                edges.append((
                    rel.src_entity.entity_name,
                    rel.tgt_entity.entity_name,
                    {
                        "relation": rel.relationship_description,
                        "source_chunk": chunk_id
                    }
                ))
            
            return ExtractionResult(
                nodes=nodes,
                edges=edges,
                metadata={"chunk_id": chunk_id, "method": "dspy"}
            )
            
        except Exception as e:
            logger.error(f"DSPy extraction failed: {e}")
            return ExtractionResult(nodes={}, edges=[])
```

### Phase 3: Prompt-based Extractor

#### Create `nano_graphrag/entity_extraction/prompt_extractor.py`
```python
"""Simple prompt-based entity extraction strategy."""

import json
import re
from typing import Dict, Any, Optional, List
import asyncio

from .base import BaseEntityExtractor, ExtractorConfig, ExtractionResult
from nano_graphrag._utils import logger

class PromptEntityExtractor(BaseEntityExtractor):
    """Entity extraction using direct LLM prompts."""
    
    def __init__(self, config: ExtractorConfig):
        """Initialize prompt-based extractor."""
        super().__init__(config)
        self._system_prompt = self._build_system_prompt()
        self._example_output = self._build_example_output()
    
    async def _initialize_impl(self):
        """Initialize prompt extractor."""
        if not self.config.model_func:
            raise ValueError("model_func is required for prompt extraction")
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for extraction."""
        entity_types_str = ", ".join(self.config.entity_types)
        
        return f"""You are an expert at extracting entities and relationships from text.

Extract entities and relationships from the given text. Focus on these entity types:
{entity_types_str}

Rules:
1. Extract only the most important entities (max {self.config.max_entities_per_chunk})
2. Extract meaningful relationships between entities (max {self.config.max_relationships_per_chunk})
3. Provide brief descriptions for entities and relationships
4. Use consistent entity names across the text
5. Return results in the specified JSON format

Output Format:
{{
    "entities": [
        {{
            "name": "Entity Name",
            "type": "Entity Type",
            "description": "Brief description"
        }}
    ],
    "relationships": [
        {{
            "source": "Source Entity Name",
            "target": "Target Entity Name",
            "relation": "Relationship Type",
            "description": "Brief description"
        }}
    ]
}}"""
    
    def _build_example_output(self) -> str:
        """Build example output for few-shot learning."""
        return json.dumps({
            "entities": [
                {
                    "name": "Apple Inc.",
                    "type": "Organization",
                    "description": "Technology company that designs and manufactures consumer electronics"
                },
                {
                    "name": "Steve Jobs",
                    "type": "Person",
                    "description": "Co-founder and former CEO of Apple Inc."
                }
            ],
            "relationships": [
                {
                    "source": "Steve Jobs",
                    "target": "Apple Inc.",
                    "relation": "founded",
                    "description": "Steve Jobs co-founded Apple Inc. in 1976"
                }
            ]
        }, indent=2)
    
    async def extract(
        self,
        chunks: Dict[str, Any],
        storage: Optional[Any] = None
    ) -> ExtractionResult:
        """Extract entities from chunks using prompts."""
        tasks = []
        
        for chunk_id, chunk_data in chunks.items():
            text = chunk_data.get("content", "")
            tasks.append(self.extract_single(text, chunk_id))
        
        results = await asyncio.gather(*tasks)
        
        # Merge and deduplicate
        return self.deduplicate_entities(results)
    
    async def extract_single(
        self,
        text: str,
        chunk_id: Optional[str] = None
    ) -> ExtractionResult:
        """Extract from single text using prompt."""
        prompt = f"""Extract entities and relationships from this text:

Text:
{text}

Example Output:
{self._example_output}

Now extract from the given text:"""
        
        try:
            # Call LLM
            response = await self.config.model_func(
                prompt,
                system_prompt=self._system_prompt,
                max_tokens=2000
            )
            
            # Parse JSON response
            extracted = self._parse_response(response)
            
            # Convert to standard format
            nodes = {}
            edges = []
            
            for entity in extracted.get("entities", []):
                node_id = entity["name"]
                nodes[node_id] = {
                    "type": entity.get("type", "Unknown"),
                    "description": entity.get("description", ""),
                    "source_chunk": chunk_id
                }
            
            for rel in extracted.get("relationships", []):
                edges.append((
                    rel["source"],
                    rel["target"],
                    {
                        "relation": rel.get("relation", "related_to"),
                        "description": rel.get("description", ""),
                        "source_chunk": chunk_id
                    }
                ))
            
            result = ExtractionResult(
                nodes=nodes,
                edges=edges,
                metadata={"chunk_id": chunk_id, "method": "prompt"}
            )
            
            # Validate result
            if self.validate_result(result):
                return result
            else:
                logger.warning(f"Invalid extraction result for chunk {chunk_id}")
                return ExtractionResult(nodes={}, edges=[])
            
        except Exception as e:
            logger.error(f"Prompt extraction failed: {e}")
            return ExtractionResult(nodes={}, edges=[])
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response to extract JSON."""
        # Try to extract JSON from response
        try:
            # First try: direct JSON parsing
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Second try: extract JSON from markdown code blocks
        json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        match = re.search(json_pattern, response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Third try: find JSON-like structure
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        
        # Fallback: empty result
        logger.warning("Failed to parse JSON from LLM response")
        return {"entities": [], "relationships": []}
```

### Phase 4: Integration with GraphRAG

#### Update `nano_graphrag/config.py`
```python
@dataclass
class ExtractionConfig:
    """Configuration for entity extraction."""
    
    strategy: str = "prompt"  # "dspy", "prompt", or custom class name
    entity_types: List[str] = field(default_factory=lambda: [
        "Person", "Organization", "Location", "Event", "Concept"
    ])
    max_entities_per_chunk: int = 20
    max_relationships_per_chunk: int = 30
    include_descriptions: bool = True
    
    # DSPy-specific
    dspy_compile: bool = False
    dspy_training_data: Optional[str] = None  # Path to training data
    
    # Custom extractor
    custom_extractor_class: Optional[str] = None  # Import path
    
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class GraphRAGConfig:
    # ... existing fields ...
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
```

#### Update `nano_graphrag/graphrag.py`
```python
class GraphRAG:
    def __init__(self, config: GraphRAGConfig):
        # ... existing init ...
        
        # Initialize entity extractor
        self._entity_extractor = self._init_extractor()
    
    def _init_extractor(self) -> BaseEntityExtractor:
        """Initialize the entity extractor based on configuration."""
        from nano_graphrag.entity_extraction import (
            DSPyEntityExtractor,
            PromptEntityExtractor,
            ExtractorConfig
        )
        
        # Build extractor config
        extractor_config = ExtractorConfig(
            entity_types=self.config.extraction.entity_types,
            max_entities_per_chunk=self.config.extraction.max_entities_per_chunk,
            max_relationships_per_chunk=self.config.extraction.max_relationships_per_chunk,
            include_entity_descriptions=self.config.extraction.include_descriptions,
            include_relationship_descriptions=self.config.extraction.include_descriptions,
            model_func=self.config.llm.best_model_func,
            model_name=self.config.llm.best_model_name
        )
        
        # Select strategy
        strategy = self.config.extraction.strategy.lower()
        
        if strategy == "dspy":
            # DSPy extractor with optional compilation
            strategy_params = {}
            if self.config.extraction.dspy_training_data:
                # Load training data
                import json
                with open(self.config.extraction.dspy_training_data) as f:
                    strategy_params["training_data"] = json.load(f)
            
            extractor_config.strategy_params = strategy_params
            return DSPyEntityExtractor(extractor_config)
        
        elif strategy == "prompt":
            # Simple prompt-based extractor
            return PromptEntityExtractor(extractor_config)
        
        elif self.config.extraction.custom_extractor_class:
            # Custom extractor
            import importlib
            
            module_path, class_name = self.config.extraction.custom_extractor_class.rsplit(".", 1)
            module = importlib.import_module(module_path)
            extractor_class = getattr(module, class_name)
            
            return extractor_class(extractor_config)
        
        else:
            raise ValueError(f"Unknown extraction strategy: {strategy}")
    
    async def _extract_entities(self, chunks: Dict[str, Any]) -> ExtractionResult:
        """Extract entities using configured strategy."""
        # Initialize extractor if needed
        await self._entity_extractor.initialize()
        
        # Run extraction
        result = await self._entity_extractor.extract(
            chunks,
            storage=self._kv_storage
        )
        
        return result
```

### Phase 5: Migration Guide and Examples

#### Create `docs/entity_extraction.md`
```markdown
# Entity Extraction Strategies

## Overview

nano-graphrag supports multiple entity extraction strategies to suit different needs:

1. **Prompt-based** (Default): Simple, direct LLM prompts
2. **DSPy-based**: Advanced, optimizable extraction with DSPy
3. **Custom**: Bring your own extraction logic

## Strategy Comparison

| Strategy | Pros | Cons | Best For |
|----------|------|------|----------|
| Prompt | Simple, no dependencies, fast | Less sophisticated | Quick prototypes, simple domains |
| DSPy | Optimizable, self-improving, sophisticated | Complex, requires DSPy | Production systems, complex domains |
| Custom | Full control | Requires implementation | Specialized domains |

## Configuration

### Prompt-based Extraction (Default)

```python
from nano_graphrag.config import GraphRAGConfig, ExtractionConfig

config = GraphRAGConfig(
    extraction=ExtractionConfig(
        strategy="prompt",
        entity_types=["Person", "Organization", "Location"],
        max_entities_per_chunk=15
    )
)
```

### DSPy-based Extraction

```python
config = GraphRAGConfig(
    extraction=ExtractionConfig(
        strategy="dspy",
        dspy_compile=True,
        dspy_training_data="path/to/training.json"
    )
)
```

### Custom Extraction

```python
from nano_graphrag.entity_extraction import BaseEntityExtractor

class MyCustomExtractor(BaseEntityExtractor):
    async def extract_single(self, text: str, chunk_id: str = None):
        # Your extraction logic
        return ExtractionResult(...)

config = GraphRAGConfig(
    extraction=ExtractionConfig(
        strategy="custom",
        custom_extractor_class="mymodule.MyCustomExtractor"
    )
)
```

## Migration from Legacy DSPy

If you're using the old DSPy-only extraction:

```python
# Old way (implicit DSPy)
rag = GraphRAG()  # Used DSPy by default

# New way (explicit strategy)
config = GraphRAGConfig(
    extraction=ExtractionConfig(strategy="dspy")
)
rag = GraphRAG(config)
```

## Performance Tuning

### Prompt Strategy
- Adjust `max_entities_per_chunk` for speed vs coverage
- Use specific entity types for better precision
- Consider caching for repeated texts

### DSPy Strategy
- Provide training data for better results
- Use compilation for production
- Monitor and retrain periodically

## Examples

See `examples/extraction_strategies.py` for complete examples.
```

#### Create `examples/extraction_strategies.py`
```python
"""Examples of different entity extraction strategies."""

import asyncio
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, ExtractionConfig

async def example_prompt_extraction():
    """Example using prompt-based extraction."""
    config = GraphRAGConfig(
        extraction=ExtractionConfig(
            strategy="prompt",
            entity_types=["Person", "Company", "Product", "Technology"],
            max_entities_per_chunk=10
        )
    )
    
    rag = GraphRAG(config)
    
    text = """
    Steve Jobs co-founded Apple Inc. with Steve Wozniak in 1976.
    Apple revolutionized personal computing with the Macintosh and
    later dominated mobile with the iPhone.
    """
    
    await rag.ainsert(text)
    
    # Query
    result = await rag.aquery("Who founded Apple?")
    print(f"Prompt extraction result: {result}")

async def example_dspy_extraction():
    """Example using DSPy extraction with optimization."""
    config = GraphRAGConfig(
        extraction=ExtractionConfig(
            strategy="dspy",
            entity_types=["Person", "Organization", "Event", "Location"],
            dspy_compile=False  # Set True with training data
        )
    )
    
    rag = GraphRAG(config)
    
    # Insert and query...

async def example_custom_extraction():
    """Example using custom extraction logic."""
    from nano_graphrag.entity_extraction import BaseEntityExtractor, ExtractionResult
    
    class DomainSpecificExtractor(BaseEntityExtractor):
        """Custom extractor for specific domain."""
        
        async def _initialize_impl(self):
            # Load domain-specific models or rules
            pass
        
        async def extract_single(self, text: str, chunk_id: str = None):
            # Custom extraction logic
            # For example, use regex for specific patterns
            import re
            
            nodes = {}
            edges = []
            
            # Extract email addresses as entities
            emails = re.findall(r'[\w\.-]+@[\w\.-]+', text)
            for email in emails:
                nodes[email] = {
                    "type": "Email",
                    "description": f"Email address: {email}"
                }
            
            # Extract URLs
            urls = re.findall(r'https?://[^\s]+', text)
            for url in urls:
                nodes[url] = {
                    "type": "URL",
                    "description": f"Web URL: {url}"
                }
            
            return ExtractionResult(nodes=nodes, edges=edges)
    
    # Register and use custom extractor
    config = GraphRAGConfig(
        extraction=ExtractionConfig(
            strategy="custom",
            custom_extractor_class="__main__.DomainSpecificExtractor"
        )
    )
    
    rag = GraphRAG(config)
    # Use as normal...

if __name__ == "__main__":
    asyncio.run(example_prompt_extraction())
```

## Definition of Done

- [ ] Base extraction interface created:
  - [ ] BaseEntityExtractor abstract class
  - [ ] ExtractionResult and ExtractorConfig dataclasses
  - [ ] Validation and deduplication utilities
- [ ] Extraction strategies implemented:
  - [ ] DSPyEntityExtractor (refactored from existing)
  - [ ] PromptEntityExtractor (new, simple)
  - [ ] Support for custom extractors
- [ ] GraphRAG integration:
  - [ ] ExtractionConfig in GraphRAGConfig
  - [ ] Extractor initialization in GraphRAG
  - [ ] Backward compatibility maintained
- [ ] Testing:
  - [ ] Unit tests for each extractor
  - [ ] Integration tests with GraphRAG
  - [ ] Performance comparison tests
  - [ ] Custom extractor example tests
- [ ] Documentation:
  - [ ] Strategy comparison guide
  - [ ] Migration guide from legacy
  - [ ] Custom extractor tutorial
  - [ ] Performance tuning guide
- [ ] Examples:
  - [ ] Prompt extraction example
  - [ ] DSPy extraction example
  - [ ] Custom extractor example
  - [ ] Strategy comparison example

## Feature Branch
`feature/ngraf-014-extraction-abstraction`

## Pull Request Requirements
- All extraction strategies pass same test suite
- Performance benchmarks for each strategy
- Documentation review
- Example validation in CI
- Backward compatibility tests pass

## Technical Considerations
- Keep DSPy as optional dependency
- Ensure async throughout for performance
- Cache extraction results when possible
- Consider streaming for large documents
- Plan for future strategies (NER models, etc.)