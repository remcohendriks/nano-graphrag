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
    """Pack sub-community reports into a CSV format for hierarchical summarization.

    When a community is too large, this function aggregates reports from its
    sub-communities instead of listing all individual nodes and edges. This
    enables hierarchical summarization where higher-level communities can
    leverage already-generated reports from lower levels.

    Args:
        community: The parent community containing sub-community references
        max_token_size: Maximum tokens allowed for the sub-community reports
        already_reports: Dictionary of previously generated community reports
        tokenizer_wrapper: Tokenizer for calculating token counts

    Returns:
        Tuple containing:
        - CSV-formatted sub-community reports
        - Token count of the generated report
        - Set of node IDs already covered by sub-communities
        - Set of edge tuples already covered by sub-communities
    """ 
    # Collect available sub-community reports
    all_sub_communities = [
        already_reports[k] for k in community["sub_communities"] if k in already_reports
    ]
    # Sort by importance (occurrence frequency)
    all_sub_communities = sorted(
        all_sub_communities, key=lambda x: x["occurrence"], reverse=True
    )
    
    # Truncate sub-communities list to fit token budget
    may_trun_all_sub_communities = truncate_list_by_token_size(
        all_sub_communities,
        key=lambda x: x["report_string"],
        max_token_size=max_token_size,
        tokenizer_wrapper=tokenizer_wrapper,
    )
    # Format sub-community reports as CSV
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
    # Track which nodes and edges are already covered by sub-communities
    # This prevents duplication in the parent community's description
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
    knowledge_graph_inst: BaseGraphStorage,
    community: SingleCommunitySchema,
    tokenizer_wrapper: TokenizerWrapper,
    max_token_size: int = 12000,
    already_reports: Optional[Dict[str, CommunitySchema]] = None,
    global_config: Optional[Dict[str, Any]] = None,
) -> str:
    """Pack a community's data into a structured text format for LLM summarization.

    This function creates a hierarchical description of a community by:
    1. Including sub-community reports (if available and needed)
    2. Listing important nodes with their properties
    3. Listing important edges with their relationships

    The function intelligently allocates token budget between these sections
    and handles large communities by leveraging sub-community summaries.

    Args:
        knowledge_graph_inst: Graph storage instance for fetching node/edge data
        community: Community to describe
        tokenizer_wrapper: Tokenizer for token counting and truncation
        max_token_size: Maximum tokens for the entire description
        already_reports: Previously generated reports for sub-communities
        global_config: Global configuration parameters

    Returns:
        Formatted string containing reports, entities, and relationships sections
    """
    # Fix mutable default arguments
    if already_reports is None:
        already_reports = {}
    if global_config is None:
        global_config = {}
    
    # Prepare raw data
    nodes_in_order = sorted(community["nodes"])
    edges_in_order = sorted(community["edges"], key=lambda x: x[0] + x[1])

    nodes_data = await asyncio.gather(
        *[knowledge_graph_inst.get_node(n) for n in nodes_in_order]
    )
    edges_data = await asyncio.gather(
        *[knowledge_graph_inst.get_edge(src, tgt) for src, tgt in edges_in_order]
    )


    # Define template and fixed overhead
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

    # Process sub-community reports
    report_describe = ""
    contain_nodes = set()
    contain_edges = set()

    # Heuristic: Consider community "large" if it has >100 nodes or edges
    # Large communities benefit from hierarchical summarization
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
        # Get sub-community reports and their contained nodes/edges
        result = _pack_single_community_by_sub_communities(
            community, remaining_budget, already_reports, tokenizer_wrapper
        )
        report_describe, report_size, contain_nodes, contain_edges = result
        remaining_budget = max(0, remaining_budget - report_size)

    # Prepare node and edge data (filtering those already in sub-communities)
    def format_row(row: list) -> str:
        """Format a data row for CSV output with proper escaping."""
        return ','.join('"{}"'.format(str(item).replace('"', '""')) for item in row)

    node_fields = ["id", "entity", "type", "description", "degree"]
    edge_fields = ["id", "source", "target", "description", "rank"]

    # Get degrees and create data structures
    node_degrees = await knowledge_graph_inst.node_degrees_batch(nodes_in_order)
    edge_degrees = await knowledge_graph_inst.edge_degrees_batch(edges_in_order)

    # Filter nodes/edges that already exist in sub-communities
    nodes_list_data = [
        [i, name, data.get("entity_type", "UNKNOWN"), 
         data.get("description", "UNKNOWN"), node_degrees[i]]
        for i, (name, data) in enumerate(zip(nodes_in_order, nodes_data))
        if name not in contain_nodes
    ]
    
    edges_list_data = [
        [i, edge[0], edge[1], data.get("description", "UNKNOWN") if data else "UNKNOWN", edge_degrees[i]]
        for i, (edge, data) in enumerate(zip(edges_in_order, edges_data))
        if (edge[0], edge[1]) not in contain_edges
    ]
    
    # Sort by importance (degree)
    nodes_list_data.sort(key=lambda x: x[-1], reverse=True)
    edges_list_data.sort(key=lambda x: x[-1], reverse=True)

    # Dynamically allocate token budget between nodes and edges
    # Calculate overhead from CSV headers
    header_tokens = len(tokenizer_wrapper.encode(
        list_of_list_to_csv([node_fields]) + "\n" + list_of_list_to_csv([edge_fields])
    ))

    data_budget = max(0, remaining_budget - header_tokens)
    total_items = len(nodes_list_data) + len(edges_list_data)
    # Allocate budget proportionally to the number of nodes vs edges
    node_ratio = len(nodes_list_data) / max(1, total_items)
    edge_ratio = 1 - node_ratio

    # Execute truncation based on allocated budget
    nodes_final = truncate_list_by_token_size(
        nodes_list_data, key=format_row, 
        max_token_size=int(data_budget * node_ratio), 
        tokenizer_wrapper=tokenizer_wrapper
    )
    edges_final = truncate_list_by_token_size(
        edges_list_data, key=format_row,
        max_token_size=int(data_budget * edge_ratio),
        tokenizer_wrapper=tokenizer_wrapper
    )

    # Assemble final output
    nodes_describe = list_of_list_to_csv([node_fields] + nodes_final)
    edges_describe = list_of_list_to_csv([edge_fields] + edges_final)

    final_output = final_template.format(
        reports=report_describe,
        entities=nodes_describe,
        relationships=edges_describe
    )

    return final_output


def _community_report_json_to_str(parsed_output: dict) -> str:
    """Convert community report JSON to formatted markdown string.

    Transforms the structured JSON output from LLM into a human-readable
    markdown format with title, summary, and detailed findings sections.

    Args:
        parsed_output: JSON dict with 'title', 'summary', and 'findings' keys

    Returns:
        Markdown-formatted report string

    Note:
        Based on Microsoft GraphRAG: index/graph/extractors/community_reports
    """
    title = parsed_output.get("title", "Report")
    summary = parsed_output.get("summary", "")
    findings = parsed_output.get("findings", [])

    def finding_summary(finding: dict):
        """Extract summary from a finding (handles both string and dict formats)."""
        if isinstance(finding, str):
            return finding
        return finding.get("summary")

    def finding_explanation(finding: dict):
        """Extract explanation from a finding (returns empty for string findings)."""
        if isinstance(finding, str):
            return ""
        return finding.get("explanation")

    report_sections = "\n\n".join(
        f"## {finding_summary(f)}\n\n{finding_explanation(f)}" for f in findings
    )
    return f"# {title}\n\n{summary}\n\n{report_sections}"


async def generate_community_report(
    community_report_kv: BaseKVStorage[CommunitySchema],
    knowledge_graph_inst: BaseGraphStorage,
    tokenizer_wrapper: TokenizerWrapper,
    global_config: Dict[str, Any],
) -> None:
    """Generate hierarchical community reports using LLM summarization.

    This function processes communities level by level (from lowest to highest),
    generating reports that can reference sub-community reports for hierarchical
    summarization. This approach enables efficient processing of large graphs
    by reusing lower-level summaries in higher-level reports.

    Args:
        community_report_kv: Key-value storage for persisting community reports
        knowledge_graph_inst: Graph storage containing community structure
        tokenizer_wrapper: Tokenizer for managing token budgets
        global_config: Configuration containing LLM functions and parameters

    Note:
        Processes communities from lowest level to highest to ensure
        sub-community reports are available when processing parent communities.
    """
    llm_extra_kwargs = global_config["special_community_report_llm_kwargs"]
    use_llm_func: callable = global_config["best_model_func"]
    use_string_json_convert_func: callable = global_config["convert_response_to_json_func"]

    communities_schema = await knowledge_graph_inst.community_schema()
    community_keys, community_values = list(communities_schema.keys()), list(communities_schema.values())
    already_processed = 0

    prompt_template = PROMPTS["community_report"]

    prompt_overhead = len(tokenizer_wrapper.encode(prompt_template.format(input_text="")))

    async def _form_single_community_report(
        community: SingleCommunitySchema, already_reports: Dict[str, CommunitySchema]
    ) -> Dict[str, Any]:
        """Generate a report for a single community using LLM."""
        nonlocal already_processed
        describe = await _pack_single_community_describe(
            knowledge_graph_inst,
            community,
            tokenizer_wrapper=tokenizer_wrapper, 
            max_token_size=global_config["best_model_max_token_size"] - prompt_overhead - 200,  # Extra tokens for chat template
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

    # Process communities level by level, starting from the lowest (most granular)
    # This ensures sub-community reports are available for parent communities
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
    # Persist all generated reports
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
        tokenizer_wrapper: Tokenizer for truncation (reserved for future use)

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