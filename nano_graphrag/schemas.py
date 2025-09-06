"""TypedDict schemas for core data structures in nano-graphrag.

This module defines type-safe schemas for nodes, edges, chunks, communities,
and other core data structures used throughout the system.

Architecture:
- Storage Layer: NodeData/EdgeData - raw database records without IDs
  (IDs are keys in storage, not fields in the data)
- View Layer: NodeView/EdgeView - enriched with IDs and parsed fields
- Transformation: Storage -> View happens at query boundaries
Note: entity_name is the node ID (key), not a field in NodeData
"""

from typing import TypedDict, Optional, List, Dict, Any, Literal, TypeGuard, Union
import numpy as np
from .prompt import GRAPH_FIELD_SEP


# Storage layer schemas - reflect actual database structure

class NodeData(TypedDict, total=False):
    """Node data as stored in graph storage.
    
    Fields match current storage implementation:
    - entity_type: Type/category of the entity
    - description: Textual description
    - source_id: Reference to source chunks (GRAPH_FIELD_SEP joined)
    """
    entity_type: str
    description: str
    source_id: str


class EdgeData(TypedDict, total=False):
    """Edge data as stored in graph storage.
    
    Fields match current storage implementation:
    - weight: Relationship strength/importance
    - description: Textual description
    - source_id: Reference to source chunks
    - order: Ordering for multiple edges
    """
    weight: float
    description: str
    source_id: str
    order: int


# View layer schemas - used in queries and context

class NodeView(TypedDict):
    """Node representation in query context.
    
    Includes node ID and all storage fields for complete context.
    """
    id: str
    entity_type: Optional[str]
    description: Optional[str]
    source_chunks: List[str]  # Parsed from source_id


class EdgeView(TypedDict):
    """Edge representation in query context.
    
    Complete edge information for query processing.
    """
    source: str  # Source node ID
    target: str  # Target node ID
    relationship: str
    weight: float
    description: Optional[str]
    source_chunks: List[str]  # Parsed from source_id


# Extraction schemas

class EntityExtractionResult(TypedDict):
    """Result from entity extraction process."""
    entities: List[Union[NodeData, Dict[str, Any]]]  # NodeData-compatible dicts
    relationships: List[Union[EdgeData, Dict[str, Any]]]  # EdgeData-compatible dicts
    chunk_id: str


class ExtractionRecord(TypedDict, total=False):
    """Single extraction record from LLM."""
    entity_name: str
    entity_type: str
    description: str
    importance_score: float


class RelationshipRecord(TypedDict, total=False):
    """Single relationship record from LLM."""
    source_entity: str
    target_entity: str
    relationship_description: str
    weight: float
    order: int


# Query schemas

class QueryContext(TypedDict):
    """Context assembled for query execution."""
    query: str
    entities: List[NodeView]
    relationships: List[EdgeView]
    chunks: List[Dict[str, Any]]  # TextChunkSchema from base.py
    communities: List[Dict[str, Any]]  # CommunitySchema from base.py


class LocalQueryContext(TypedDict, total=False):
    """Context specific to local queries."""
    query: str
    entities: str  # Formatted entity context
    relationships: str  # Formatted relationship context  
    chunks: str  # Formatted chunk context
    community_reports: str  # Formatted community reports


class GlobalQueryContext(TypedDict, total=False):
    """Context specific to global queries."""
    query: str
    community_reports: str  # Formatted community reports
    response_type: str


# LLM communication schemas

class LLMMessage(TypedDict):
    """Standard LLM message format.
    
    Used across all LLM providers for consistent messaging.
    """
    role: Literal["system", "user", "assistant"]
    content: str


class BedrockMessage(TypedDict):
    """Amazon Bedrock specific message format."""
    role: Literal["user", "assistant"]
    content: List[Dict[str, str]]  # [{"text": "..."}]


# Embedding schemas

class EmbeddingResult(TypedDict):
    """Result from embedding operation."""
    embeddings: np.ndarray
    model: str
    dimensions: int
    usage: Optional[Dict[str, int]]


class EmbeddingResponse(TypedDict):
    """Response from embedding provider."""
    embeddings: np.ndarray
    dimensions: int
    model: str
    usage: Dict[str, int]


# Community schemas (extend existing ones)

class CommunityNodeInfo(TypedDict):
    """Node information within a community."""
    entity: str
    type: Optional[str]
    description: Optional[str]
    rank: float


class CommunityEdgeInfo(TypedDict):
    """Edge information within a community."""
    source: str
    target: str
    relationship: str
    weight: float


class CommunityReportData(TypedDict, total=False):
    """Parsed community report data."""
    title: str
    summary: str
    rating: float
    importance: float
    findings: List[str]


# Runtime validation helpers

def is_valid_node_data(data: Dict[str, Any]) -> TypeGuard[NodeData]:
    """Validate that dict conforms to NodeData schema.
    
    Checks that data is a dict with only allowed NodeData fields.
    """
    if not isinstance(data, dict):
        return False
    # Check that all keys are valid NodeData fields
    allowed_fields = {"entity_type", "description", "source_id"}
    return all(key in allowed_fields for key in data.keys())


def is_valid_edge_data(data: Dict[str, Any]) -> TypeGuard[EdgeData]:
    """Validate that dict conforms to EdgeData schema.
    
    Checks that data is a dict with only allowed EdgeData fields.
    """
    if not isinstance(data, dict):
        return False
    # Check that all keys are valid EdgeData fields
    allowed_fields = {"weight", "description", "source_id", "order"}
    return all(key in allowed_fields for key in data.keys())


def is_valid_llm_message(msg: Dict[str, Any]) -> TypeGuard[LLMMessage]:
    """Validate that dict conforms to LLMMessage schema."""
    if not isinstance(msg, dict):
        return False
    
    if "role" not in msg or "content" not in msg:
        return False
    
    if msg["role"] not in ["system", "user", "assistant"]:
        return False
    
    return isinstance(msg["content"], str)


def validate_extraction_record(record: Dict[str, Any]) -> ExtractionRecord:
    """Validate and coerce extraction record.
    
    Ensures required fields are present and typed correctly.
    """
    if not isinstance(record.get("entity_name"), str):
        raise ValueError(f"Invalid entity_name in record: {record}")
    
    return ExtractionRecord(
        entity_name=record["entity_name"],
        entity_type=record.get("entity_type", ""),
        description=record.get("description", ""),
        importance_score=float(record.get("importance_score", 0.0))
    )


def validate_relationship_record(record: Dict[str, Any]) -> RelationshipRecord:
    """Validate and coerce relationship record.
    
    Ensures required fields are present and typed correctly.
    """
    if not isinstance(record.get("source_entity"), str):
        raise ValueError(f"Invalid source_entity in record: {record}")
    if not isinstance(record.get("target_entity"), str):
        raise ValueError(f"Invalid target_entity in record: {record}")
    
    return RelationshipRecord(
        source_entity=record["source_entity"],
        target_entity=record["target_entity"],
        relationship_description=record.get("relationship_description", ""),
        weight=float(record.get("weight", 1.0)),
        order=int(record.get("order", 0))
    )


def parse_source_id(source_id: str, separator: str = None) -> List[str]:
    """Parse source_id field into list of chunk IDs.
    
    Args:
        source_id: Concatenated source IDs
        separator: Field separator (default: GRAPH_FIELD_SEP from prompt.py)
    
    Returns:
        List of individual chunk IDs
    """
    if separator is None:
        separator = GRAPH_FIELD_SEP
    if not source_id:
        return []
    return source_id.split(separator)


def build_source_id(chunk_ids: List[str], separator: str = None) -> str:
    """Build source_id field from list of chunk IDs.
    
    Args:
        chunk_ids: List of chunk IDs
        separator: Field separator (default: GRAPH_FIELD_SEP from prompt.py)
    
    Returns:
        Concatenated source ID string
    """
    if separator is None:
        separator = GRAPH_FIELD_SEP
    return separator.join(chunk_ids)


# Re-export schemas from base.py to have single import point
# These will be imported when schemas.py is used
__all__ = [
    # Storage schemas
    "NodeData",
    "EdgeData",
    # View schemas
    "NodeView", 
    "EdgeView",
    # Extraction schemas
    "EntityExtractionResult",
    "ExtractionRecord",
    "RelationshipRecord",
    # Query schemas
    "QueryContext",
    "LocalQueryContext",
    "GlobalQueryContext",
    # LLM schemas
    "LLMMessage",
    "BedrockMessage",
    # Embedding schemas
    "EmbeddingResult",
    "EmbeddingResponse",
    # Community schemas
    "CommunityNodeInfo",
    "CommunityEdgeInfo", 
    "CommunityReportData",
    # Validators
    "is_valid_node_data",
    "is_valid_edge_data",
    "is_valid_llm_message",
    "validate_extraction_record",
    "validate_relationship_record",
    # Utilities
    "parse_source_id",
    "build_source_id",
]