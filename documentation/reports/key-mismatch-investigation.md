# Key Mismatch Investigation Report

## Executive Summary
Document retrieval fails after querying/ranking because of a critical mismatch in how entity names are stored and retrieved between the Graph storage and Vector DB (Qdrant). The graph stores entity names with their original quotes while Qdrant returns clean names without quotes, causing lookup failures.

## Problem Statement
After successfully implementing the 2nd sparse embedding and achieving good ranking results, the system fails at the document retrieval stage with the warning: "Some nodes are missing, maybe the storage is damaged."

## Investigation Findings

### 1. Storage Architecture

#### Graph Storage (NetworkX/Neo4j)
- **Node ID**: Uses entity name directly as the node identifier
- **Format**: Preserves original format including quotes
- **Example**: Node ID = `"EXECUTIVE ORDER 14196"` (with quotes)

#### Vector DB (Qdrant)
- **Point ID**: Uses hashed ID with `ent-` prefix
- **Entity Name Field**: Stores clean name without quotes
- **Example**:
  - ID: `ent-abc123def456...`
  - entity_name: `EXECUTIVE ORDER 14196` (no quotes)

### 2. Data Flow Analysis

#### During Extraction (`_extraction.py`)
```python
# Line 107: Extract entity name
entity_name = clean_str(record_attributes[1].upper())
# clean_str() removes HTML escapes but KEEPS quotes

# Line 189: Store in graph
await knowledge_graph_inst.upsert_node(entity_name, ...)
# Uses entity_name WITH quotes as node ID

# Lines 431-436: Store in vector DB
entity_name_clean = dp["entity_name"].strip('"').strip("'")
entity_id = compute_mdhash_id(entity_name_clean, prefix="ent-")
# Strips quotes before storing in VDB
```

#### During Community Generation (`graphrag.py`)
```python
# Lines 502-504: Update VDB with clean names
entity_name_clean = entity_name.strip('"').strip("'")
updates[entity_key] = {
    "entity_name": entity_name_clean,  # Clean name stored
    ...
}
```

#### During Query (`_query.py`)
```python
# Line 217: Query vector DB
results = await entities_vdb.query(query, top_k=...)
# Returns entities with clean names (no quotes)

# Line 237: Try to fetch from graph
node_datas = await knowledge_graph_inst.get_nodes_batch(
    [r["entity_name"] for r in results]
)
# FAILS: Looking for "EXECUTIVE ORDER 14196"
# but graph has node ""EXECUTIVE ORDER 14196""
```

### 3. Example Failure Scenario

1. **Extraction Phase**:
   - LLM returns: `"entity","EXECUTIVE ORDER 14196","LAW",...`
   - Graph stores node with ID: `"EXECUTIVE ORDER 14196"` (quotes included)

2. **Vector DB Storage**:
   - Strips quotes: `EXECUTIVE ORDER 14196`
   - Stores with ID: `ent-7f3a2b1c...`
   - Payload: `{"entity_name": "EXECUTIVE ORDER 14196"}`

3. **Query Phase**:
   - Qdrant returns: `{"entity_name": "EXECUTIVE ORDER 14196", "score": 0.95}`
   - Graph lookup for `EXECUTIVE ORDER 14196` fails
   - Node `"EXECUTIVE ORDER 14196"` exists but with quotes

4. **Result**: "Some nodes are missing" warning

## Solution Options

### Option 1: Strip Quotes During Graph Storage (Recommended)
**Modify `_extraction.py` line 189:**
```python
# Strip quotes before storing in graph
entity_name_for_graph = entity_name.strip('"').strip("'")
await knowledge_graph_inst.upsert_node(entity_name_for_graph, ...)
```
**Pros**:
- Consistent storage format across all systems
- Clean entity names everywhere
- No query-time fixes needed

**Cons**:
- Requires re-indexing existing data

### Option 2: Handle Both Formats During Query
**Modify `_query.py` lines 237-240:**
```python
# Try clean name first, then with quotes as fallback
clean_names = [r["entity_name"] for r in results]
node_datas = await knowledge_graph_inst.get_nodes_batch(clean_names)

# Fallback for missing nodes
missing_indices = [i for i, n in enumerate(node_datas) if n is None]
if missing_indices:
    quoted_names = [f'"{clean_names[i]}"' for i in missing_indices]
    fallback_nodes = await knowledge_graph_inst.get_nodes_batch(quoted_names)
    for i, node in zip(missing_indices, fallback_nodes):
        if node is not None:
            node_datas[i] = node
```
**Pros**:
- Works with existing data
- No re-indexing needed

**Cons**:
- Performance overhead (double lookups)
- Complexity in query code

### Option 3: Migrate Existing Graph Data
**One-time migration script:**
```python
# Update all node IDs to remove quotes
for old_id in graph.nodes():
    if old_id.startswith('"') and old_id.endswith('"'):
        new_id = old_id.strip('"')
        # Rename node
```
**Pros**:
- Fixes existing data
- Clean solution

**Cons**:
- Requires downtime
- Risk of data corruption

## Recommendation

Implement **Option 1** (strip quotes during graph storage) for new data and **Option 3** (migration) for existing data. This ensures:
1. Consistent data format going forward
2. No performance overhead during queries
3. Clean, maintainable code

## Implementation Priority

1. **Immediate**: Implement Option 1 to fix new extractions
2. **Short-term**: Add Option 2 as temporary fallback for existing data
3. **Long-term**: Execute Option 3 migration when convenient

## Testing Requirements

1. Verify entity extraction with various quote formats
2. Test query retrieval with entities containing quotes
3. Ensure backward compatibility with existing data
4. Performance testing with fallback logic

## Impact Assessment

- **Severity**: High - Breaks document retrieval
- **Scope**: All queries involving entities with quotes
- **User Impact**: Queries fail silently with missing context
- **Data Impact**: No data loss, only retrieval issues