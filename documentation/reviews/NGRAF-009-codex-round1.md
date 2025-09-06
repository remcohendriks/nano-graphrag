Debug reviewer ready.

# Abstract

NGRAF-009 adds a dedicated `schemas.py` with TypedDicts and adopts those types across extraction, query, community, and LLM base history without changing behavior. Overall, the implementation adheres to the ticket: types are additive, optional fields mirror current payloads, and storage interfaces remain untouched. I found no functional regressions. I call out a few typing nits (e.g., EdgeData’s relationship field lives only in EdgeView), minor consistency issues (use GRAPH_FIELD_SEP in helpers), and a couple of places where using the new types could go further (return annotations for a few helpers; tighten `EntityExtractionResult` element types). Nothing blocks merge.

# Critical Issues (must fix before merge)

- None found. Changes are type-only; runtime logic remains the same. Tests pass and imports are clean.

# High Priority Issues (should fix soon)

- schemas.py: Align separator helpers with runtime constant
  - File: `nano_graphrag/schemas.py`, lines ~214–243 (parse_source_id/build_source_id)
  - Issue: Default separator is a hardcoded string `"<SEP>"`. The runtime constant is `GRAPH_FIELD_SEP` from `nano_graphrag/prompt.py`.
  - Risk: Silent drift if the delimiter changes in PROMPTS.
  - Fix: Import `GRAPH_FIELD_SEP` and set it as the default; keep parameter override intact.
    ```python
    from .prompt import GRAPH_FIELD_SEP
    def parse_source_id(source_id: str, separator: str = GRAPH_FIELD_SEP) -> List[str]:
        ...
    def build_source_id(chunk_ids: List[str], separator: str = GRAPH_FIELD_SEP) -> str:
        ...
    ```

- schemas.EntityExtractionResult: Loosened types obscure value
  - File: `nano_graphrag/schemas.py`, lines ~59–72
  - Issue: `entities: List[Dict[str, Any]]` and `relationships: List[Dict[str, Any]]` are typed as “any dict”, while the code produces NodeData/EdgeData-like shapes.
  - Suggestion: Use `List[NodeData]` and `List[EdgeData]` (or `List[NodeData | Dict[str, Any]]` if transitional). This improves IDE affordances without enforcing runtime change.

# Medium Priority Suggestions (improvements)

- llm/base history typing
  - File: `nano_graphrag/llm/base.py`, history param switched to `List[LLMMessage]` at lines ~115, 147, 188, 217. Good change.
  - Follow-up: Adjust provider docstrings or type aliases where needed to avoid ambiguity in consumers sending legacy `Dict[str,str]` messages. Optionally add a TypeGuard adapter (legacy dict -> LLMMessage) in a future PR.

- schemas.EdgeView consistency
  - File: `nano_graphrag/schemas.py`, lines ~38–60
  - Note: `relationship` exists in EdgeView but not in EdgeData (storage has `description` and `weight`). This mirrors current code, but consider a comment clarifying that EdgeData does not include a typed “relationship” string and that relationship text is carried in `description`.

- Introduce aliases for existing TypedDicts
  - The code reuses `TextChunkSchema`, `CommunitySchema` indirectly in contexts but uses `Dict[str, Any]` in `QueryContext` for `chunks` and `communities`.
  - Suggestion: Import and reference existing `TextChunkSchema`, `CommunitySchema` in QueryContext to gain stronger typing with zero behavior change.

- Add return annotations where added in signatures
  - A few internal helpers could benefit from explicit return types for consistency:
    - `_extraction._process_single_content` already updated to return a Tuple[...]; good. Ensure surrounding helpers like `_handle_single_*` and merge helpers consistently return Optional[...] or concrete dict types (NodeData/EdgeData) where appropriate. You’ve done this for the major ones; minor helpers could also be annotated.

- TypeGuard validators accept “any dict”
  - Files: `schemas.is_valid_node_data`, `schemas.is_valid_edge_data`
  - Current behavior: returns True for any dict; this is fine for now but slightly misleading. Consider minimally assert presence of at least one expected key (e.g., entity_type for NodeData) without breaking current flows. Not a blocker.

# Low Priority Notes (nice to have)

- tests/test_schemas.py: Great coverage. Consider adding one test that composes typed QueryContext with NodeView/EdgeView instances built from NodeData/EdgeData (ensures end-to-end shape sanity).
- Minor: `BedrockMessage` shape relies on `List[Dict[str,str]]`. If we formalize this later, a dedicated TypedDict for the content item (`{"text": str}`) would help.
- Consider re-exporting existing base.TypedDicts from schemas.py for a single import surface (you’ve done this partially via __all__, but explicit imports would make it clearer).

# Positive Observations (well done)

- Adheres to “no runtime change”: All changes are additive type hints; storage protocols not altered.
- Good separation between storage schemas (NodeData/EdgeData) and view schemas (NodeView/EdgeView) reflecting real data lifecycles.
- `LLMMessage` adoption in BaseLLMProvider removes ambiguity in history shape; nice incremental improvement.
- Optional (`total=False`) fields minimize friction while still improving developer experience.
- Utilities for `source_id` parsing/building help centralize separators and reduce scattered string ops.
- Tests are thorough (25 cases), including TypeGuard and utility function behavior.

# Conclusion

Solid implementation that materially improves type clarity without touching behavior. No blockers to merge. I recommend the small follow-ups: use `GRAPH_FIELD_SEP` in schema helpers, tighten `EntityExtractionResult` to NodeData/EdgeData lists, and consider pointing QueryContext’s `chunks`/`communities` to existing TypedDicts. These are straightforward and will further increase the benefits of this PR without changing runtime behavior.
