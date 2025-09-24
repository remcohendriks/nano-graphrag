"""LLM prompt-based entity extraction strategy."""

import re
import json
import html
from typing import Dict, Any, Optional, List
from collections import defaultdict

from .base import BaseEntityExtractor, ExtractorConfig, ExtractionResult, TextChunkSchema
from nano_graphrag._utils import (
    logger,
    pack_user_ass_to_openai_messages
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

        # Check if extraction is complete or truncated
        completion_delimiter = context_base["completion_delimiter"]
        has_completed = completion_delimiter in final_result

        # Check for common truncation indicators
        is_truncated = (
            not has_completed and
            final_result and
            (final_result.rstrip().endswith(("...", "etc", "etc.")) or len(final_result) > 1500)
        )

        if is_truncated:
            logger.info(f"[EXTRACT] Chunk {chunk_id} - Extraction appears truncated, starting continuation...")

        # Continuation loop for truncated extractions
        history = pack_user_ass_to_openai_messages(hint_prompt, final_result, False)
        continuation_count = 0

        while not has_completed and is_truncated and continuation_count < self.config.max_continuation_attempts:
            continuation_prompt = PROMPTS["entity_extraction_continuation"].format(
                completion_delimiter=completion_delimiter
            )

            logger.info(f"[EXTRACT] Chunk {chunk_id} - Continuation attempt {continuation_count + 1}/{self.config.max_continuation_attempts}")
            continuation_result = await self.config.model_func(continuation_prompt, history=history)

            if isinstance(continuation_result, list):
                continuation_result = continuation_result[0]["text"]

            history += pack_user_ass_to_openai_messages(continuation_prompt, continuation_result, False)
            final_result += "\n" + continuation_result  # Add newline to separate continuations
            continuation_count += 1

            logger.info(f"[EXTRACT] Continuation {continuation_count}: Added {len(continuation_result)} chars")

            # Check if we're now complete
            has_completed = completion_delimiter in continuation_result

            if has_completed:
                logger.info(f"[EXTRACT] Chunk {chunk_id} - Extraction completed after {continuation_count} continuations")
                break

        if continuation_count >= self.config.max_continuation_attempts and not has_completed:
            logger.warning(f"[EXTRACT] Chunk {chunk_id} - Max continuations reached without completion")

        # Gleaning iterations (for finding missed entities, not for continuing truncated output)
        if self.config.max_gleaning > 0:
            continue_prompt = PROMPTS["entity_continue_extraction"]
            if_loop_prompt = PROMPTS["entity_if_loop_extraction"]

            # Note: history is already set from continuation loop above, which includes all continuations

            for glean_index in range(self.config.max_gleaning):
                glean_result = await self.config.model_func(continue_prompt, history=history)
                history += pack_user_ass_to_openai_messages(continue_prompt, glean_result, False)
                # Ensure newline between responses for proper NDJSON parsing
                if final_result and not final_result.endswith('\n'):
                    final_result += '\n'
                final_result += glean_result

                if glean_index == self.config.max_gleaning - 1:
                    break

                if_loop_result: str = await self.config.model_func(
                    if_loop_prompt, history=history
                )
                if_loop_result = if_loop_result.strip().strip('"').strip("'").lower()
                if if_loop_result != "yes":
                    break

        # Helper function for safe float conversion
        def safe_float(value, default=1.0):
            try:
                return float(value) if value is not None else default
            except (ValueError, TypeError):
                return default

        def sanitize_str(text):
            if not text:
                return ""
            text = html.unescape(text)
            text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
            return text.strip()

        # Parse NDJSON format
        nodes = {}
        edges = []
        entity_count = 0
        relationship_count = 0

        lines = final_result.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line or context_base["completion_delimiter"] in line:
                continue

            try:
                obj = json.loads(line)

                if obj.get('type') == 'entity':
                    entity_name = sanitize_str(obj.get('name', '')).upper()
                    if entity_name:
                        nodes[entity_name] = {
                            "entity_name": entity_name,
                            "entity_type": sanitize_str(obj.get('entity_type', 'UNKNOWN')),
                            "description": sanitize_str(obj.get('description', '')),
                            "source_id": chunk_id
                        }
                        entity_count += 1

                elif obj.get('type') == 'relationship':
                    source = sanitize_str(obj.get('source', '')).upper()
                    target = sanitize_str(obj.get('target', '')).upper()
                    if source and target:
                        edges.append((
                            source,
                            target,
                            {
                                "weight": safe_float(obj.get('strength'), 1.0),
                                "description": sanitize_str(obj.get('description', '')),
                                "source_id": chunk_id
                            }
                        ))
                        relationship_count += 1

            except (json.JSONDecodeError, ValueError) as e:
                logger.debug(f"Failed to parse line: {line[:100]}... Error: {e}")
                continue

        logger.info(f"[EXTRACT] Chunk {chunk_id} - Parsed {entity_count} entities, {relationship_count} relationships")

        # Log extraction results for this chunk
        logger.info(f"[EXTRACT] Chunk {chunk_id} results: {len(nodes)} entities, {len(edges)} relationships")
        if not edges and nodes:
            logger.warning(f"[EXTRACT] Chunk {chunk_id} has entities but NO relationships!")

        return ExtractionResult(
            nodes=nodes,
            edges=edges,
            metadata={"chunk_id": chunk_id, "method": "llm"}
        )