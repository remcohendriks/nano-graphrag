# NGRAF-020 Round 7 - Sparse Embedding Preservation Fix

## Issue Summary

**Finding PO-001**: The sparse embedding vectors were disappearing during community-generated entity re-upserts. While `sparse_name` persisted, the actual `sparse` vectors became empty, breaking hybrid search functionality.

## Root Cause

The content format was inconsistent between initial entity insertion and community re-upserts:

### Initial Entity Insertion (_extraction.py:405)
```python
"content": f"{entity_name_clean} {dp['description']}"  # Includes name + description
```

### Community Re-upsert (graphrag.py:539 - BEFORE FIX)
```python
"content": description  # Only description, missing entity name
```

This caused SPLADE to receive text without the entity name, generating weak or empty sparse vectors since entity names are often the most distinctive signal for sparse retrieval.

## Resolution

### Code Change

**File**: `nano_graphrag/graphrag.py`
**Line**: 539
**Change**: Include entity name in content field

```python
# After fix
"content": f"{entity_name_clean} {description}"  # Now matches initial format
```

This single-line change ensures consistency between initial insertion and community re-upserts.

## Validation

### Test Added
Added regression test in `tests/test_entity_embedding_preservation.py`:
- `test_community_reupsert_includes_entity_name_in_content()`
- Verifies content format consistency
- Ensures entity name is present for SPLADE

### Test Results
```bash
pytest tests/test_entity_embedding_preservation.py -q
# Result: 5 passed, 1 skipped

pytest tests/test__extraction.py -q
# Result: 5 passed
```

## Impact

### Before Fix
- SPLADE received: `"Presidential directive on sovereign wealth fund"`
- Generated weak/empty sparse vectors
- Hybrid search degraded after community generation

### After Fix
- SPLADE receives: `"EXECUTIVE_ORDER_14196 Presidential directive on sovereign wealth fund"`
- Generates proper sparse vectors with entity name signal
- Hybrid search maintains effectiveness throughout pipeline

## Technical Details

The fix leverages the already-extracted `entity_name_clean` variable (line 536), making this a minimal change with maximum impact. The format now matches exactly what's used during initial entity insertion, ensuring SPLADE receives consistent input throughout the GraphRAG pipeline.

## Conclusion

This regression was successfully fixed with a one-line change that restores sparse embedding functionality during community re-upserts. The fix ensures that both dense and sparse channels remain effective for hybrid search after community generation.