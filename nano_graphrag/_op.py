"""
DEPRECATED: This module is preserved for backward compatibility.
Please import from the specific modules instead:
- chunking: Text chunking operations
- extraction: Entity and relationship extraction
- community: Community detection and reports
- query: Query operations
"""

import warnings

# Show deprecation warning
warnings.warn(
    "Importing from _op.py is deprecated. "
    "Please import from specific modules: chunking, extraction, community, query",
    DeprecationWarning,
    stacklevel=2
)

# Import all functions from new modules for backward compatibility
from .chunking import (
    chunking_by_token_size,
    chunking_by_seperators,
    get_chunks,
    get_chunks_v2
)

from .extraction import (
    _handle_entity_relation_summary,
    _handle_single_entity_extraction,
    _handle_single_relationship_extraction,
    _merge_nodes_then_upsert,
    _merge_edges_then_upsert,
    extract_entities,
    extract_entities_from_chunks
)

from .community import (
    _pack_single_community_by_sub_communities,
    _pack_single_community_describe,
    _community_report_json_to_str,
    generate_community_report,
    summarize_community
)

from .query import (
    _find_most_related_community_from_entities,
    _find_most_related_text_unit_from_entities,
    _find_most_related_edges_from_entities,
    _build_local_query_context,
    _map_global_communities,
    local_query,
    global_query,
    naive_query
)