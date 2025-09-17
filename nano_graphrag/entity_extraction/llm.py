"""LLM prompt-based entity extraction strategy."""

import re
from typing import Dict, Any, Optional, List
from collections import defaultdict

from .base import BaseEntityExtractor, ExtractorConfig, ExtractionResult, TextChunkSchema
from nano_graphrag._utils import (
    logger,
    clean_str,
    split_string_by_multi_markers,
    pack_user_ass_to_openai_messages,
    is_float_regex
)
from nano_graphrag.prompt import GRAPH_FIELD_SEP, PROMPTS


class LLMEntityExtractor(BaseEntityExtractor):
    """Entity extraction using LLM prompts with gleaning."""

    async def _initialize_impl(self):
        """Initialize LLM extractor."""
        if not self.config.model_func:
            raise ValueError("model_func is required for LLM extraction")

    async def extract(
        self,
        chunks: Dict[str, TextChunkSchema],
        storage: Optional[Any] = None
    ) -> ExtractionResult:
        """Extract entities from chunks using LLM prompts."""
        import asyncio

        # Parallelize extraction across chunks
        tasks = [
            self.extract_single(chunk_data.get("content", ""), chunk_id)
            for chunk_id, chunk_data in chunks.items()
        ]

        # Execute all extractions concurrently
        # Rate limiting is handled by the wrapped model_func
        results = await asyncio.gather(*tasks)

        return self.deduplicate_entities(results)

    async def extract_single(
        self,
        text: str,
        chunk_id: Optional[str] = None
    ) -> ExtractionResult:
        """Extract from single text using LLM prompts with gleaning."""
        entity_extract_prompt = PROMPTS["entity_extraction"]
        context_base = dict(
            tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
            record_delimiter=PROMPTS["DEFAULT_RECORD_DELIMITER"],
            completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
            entity_types=",".join(self.config.entity_types),
            input_text=text
        )

        hint_prompt = entity_extract_prompt.format(**context_base)
        final_result = await self.config.model_func(hint_prompt)

        if isinstance(final_result, list):
            final_result = final_result[0]["text"]

        # Log the raw LLM output for debugging
        logger.info(f"[EXTRACT] Chunk {chunk_id} - LLM returned {len(final_result) if final_result else 0} chars")
        if final_result:
            # Log first 500 chars of the response to see what format we're getting
            logger.info(f"[EXTRACT] LLM output sample: {final_result}...")
        else:
            logger.warning(f"[EXTRACT] LLM returned empty/None result for chunk {chunk_id}")

        # Gleaning iterations
        if self.config.max_gleaning > 0:
            continue_prompt = PROMPTS["entity_continue_extraction"]
            if_loop_prompt = PROMPTS["entity_if_loop_extraction"]

            history = pack_user_ass_to_openai_messages(hint_prompt, final_result, False)

            for glean_index in range(self.config.max_gleaning):
                glean_result = await self.config.model_func(continue_prompt, history=history)
                history += pack_user_ass_to_openai_messages(continue_prompt, glean_result, False)
                final_result += glean_result

                if glean_index == self.config.max_gleaning - 1:
                    break

                if_loop_result: str = await self.config.model_func(
                    if_loop_prompt, history=history
                )
                if_loop_result = if_loop_result.strip().strip('"').strip("'").lower()
                if if_loop_result != "yes":
                    break

        # Parse extraction results
        records = split_string_by_multi_markers(
            final_result,
            [context_base["record_delimiter"], context_base["completion_delimiter"]],
        )

        logger.info(f"[EXTRACT] Chunk {chunk_id} - Parsed {len(records)} records from LLM output")
        if records:
            logger.info(f"[EXTRACT] Sample records (first 3): {records[:3]}")

        nodes = {}
        edges = []

        for record in records:
            record_match = re.search(r"\((.*)\)", record)
            if record_match is None:
                continue
            record_content = record_match.group(1)
            record_attributes = split_string_by_multi_markers(
                record_content, [context_base["tuple_delimiter"]]
            )

            # Handle entity extraction
            if len(record_attributes) >= 4 and record_attributes[0] == '"entity"':
                entity_name = clean_str(record_attributes[1].upper())
                if entity_name.strip():
                    entity_type = clean_str(record_attributes[2].upper())
                    entity_description = clean_str(record_attributes[3])

                    nodes[entity_name] = {
                        "entity_name": entity_name,
                        "entity_type": entity_type,
                        "description": entity_description,
                        "source_id": chunk_id
                    }

            # Handle relationship extraction
            elif len(record_attributes) >= 5 and record_attributes[0] == '"relationship"':
                source = clean_str(record_attributes[1].upper())
                target = clean_str(record_attributes[2].upper())
                edge_description = clean_str(record_attributes[3])
                weight = (
                    float(record_attributes[-1])
                    if is_float_regex(record_attributes[-1])
                    else 1.0
                )

                edges.append((
                    source,
                    target,
                    {
                        "weight": weight,
                        "description": edge_description,
                        "source_id": chunk_id
                    }
                ))

        # Log extraction results for this chunk
        logger.info(f"[EXTRACT] Chunk {chunk_id} results: {len(nodes)} entities, {len(edges)} relationships")
        if not edges and nodes:
            logger.warning(f"[EXTRACT] Chunk {chunk_id} has entities but NO relationships!")

        return ExtractionResult(
            nodes=nodes,
            edges=edges,
            metadata={"chunk_id": chunk_id, "method": "llm"}
        )