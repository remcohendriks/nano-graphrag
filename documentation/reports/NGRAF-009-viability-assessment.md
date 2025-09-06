# NGRAF-009 Viability Assessment: TypedDict Schemas

## Abstract

NGRAF-009 proposes introducing comprehensive TypedDict schemas for core data structures to improve type safety and IDE support. This assessment finds the ticket **HIGHLY VIABLE** with strategic importance for codebase maintainability. The current codebase already uses TypedDict minimally (TextChunkSchema, CommunitySchema) but lacks systematic typing for nodes, edges, and other core structures. Implementation would significantly improve developer experience and reduce runtime errors.

## Current State Analysis

### Existing TypedDict Usage
The codebase currently has limited TypedDict adoption:

1. **nano_graphrag/base.py**:
   - `TextChunkSchema` - defines chunk structure
   - `SingleCommunitySchema` and `CommunitySchema` - community data
   - Missing: Node, Edge, Query result schemas

2. **nano_graphrag/llm/base.py**:
   - `CompletionParams`, `StreamChunk`, `CompletionResponse` - LLM interfaces
   - Well-structured vendor-neutral types

### Critical Gaps Identified

1. **Node/Edge Structure Ambiguity**:
   - Storage interfaces use `dict[str, str]` or `tuple[str, dict]`
   - `upsert_nodes_batch` takes `list[tuple[str, dict[str, str]]]`
   - No clear contract for required vs optional fields
   - Inconsistent field naming across modules

2. **Extraction Output Uncertainty**:
   - `extract_entities` returns untyped dicts
   - Entity deduplication logic assumes fields without validation
   - Relationship extraction has no type contract

3. **Storage Interface Weakness**:
   - Methods return `Union[dict, None]` without structure
   - No compile-time validation of data shapes
   - Easy to introduce KeyErrors

## Viability Assessment

### HIGH VIABILITY ✅

**Reasons for High Viability:**

1. **Minimal Breaking Changes**: TypedDict is structural typing - existing dict code remains compatible
2. **Incremental Adoption**: Can add types gradually without refactoring
3. **Immediate Developer Benefits**: IDE autocomplete, type checking
4. **Runtime Validation Ready**: TypeGuard functions provide optional runtime checks
5. **Documentation Value**: Self-documenting data contracts

### Implementation Complexity: MEDIUM

**Complexity Factors:**
- Need to audit all data flows to capture actual structure
- Storage interfaces use varied patterns (tuples, dicts)
- Must maintain backward compatibility
- Some fields are dynamically added

### Risk Assessment: LOW

**Risk Mitigation:**
- TypedDict allows gradual typing
- `total=False` for optional fields
- Runtime validation is opt-in
- No changes to actual data flow

## Strategic Importance

### Architecture Benefits

1. **Clear Data Contracts**: Explicit interfaces between modules
2. **Refactoring Safety**: Type checker catches breaking changes
3. **Onboarding Efficiency**: New developers understand data shapes immediately
4. **Bug Prevention**: Eliminates typo-based KeyErrors

### Technical Debt Reduction

Current code has implicit assumptions about data structure:
```python
# Current - unclear what fields exist
node = storage.get_node(node_id)
if node and node.get("entity_type"):  # Hope these fields exist
    ...

# With TypedDict - explicit contract
node: Optional[NodeSchema] = storage.get_node(node_id)
if node and node["entity_type"]:  # IDE knows fields
    ...
```

## Implementation Recommendations

### Phase 1: Core Schemas (This Ticket)
1. Create `schemas.py` with essential TypedDicts
2. Add type annotations to high-traffic functions
3. Provide TypeGuard validators for critical paths
4. Update extraction and query modules

### Phase 2: Storage Alignment (Future)
1. Update storage protocols with typed returns
2. Migrate from tuples to TypedDict in storage
3. Add runtime validation at storage boundaries

### Phase 3: Full Coverage (Future)
1. Type all function signatures
2. Enable strict type checking in CI
3. Remove all `dict` annotations

## Compatibility Considerations

### With Recent Changes

**NGRAF-006 (Module Decomposition)**: 
- Clean module structure makes typing easier
- Each module can have focused schemas

**NGRAF-007 (Config Normalization)**:
- Config already uses dataclasses, complementary approach
- Could add ConfigDict types for dict representations

**NGRAF-008 (Legacy Cleanup)**:
- Deprecation established, good time to improve types
- New provider interface already uses TypedDict

### Storage Pattern Challenge

Current storage uses tuples:
```python
async def upsert_nodes_batch(self, nodes_data: list[tuple[str, dict[str, str]]])
```

Recommendation: Keep tuple interface but document dict structure:
```python
NodeData = TypedDict("NodeData", {
    "entity_name": str,
    "entity_type": Optional[str],
    "description": Optional[str]
})

async def upsert_nodes_batch(
    self, 
    nodes_data: list[tuple[str, NodeData]]  # ID, data pairs
)
```

## Critical Success Factors

1. **Accurate Schema Definition**: Must reflect actual runtime data
2. **Backward Compatibility**: No breaking changes to existing code
3. **Developer Buy-in**: Team must use types consistently
4. **Gradual Rollout**: Start with core modules, expand systematically

## Potential Challenges

1. **Dynamic Fields**: Some structures have runtime-determined fields
   - Solution: Use `Dict[str, Any]` for metadata fields

2. **Legacy Patterns**: Tuple-based storage interfaces
   - Solution: Type the dict portion, keep tuple structure

3. **Optional Fields**: Many fields are conditionally present
   - Solution: Use `total=False` or `Optional[T]`

## Recommendation

**IMPLEMENT WITH HIGH PRIORITY**

This ticket provides foundational improvements that will:
- Reduce bugs immediately
- Improve developer productivity
- Enable safer refactoring
- Provide living documentation

The implementation is low-risk with high reward. The gradual typing approach means no disruption to existing code while gaining immediate benefits.

## Proposed Modifications to Ticket

1. **Clarify Storage Tuple Pattern**: Document that tuple interfaces remain unchanged
2. **Add Migration Examples**: Show before/after for common patterns
3. **Define Validation Strategy**: When to use runtime TypeGuard vs static only
4. **Specify Required Fields**: Clearly mark which fields are always present
5. **Include Serialization Helpers**: For JSON/dict conversion

## Conclusion

NGRAF-009 is highly viable and should be prioritized. The codebase is ready for systematic typing, with minimal existing TypedDict usage that can be expanded. The benefits far outweigh the implementation effort, and the gradual adoption path ensures no disruption.

---
*Architect Assessment Completed: 2025-01-06*  
*Recommendation: Proceed with implementation*