"""DSPy-based entity extraction strategy with lazy loading."""

from typing import Dict, Any, Optional
import asyncio
from collections import defaultdict

from .base import BaseEntityExtractor, ExtractorConfig, ExtractionResult, TextChunkSchema
from nano_graphrag._utils import logger


class DSPyEntityExtractor(BaseEntityExtractor):
    """Entity extraction using DSPy framework with lazy loading."""

    def __init__(self, config: ExtractorConfig):
        """Initialize DSPy extractor."""
        super().__init__(config)
        self._extractor_module = None
        self._dspy = None

    async def _initialize_impl(self):
        """Initialize DSPy components with lazy loading."""
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
            # Wrap async model function for DSPy
            class AsyncModelWrapper:
                def __init__(self, async_func):
                    self.async_func = async_func

                def __call__(self, prompt, **kwargs):
                    # DSPy expects synchronous calls
                    import asyncio
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # We're already in async context, create task
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(asyncio.run, self.async_func(prompt, **kwargs))
                            return future.result()
                    else:
                        return loop.run_until_complete(self.async_func(prompt, **kwargs))

            lm = AsyncModelWrapper(self.config.model_func)
        else:
            # Use default OpenAI
            lm = self._dspy.OpenAI(
                model=self.config.model_name or "gpt-5-mini",
                max_tokens=4000
            )

        self._dspy.settings.configure(lm=lm)

        # Create extractor module
        from .module import TypedEntityRelationshipExtractor

        self._extractor_module = TypedEntityRelationshipExtractor(
            entity_types=self.config.entity_types,
            num_refine_turns=self.config.strategy_params.get("num_refine_turns", 1),
            self_refine=self.config.strategy_params.get("self_refine", True)
        )

        # Load compiled module if provided
        if self.config.strategy_params.get("compiled_module_path"):
            self._extractor_module.load(
                self.config.strategy_params["compiled_module_path"]
            )

    async def extract(
        self,
        chunks: Dict[str, TextChunkSchema],
        storage: Optional[Any] = None
    ) -> ExtractionResult:
        """Extract entities from chunks using DSPy."""
        all_results = []

        for chunk_id, chunk_data in chunks.items():
            text = chunk_data.get("content", "")
            result = await self.extract_single(text, chunk_id)
            all_results.append(result)

        return self.deduplicate_entities(all_results)

    async def extract_single(
        self,
        text: str,
        chunk_id: Optional[str] = None
    ) -> ExtractionResult:
        """Extract from single text using DSPy."""
        try:
            # Run extraction in thread pool to avoid blocking
            prediction = await asyncio.to_thread(
                self._extractor_module,
                input_text=text
            )

            nodes = {}
            edges = []

            # Convert DSPy entities to standard format
            for entity in prediction.entities:
                # Handle both dict and object formats
                if isinstance(entity, dict):
                    entity_name = entity.get("entity_name", "").upper()
                    entity_type = entity.get("entity_type", "UNKNOWN").upper()
                    entity_desc = entity.get("entity_description", "")
                else:
                    entity_name = getattr(entity, "entity_name", "").upper()
                    entity_type = getattr(entity, "entity_type", "UNKNOWN").upper()
                    entity_desc = getattr(entity, "entity_description", "")

                if entity_name:
                    nodes[entity_name] = {
                        "entity_name": entity_name,
                        "entity_type": entity_type,
                        "description": entity_desc,
                        "source_id": chunk_id
                    }

            # Convert DSPy relationships to standard format
            for rel in prediction.relationships:
                # Handle both dict and object formats
                if isinstance(rel, dict):
                    src_id = rel.get("src_id", "").upper()
                    tgt_id = rel.get("tgt_id", "").upper()
                    description = rel.get("description", "")
                    weight = rel.get("weight", 1.0)
                else:
                    # Handle nested entity objects
                    if hasattr(rel, "src_entity"):
                        src_id = getattr(rel.src_entity, "entity_name", "").upper()
                    else:
                        src_id = getattr(rel, "src_id", "").upper()

                    if hasattr(rel, "tgt_entity"):
                        tgt_id = getattr(rel.tgt_entity, "entity_name", "").upper()
                    else:
                        tgt_id = getattr(rel, "tgt_id", "").upper()

                    if hasattr(rel, "relationship_description"):
                        description = rel.relationship_description
                    else:
                        description = getattr(rel, "description", "")

                    weight = getattr(rel, "weight", 1.0)

                if src_id and tgt_id:
                    edges.append((
                        src_id,
                        tgt_id,
                        {
                            "weight": weight,
                            "description": description,
                            "source_id": chunk_id
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