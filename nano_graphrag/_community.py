"""Community detection and report generation for nano-graphrag."""

import asyncio
from typing import Dict, List, Optional, Any, Tuple, Set
from ._utils import (
    logger,
    list_of_list_to_csv,
    truncate_list_by_token_size,
    TokenizerWrapper
)
from .base import (
    BaseGraphStorage,
    BaseKVStorage,
    SingleCommunitySchema,
    CommunitySchema,
)
from .prompt import PROMPTS
# Import shared helper from extraction module
from ._extraction import _handle_entity_relation_summary
from .schemas import CommunityReportData


def _pack_single_community_by_sub_communities(
    community: SingleCommunitySchema,
    max_token_size: int,
    already_reports: Dict[str, CommunitySchema],
    tokenizer_wrapper: TokenizerWrapper,
) -> Tuple[str, int, Set[str], Set[Tuple[str, str]]]: 
    all_sub_communities = [
        already_reports[k] for k in community["sub_communities"] if k in already_reports
    ]
    all_sub_communities = sorted(
        all_sub_communities, key=lambda x: x["occurrence"], reverse=True
    )
    
    may_trun_all_sub_communities = truncate_list_by_token_size(
        all_sub_communities,
        key=lambda x: x["report_string"],
        max_token_size=max_token_size,
        tokenizer_wrapper=tokenizer_wrapper,
    )
    sub_fields = ["id", "report", "rating", "importance"]
    sub_communities_describe = list_of_list_to_csv(
        [sub_fields]
        + [
            [
                i,
                c["report_string"],
                c["report_json"].get("rating", -1),
                c["occurrence"],
            ]
            for i, c in enumerate(may_trun_all_sub_communities)
        ]
    )
    already_nodes = []
    already_edges = []
    for c in may_trun_all_sub_communities:
        already_nodes.extend(c["nodes"])
        already_edges.extend([tuple(e) for e in c["edges"]])
    

    return (
        sub_communities_describe,
        len(tokenizer_wrapper.encode(sub_communities_describe)),
        set(already_nodes),
        set(already_edges),
    )


async def _pack_single_community_describe(
    knwoledge_graph_inst: BaseGraphStorage,
    community: SingleCommunitySchema,
    tokenizer_wrapper: TokenizerWrapper,
    max_token_size: int = 12000,
    already_reports: Optional[Dict[str, CommunitySchema]] = None,
    global_config: Optional[Dict[str, Any]] = None,
) -> str:
    # Fix mutable default arguments
    if already_reports is None:
        already_reports = {}
    if global_config is None:
        global_config = {}
    
    # 1. 准备原始数据
    nodes_in_order = sorted(community["nodes"])
    edges_in_order = sorted(community["edges"], key=lambda x: x[0] + x[1])

    nodes_data = await asyncio.gather(
        *[knwoledge_graph_inst.get_node(n) for n in nodes_in_order]
    )
    edges_data = await asyncio.gather(
        *[knwoledge_graph_inst.get_edge(src, tgt) for src, tgt in edges_in_order]
    )


    # 2. 定义模板和固定开销
    final_template = """-----Reports-----
```csv
{reports}
```
-----Entities-----
```csv
{entities}
```
-----Relationships-----
```csv
{relationships}
```"""
    base_template_tokens = len(tokenizer_wrapper.encode(
        final_template.format(reports="", entities="", relationships="")
    ))
    remaining_budget = max_token_size - base_template_tokens

    # 3. 处理子社区报告
    report_describe = ""
    contain_nodes = set()
    contain_edges = set()
    
    # 启发式截断检测
    truncated = len(nodes_in_order) > 100 or len(edges_in_order) > 100
    
    need_to_use_sub_communities = (
        truncated and 
        community["sub_communities"] and 
        already_reports
    )
    force_to_use_sub_communities = global_config.get("addon_params", {}).get(
        "force_to_use_sub_communities", False
    )
    
    if need_to_use_sub_communities or force_to_use_sub_communities:
        logger.debug(f"Community {community['title']} using sub-communities")
        # 获取子社区报告及包含的节点/边
        result = _pack_single_community_by_sub_communities(
            community, remaining_budget, already_reports, tokenizer_wrapper
        )
        report_describe, report_size, contain_nodes, contain_edges = result
        remaining_budget = max(0, remaining_budget - report_size)

    # 4. 准备节点和边数据（过滤子社区已包含的）
    def format_row(row: list) -> str:
        return ','.join('"{}"'.format(str(item).replace('"', '""')) for item in row)

    node_fields = ["id", "entity", "type", "description", "degree"]
    edge_fields = ["id", "source", "target", "description", "rank"]

    # 获取度数并创建数据结构
    node_degrees = await knwoledge_graph_inst.node_degrees_batch(nodes_in_order)
    edge_degrees = await knwoledge_graph_inst.edge_degrees_batch(edges_in_order)
    
    # 过滤已存在于子社区的节点/边
    nodes_list_data = [
        [i, name, data.get("entity_type", "UNKNOWN"), 
         data.get("description", "UNKNOWN"), node_degrees[i]]
        for i, (name, data) in enumerate(zip(nodes_in_order, nodes_data))
        if name not in contain_nodes  # 关键过滤
    ]
    
    edges_list_data = [
        [i, edge[0], edge[1], data.get("description", "UNKNOWN"), edge_degrees[i]]
        for i, (edge, data) in enumerate(zip(edges_in_order, edges_data))
        if (edge[0], edge[1]) not in contain_edges  # 关键过滤
    ]
    
    # 按重要性排序
    nodes_list_data.sort(key=lambda x: x[-1], reverse=True)
    edges_list_data.sort(key=lambda x: x[-1], reverse=True)

    # 5. 动态分配预算
    # 计算表头开销
    header_tokens = len(tokenizer_wrapper.encode(
        list_of_list_to_csv([node_fields]) + "\n" + list_of_list_to_csv([edge_fields])
    ))



    data_budget = max(0, remaining_budget - header_tokens)
    total_items = len(nodes_list_data) + len(edges_list_data)
    node_ratio = len(nodes_list_data) / max(1, total_items)
    edge_ratio = 1 - node_ratio




    # 执行截断
    nodes_final = truncate_list_by_token_size(
        nodes_list_data, key=format_row, 
        max_token_size=int(data_budget * node_ratio), 
        tokenizer_wrapper=tokenizer_wrapper
    )
    edges_final = truncate_list_by_token_size(
        edges_list_data, key=format_row,
        max_token_size= int(data_budget * edge_ratio),
        tokenizer_wrapper=tokenizer_wrapper
    )

    # 6. 组装最终输出
    nodes_describe = list_of_list_to_csv([node_fields] + nodes_final)
    edges_describe = list_of_list_to_csv([edge_fields] + edges_final)



    final_output = final_template.format(
        reports=report_describe,
        entities=nodes_describe,
        relationships=edges_describe
    )

    return final_output


def _community_report_json_to_str(parsed_output: dict) -> str:
    """refer official graphrag: index/graph/extractors/community_reports"""
    title = parsed_output.get("title", "Report")
    summary = parsed_output.get("summary", "")
    findings = parsed_output.get("findings", [])

    def finding_summary(finding: dict):
        if isinstance(finding, str):
            return finding
        return finding.get("summary")

    def finding_explanation(finding: dict):
        if isinstance(finding, str):
            return ""
        return finding.get("explanation")

    report_sections = "\n\n".join(
        f"## {finding_summary(f)}\n\n{finding_explanation(f)}" for f in findings
    )
    return f"# {title}\n\n{summary}\n\n{report_sections}"


async def generate_community_report(
    community_report_kv: BaseKVStorage[CommunitySchema],
    knwoledge_graph_inst: BaseGraphStorage,
    tokenizer_wrapper: TokenizerWrapper,
    global_config: Dict[str, Any],
) -> None:
    llm_extra_kwargs = global_config["special_community_report_llm_kwargs"]
    use_llm_func: callable = global_config["best_model_func"]
    use_string_json_convert_func: callable = global_config["convert_response_to_json_func"]

    communities_schema = await knwoledge_graph_inst.community_schema()
    community_keys, community_values = list(communities_schema.keys()), list(communities_schema.values())
    already_processed = 0

    prompt_template = PROMPTS["community_report"]

    prompt_overhead = len(tokenizer_wrapper.encode(prompt_template.format(input_text="")))

    async def _form_single_community_report(
        community: SingleCommunitySchema, already_reports: Dict[str, CommunitySchema]
    ) -> Dict[str, Any]:
        nonlocal already_processed
        describe = await _pack_single_community_describe(
            knwoledge_graph_inst,
            community,
            tokenizer_wrapper=tokenizer_wrapper, 
            max_token_size=global_config["best_model_max_token_size"] - prompt_overhead -200, # extra token for chat template and prompt template
            already_reports=already_reports,
            global_config=global_config,
        )
        prompt = prompt_template.format(input_text=describe)


        response = await use_llm_func(prompt, **llm_extra_kwargs)
        data = use_string_json_convert_func(response)
        already_processed += 1
        now_ticks = PROMPTS["process_tickers"][already_processed % len(PROMPTS["process_tickers"])]
        logger.debug(f"{now_ticks} Processed {already_processed} communities")
        return data

    levels = sorted(set([c["level"] for c in community_values]), reverse=True)
    logger.info(f"Generating by levels: {levels}")
    community_datas = {}
    for level in levels:
        this_level_community_keys, this_level_community_values = zip(
            *[
                (k, v)
                for k, v in zip(community_keys, community_values)
                if v["level"] == level
            ]
        )
        this_level_communities_reports = await asyncio.gather(
            *[
                _form_single_community_report(c, community_datas)
                for c in this_level_community_values
            ]
        )
        community_datas.update(
            {
                k: {
                    "report_string": _community_report_json_to_str(r),
                    "report_json": r,
                    **v,
                }
                for k, r, v in zip(
                    this_level_community_keys,
                    this_level_communities_reports,
                    this_level_community_values,
                )
            }
        )
    # Progress complete
    await community_report_kv.upsert(community_datas)


async def summarize_community(
    node_ids: List[str],
    graph: BaseGraphStorage,
    model_func: callable,
    max_tokens: int = 2048,
    to_json_func: callable = None,
    tokenizer_wrapper: TokenizerWrapper = None
) -> dict:
    """Summarize a single community of nodes.
    
    Args:
        node_ids: List of node IDs in the community
        graph: Graph storage to fetch node/edge data
        model_func: LLM function for summarization
        max_tokens: Maximum tokens for summary
        to_json_func: Function to convert response to JSON
        tokenizer_wrapper: Tokenizer for truncation
        
    Returns:
        Community report dictionary
    """
    if to_json_func is None:
        from ._utils import convert_response_to_json
        to_json_func = convert_response_to_json
    
    # Get nodes and edges for this community
    nodes_data = []
    edges_data = []
    
    for node_id in node_ids:
        node = await graph.get_node(node_id)
        if node:
            nodes_data.append(node)
            # Get edges from this node
            edges = await graph.get_node_edges(node_id)
            if edges:
                edges_data.extend(edges)
    
    # Build description
    description_parts = []
    
    # Add nodes
    if nodes_data:
        description_parts.append("Entities:")
        for node in nodes_data[:20]:  # Limit to prevent token overflow
            description_parts.append(f"- {node.get('name', node.get('id'))}: {node.get('description', '')[:200]}")
    
    # Add relationships
    if edges_data:
        description_parts.append("\nRelationships:")
        for edge in edges_data[:20]:  # Limit to prevent token overflow
            description_parts.append(
                f"- {edge.get('source')} -> {edge.get('target')}: {edge.get('relation', 'RELATED')}"
            )
    
    describe = "\n".join(description_parts)
    
    # Generate summary
    prompt = PROMPTS.get("community_report", "Summarize this community:\n{input_text}")
    response = await model_func(prompt.format(input_text=describe))
    
    # Try to parse as JSON, otherwise use as text
    try:
        report_data = to_json_func(response)
        # Check if parsing returned empty dict (failed parsing)
        if not report_data:
            raise ValueError("Empty JSON result")
    except:
        report_data = {
            "summary": response[:max_tokens],
            "entities": [n.get("name", n.get("id")) for n in nodes_data],
            "relationships": len(edges_data)
        }

    return report_data