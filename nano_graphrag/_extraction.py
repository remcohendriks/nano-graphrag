"""Entity and relationship extraction operations for nano-graphrag."""

import re
import asyncio
from typing import Union, Dict, List, Optional, Any, Tuple
from collections import Counter, defaultdict
from ._utils import (
    logger,
    clean_str,
    compute_mdhash_id,
    is_float_regex,
    pack_user_ass_to_openai_messages,
    split_string_by_multi_markers,
    TokenizerWrapper
)
from .base import (
    BaseGraphStorage,
    BaseVectorStorage,
    TextChunkSchema,
)
from .prompt import GRAPH_FIELD_SEP, PROMPTS
from .schemas import NodeData, EdgeData, ExtractionRecord, RelationshipRecord


async def _handle_entity_relation_summary(
    entity_or_relation_name: str,
    description: str,
    global_config: dict,
    tokenizer_wrapper: TokenizerWrapper,
) -> str:
    use_llm_func: callable = global_config["cheap_model_func"]
    llm_max_tokens = global_config["cheap_model_max_token_size"]
    summary_max_tokens = global_config["entity_summary_to_max_tokens"]


    tokens = tokenizer_wrapper.encode(description)
    if len(tokens) < summary_max_tokens:
        return description
    prompt_template = PROMPTS["summarize_entity_descriptions"]

    use_description = tokenizer_wrapper.decode(tokens[:llm_max_tokens])
    context_base = dict(
        entity_name=entity_or_relation_name,
        description_list=use_description.split(GRAPH_FIELD_SEP),
    )
    use_prompt = prompt_template.format(**context_base)
    logger.debug(f"Trigger summary: {entity_or_relation_name}")
    summary = await use_llm_func(use_prompt, max_tokens=summary_max_tokens)
    return summary


async def _handle_single_entity_extraction(
    record_attributes: List[str],
    chunk_key: str,
) -> Optional[Dict[str, Any]]:
    if len(record_attributes) < 4:
        logger.debug(f"[EXTRACT] Entity parse failed - not enough attributes: {record_attributes}")
        return None
    if record_attributes[0] != '"entity"':
        logger.debug(f"[EXTRACT] Not an entity record: {record_attributes[0]}")
        return None
    # add this record as a node in the G
    entity_name = clean_str(record_attributes[1].upper())
    if not entity_name.strip():
        return None
    entity_type = clean_str(record_attributes[2].upper())
    entity_description = clean_str(record_attributes[3])
    entity_source_id = chunk_key
    return dict(
        entity_name=entity_name,
        entity_type=entity_type,
        description=entity_description,
        source_id=entity_source_id,
    )


async def _handle_single_relationship_extraction(
    record_attributes: List[str],
    chunk_key: str,
) -> Optional[Dict[str, Any]]:
    if len(record_attributes) < 5:
        logger.debug(f"[EXTRACT] Relationship parse failed - not enough attributes: {record_attributes}")
        return None
    if record_attributes[0] != '"relationship"':
        logger.debug(f"[EXTRACT] Not a relationship record: {record_attributes[0]}")
        return None
    # add this record as edge
    source = clean_str(record_attributes[1].upper())
    target = clean_str(record_attributes[2].upper())
    edge_description = clean_str(record_attributes[3])
    edge_source_id = chunk_key
    weight = (
        float(record_attributes[-1]) if is_float_regex(record_attributes[-1]) else 1.0
    )
    return dict(
        src_id=source,
        tgt_id=target,
        weight=weight,
        description=edge_description,
        source_id=edge_source_id,
    )


async def _merge_nodes_then_upsert(
    entity_name: str,
    nodes_data: List[Dict[str, Any]],
    knwoledge_graph_inst: BaseGraphStorage,
    global_config: Dict[str, Any],
    tokenizer_wrapper: TokenizerWrapper,
) -> Dict[str, Any]:
    already_entitiy_types = []
    already_source_ids = []
    already_description = []

    already_node = await knwoledge_graph_inst.get_node(entity_name)
    if already_node is not None:
        already_entitiy_types.append(already_node["entity_type"])
        already_source_ids.extend(
            split_string_by_multi_markers(already_node["source_id"], [GRAPH_FIELD_SEP])
        )
        already_description.append(already_node["description"])

    entity_type = sorted(
        Counter(
            [dp["entity_type"] for dp in nodes_data] + already_entitiy_types
        ).items(),
        key=lambda x: x[1],
        reverse=True,
    )[0][0]
    description = GRAPH_FIELD_SEP.join(
        sorted(set([dp["description"] for dp in nodes_data] + already_description))
    )
    source_id = GRAPH_FIELD_SEP.join(
        set([dp["source_id"] for dp in nodes_data] + already_source_ids)
    )
    description = await _handle_entity_relation_summary(
        entity_name, description, global_config, tokenizer_wrapper
    )
    node_data = dict(
        entity_type=entity_type,
        description=description,
        source_id=source_id,
    )
    await knwoledge_graph_inst.upsert_node(
        entity_name,
        node_data=node_data,
    )
    node_data["entity_name"] = entity_name
    return node_data


async def _merge_edges_then_upsert(
    src_id: str,
    tgt_id: str,
    edges_data: List[Dict[str, Any]],
    knwoledge_graph_inst: BaseGraphStorage,
    global_config: Dict[str, Any],
    tokenizer_wrapper: TokenizerWrapper,
) -> None:
    already_weights = []
    already_source_ids = []
    already_description = []
    already_order = []
    if await knwoledge_graph_inst.has_edge(src_id, tgt_id):
        already_edge = await knwoledge_graph_inst.get_edge(src_id, tgt_id)
        already_weights.append(already_edge["weight"])
        already_source_ids.extend(
            split_string_by_multi_markers(already_edge["source_id"], [GRAPH_FIELD_SEP])
        )
        already_description.append(already_edge["description"])
        already_order.append(already_edge.get("order", 1))

    # [numberchiffre]: `Relationship.order` is only returned from DSPy's predictions
    order = min([dp.get("order", 1) for dp in edges_data] + already_order)
    weight = sum([dp["weight"] for dp in edges_data] + already_weights)
    description = GRAPH_FIELD_SEP.join(
        sorted(set([dp["description"] for dp in edges_data] + already_description))
    )
    source_id = GRAPH_FIELD_SEP.join(
        set([dp["source_id"] for dp in edges_data] + already_source_ids)
    )
    for need_insert_id in [src_id, tgt_id]:
        if not (await knwoledge_graph_inst.has_node(need_insert_id)):
            await knwoledge_graph_inst.upsert_node(
                need_insert_id,
                node_data={
                    "source_id": source_id,
                    "description": description,
                    "entity_type": '"UNKNOWN"',
                },
            )
    description = await _handle_entity_relation_summary(
        (src_id, tgt_id), description, global_config, tokenizer_wrapper
    )
    await knwoledge_graph_inst.upsert_edge(
        src_id,
        tgt_id,
        edge_data=dict(
            weight=weight, description=description, source_id=source_id, order=order
        ),
    )


async def extract_entities(
    chunks: Dict[str, TextChunkSchema],
    knwoledge_graph_inst: BaseGraphStorage,
    entity_vdb: BaseVectorStorage,
    tokenizer_wrapper: TokenizerWrapper,
    global_config: Dict[str, Any],
    using_amazon_bedrock: bool=False,
) -> Optional[BaseGraphStorage]:
    import time
    start_time = time.time()
    logger.info(f"[EXTRACT] Starting extract_entities with {len(chunks)} chunks")
    use_llm_func: callable = global_config["best_model_func"]
    entity_extract_max_gleaning = global_config["entity_extract_max_gleaning"]
    logger.info(f"[EXTRACT] Max gleaning: {entity_extract_max_gleaning}")

    ordered_chunks = list(chunks.items())

    entity_extract_prompt = PROMPTS["entity_extraction"]
    context_base = dict(
        tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
        record_delimiter=PROMPTS["DEFAULT_RECORD_DELIMITER"],
        completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
        entity_types=",".join(PROMPTS["DEFAULT_ENTITY_TYPES"]),
    )
    continue_prompt = PROMPTS["entity_continue_extraction"]
    if_loop_prompt = PROMPTS["entity_if_loop_extraction"]

    already_processed = 0
    already_entities = 0
    already_relations = 0

    async def _process_single_content(chunk_key_dp: Tuple[str, TextChunkSchema]) -> Tuple[Dict[str, List], Dict[Tuple[str, str], List]]:
        nonlocal already_processed, already_entities, already_relations
        chunk_key = chunk_key_dp[0]
        chunk_dp = chunk_key_dp[1]
        content = chunk_dp["content"]
        hint_prompt = entity_extract_prompt.format(**context_base, input_text=content)
        final_result = await use_llm_func(hint_prompt)
        if isinstance(final_result, list):
            final_result = final_result[0]["text"]
        
        # Log the raw LLM output for debugging
        logger.info(f"[EXTRACT] Chunk {chunk_key} - LLM returned {len(final_result) if final_result else 0} chars")

        history = pack_user_ass_to_openai_messages(hint_prompt, final_result, using_amazon_bedrock)
        for now_glean_index in range(entity_extract_max_gleaning):
            glean_result = await use_llm_func(continue_prompt, history=history)

            history += pack_user_ass_to_openai_messages(continue_prompt, glean_result, using_amazon_bedrock)
            final_result += glean_result
            if now_glean_index == entity_extract_max_gleaning - 1:
                break

            if_loop_result: str = await use_llm_func(
                if_loop_prompt, history=history
            )
            if_loop_result = if_loop_result.strip().strip('"').strip("'").lower()
            if if_loop_result != "yes":
                break

        records = split_string_by_multi_markers(
            final_result,
            [context_base["record_delimiter"], context_base["completion_delimiter"]],
        )

        logger.info(f"[EXTRACT] Chunk {chunk_key} - Parsed {len(records)} records from LLM output")

        maybe_nodes = defaultdict(list)
        maybe_edges = defaultdict(list)

        # Log sample records for debugging
        if records:
            logger.info(f"[EXTRACT] Sample records (first 3): {records[:3]}")

        for record in records:
            record = re.search(r"\((.*)\)", record)
            if record is None:
                continue
            record = record.group(1)
            record_attributes = split_string_by_multi_markers(
                record, [context_base["tuple_delimiter"]]
            )
            if_entities = await _handle_single_entity_extraction(
                record_attributes, chunk_key
            )
            if if_entities is not None:
                maybe_nodes[if_entities["entity_name"]].append(if_entities)
                continue

            if_relation = await _handle_single_relationship_extraction(
                record_attributes, chunk_key
            )
            if if_relation is not None:
                maybe_edges[(if_relation["src_id"], if_relation["tgt_id"])].append(
                    if_relation
                )

        # Log extraction results for this chunk
        logger.info(f"[EXTRACT] Chunk {chunk_key} results: {len(maybe_nodes)} entities, {len(maybe_edges)} relationships")
        if not maybe_edges and maybe_nodes:
            logger.warning(f"[EXTRACT] Chunk {chunk_key} has entities but NO relationships!")

        already_processed += 1
        already_entities += len(maybe_nodes)
        already_relations += len(maybe_edges)
        now_ticks = PROMPTS["process_tickers"][
            already_processed % len(PROMPTS["process_tickers"])
        ]
        logger.debug(
            f"{now_ticks} Processed {already_processed}({already_processed*100//len(ordered_chunks)}%) chunks,  {already_entities} entities(duplicated), {already_relations} relations(duplicated)"
        )
        return dict(maybe_nodes), dict(maybe_edges)

    # use_llm_func is wrapped in ascynio.Semaphore, limiting max_async callings
    logger.info(f"[EXTRACT] Processing {len(ordered_chunks)} chunks in parallel...")
    extract_start = time.time()
    results = await asyncio.gather(
        *[_process_single_content(c) for c in ordered_chunks]
    )
    extract_time = time.time() - extract_start
    logger.info(f"[EXTRACT] Parallel extraction completed in {extract_time:.2f}s")
    # Progress complete
    maybe_nodes = defaultdict(list)
    maybe_edges = defaultdict(list)
    for m_nodes, m_edges in results:
        for k, v in m_nodes.items():
            maybe_nodes[k].extend(v)
        for k, v in m_edges.items():
            # it's undirected graph
            maybe_edges[tuple(sorted(k))].extend(v)
    
    logger.info(f"[EXTRACT] Extracted {len(maybe_nodes)} unique entities and {len(maybe_edges)} unique relationships")
    logger.info(f"[EXTRACT] Merging and upserting {len(maybe_nodes)} entities...")
    entity_start = time.time()
    all_entities_data = await asyncio.gather(
        *[
            _merge_nodes_then_upsert(k, v, knwoledge_graph_inst, global_config, tokenizer_wrapper)
            for k, v in maybe_nodes.items()
        ]
    )
    entity_time = time.time() - entity_start
    logger.info(f"[EXTRACT] Entity upsert completed in {entity_time:.2f}s")

    logger.info(f"[EXTRACT] Merging and upserting {len(maybe_edges)} relationships...")
    edge_start = time.time()
    await asyncio.gather(
        *[
            _merge_edges_then_upsert(k[0], k[1], v, knwoledge_graph_inst, global_config, tokenizer_wrapper)
            for k, v in maybe_edges.items()
        ]
    )
    edge_time = time.time() - edge_start
    logger.info(f"[EXTRACT] Relationship upsert completed in {edge_time:.2f}s")
    if not len(all_entities_data):
        logger.warning("[EXTRACT] WARNING: No entities extracted - check LLM configuration")
        total_time = time.time() - start_time
        logger.info(f"[EXTRACT] Total extraction time: {total_time:.2f}s (failed - no entities)")
        return None
    if entity_vdb is not None:
        logger.info(f"[EXTRACT] Updating entity vector DB with {len(all_entities_data)} entities...")
        vdb_start = time.time()
        data_for_vdb = {
            compute_mdhash_id(dp["entity_name"], prefix="ent-"): {
                "content": dp["entity_name"] + dp["description"],
                "entity_name": dp["entity_name"],
            }
            for dp in all_entities_data
        }
        await entity_vdb.upsert(data_for_vdb)
        vdb_time = time.time() - vdb_start
        logger.info(f"[EXTRACT] Vector DB updated in {vdb_time:.2f}s")

    total_time = time.time() - start_time
    logger.info(f"[EXTRACT] Total extraction time: {total_time:.2f}s (entities: {len(all_entities_data)}, edges: {len(maybe_edges)})")
    return knwoledge_graph_inst


async def extract_entities_from_chunks(
    chunks: List[TextChunkSchema],
    model_func: callable,
    tokenizer_wrapper: TokenizerWrapper,
    max_gleaning: int = 1,
    summary_max_tokens: int = 500,
    to_json_func: Optional[callable] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """Extract entities from chunks without storage side effects.
    
    Args:
        chunks: List of text chunks
        model_func: LLM function for extraction
        tokenizer_wrapper: Tokenizer
        max_gleaning: Number of extraction iterations
        summary_max_tokens: Max tokens for summaries
        to_json_func: Function to convert responses to JSON
        
    Returns:
        Dictionary with 'nodes' and 'edges' lists
    """
    if to_json_func is None:
        from ._utils import convert_response_to_json
        to_json_func = convert_response_to_json
    
    entity_extract_prompt = PROMPTS["entity_extraction"]
    context_base = dict(
        tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
        record_delimiter=PROMPTS["DEFAULT_RECORD_DELIMITER"],
        completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
        entity_types=PROMPTS["DEFAULT_ENTITY_TYPES"]
    )
    
    all_entities = {}
    all_relationships = []
    
    for chunk in chunks:
        context = dict(
            input_text=chunk["content"],
            **context_base
        )
        
        logger.debug(f"Processing chunk for entity extraction, max_gleaning={max_gleaning}")
        
        # Always do at least one extraction pass
        response = await model_func(
            entity_extract_prompt.format(**context)
        )
        
        # Accumulate responses from gleaning passes
        all_responses = [response]
        
        # Then do additional gleaning passes if configured
        for glean_index in range(max_gleaning):
            glean_response = await model_func(
                PROMPTS.get("entity_continue_extraction", PROMPTS.get("entity_extraction", "")).format(**context)
            )
            all_responses.append(glean_response)
        
        # Combine all responses with record delimiter to ensure proper parsing
        response = context_base["record_delimiter"].join(all_responses)
        
        # Parse entities and relationships from delimiter format response
        # The LLM returns format like: ("entity"<|>NAME<|>TYPE<|>DESC)##("relationship"<|>...)
        records = split_string_by_multi_markers(
            response,
            [context_base["record_delimiter"], context_base["completion_delimiter"]],
        )
        
        # Filter out empty records
        records = [r for r in records if r.strip()]
        
        for record in records:
            if not record.strip():
                continue
            # Extract content between parentheses
            match = re.search(r'\((.*)\)', record)
            if match is None:
                continue
            record_content = match.group(1)
            # Split by tuple delimiter
            attributes = split_string_by_multi_markers(
                record_content, [context_base["tuple_delimiter"]]
            )
            
            if len(attributes) >= 4 and attributes[0] == '"entity"':
                entity_name = clean_str(attributes[1].upper())
                if entity_name and entity_name not in all_entities:
                    all_entities[entity_name] = {
                        "name": entity_name,
                        "type": clean_str(attributes[2].upper()),
                        "description": clean_str(attributes[3])
                    }
            elif len(attributes) >= 4 and attributes[0] == '"relationship"':
                src = clean_str(attributes[1].upper())
                tgt = clean_str(attributes[2].upper())
                if src and tgt:
                    all_relationships.append({
                        "source": src,
                        "target": tgt,
                        "description": clean_str(attributes[3])
                    })
    
    # Convert to nodes and edges format
    nodes = [
        {
            "id": name,
            "name": name,
            "type": entity.get("type", "UNKNOWN"),
            "description": entity.get("description", "")[:summary_max_tokens]
        }
        for name, entity in all_entities.items()
    ]
    
    edges = [
        {
            "source": rel.get("source", rel.get("from")),
            "target": rel.get("target", rel.get("to")),
            "relation": rel.get("relation", rel.get("type", "RELATED")),
            "description": rel.get("description", "")
        }
        for rel in all_relationships
        if rel.get("source") or rel.get("from")
    ]
    
    logger.debug(f"Entity extraction completed - {len(nodes)} nodes, {len(edges)} edges")
    return {"nodes": nodes, "edges": edges}