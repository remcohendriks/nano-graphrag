# NGRAF-022 Phase 2: Complete Batch Integration

## User Story
As a developer, I need to complete the batch transaction integration so that the system uses the proper `DocumentGraphBatch` infrastructure that was built but never connected, eliminating all remaining deadlock potential while maintaining performance.

## Background
Phase 1 (completed) removed `asyncio.gather` calls to stop immediate deadlocks. However, we discovered that `extract_entities()` in `_extraction.py` already implements proper batch processing with `DocumentGraphBatch`, but it's not being used because `graphrag.py` calls the legacy `_extract_entities_wrapper` instead.

## Current State
- ✅ `DocumentGraphBatch` class exists and works
- ✅ `execute_document_batch()` implemented for Neo4j and NetworkX
- ✅ `extract_entities()` in `_extraction.py` uses batch correctly (lines 421-458)
- ❌ `graphrag.py` uses legacy `_extract_entities_wrapper` with individual transactions
- ❌ Batch infrastructure never exercised in production

## Technical Implementation

### 1. Switch to Proper Function
**File**: `nano_graphrag/graphrag.py`

**Line 236**: Change function assignment
```python
# OLD (current):
self.entity_extraction_func = self._extract_entities_wrapper

# NEW:
from nano_graphrag._extraction import extract_entities
self.entity_extraction_func = extract_entities
```

### 2. Remove Legacy Wrapper
**Remove entire `_extract_entities_wrapper` method** (lines 238-330)
- No longer needed
- Contains problematic sequential calls (Phase 1 fix)
- Replaced by proper batch implementation

### 3. Adjust Function Signatures (if needed)
Ensure `extract_entities` signature matches expected interface:
- Parameters: chunks, graph_storage, entity_vdb, tokenizer_wrapper, global_config
- Return: Optional[BaseGraphStorage]

### 4. Verify Batch Execution Path
Confirm flow:
1. `extract_entities` accumulates nodes/edges in `DocumentGraphBatch`
2. Single call to `graph_storage.execute_document_batch(batch)`
3. Neo4j receives one transaction per document
4. No deadlocks possible with deterministic lock ordering

## Benefits
- **Performance**: Batch operations are faster than individual transactions
- **Reliability**: Single transaction eliminates deadlock potential
- **Architecture**: Uses infrastructure already built and tested
- **Maintainability**: Removes duplicate code and legacy wrapper

## Testing Plan

### Unit Tests
1. Verify `extract_entities` is called instead of wrapper
2. Confirm `execute_document_batch` receives complete batch
3. Test with multiple chunks containing overlapping entities

### Integration Tests
1. Process document with 50+ chunks
2. Verify no deadlocks with shared entities
3. Compare performance: batch vs sequential

### Regression Tests
1. All existing entity extraction tests must pass
2. Neo4j batch tests remain green
3. NetworkX compatibility maintained

## Definition of Done
- [ ] Legacy `_extract_entities_wrapper` removed
- [ ] `extract_entities` wired as `entity_extraction_func`
- [ ] All tests passing
- [ ] No Neo4j deadlocks in stress testing
- [ ] Performance metrics show improvement
- [ ] Documentation updated

## Notes
- This completes the work started in NGRAF-022
- The infrastructure was built correctly but never connected
- Phase 2 is primarily about removing old code and connecting to the new
- Expected LOC: +5, -100 (net reduction)

## Feature Branch
`feature/ngraf-022-batch-integration-phase2`

## PR Requirements
1. Title: "feat: Complete batch integration for Neo4j transactions (NGRAF-022 Phase 2)"
2. Description must reference original NGRAF-022 and Phase 1 work
3. Include performance comparison metrics
4. Highlight that this uses existing, tested infrastructure