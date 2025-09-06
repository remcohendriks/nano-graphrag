# NGRAF-009 Viability Assessment — TypedDict Schemas

## Summary
- Viable with minor adjustments. The codebase already defines a few TypedDicts (e.g., `TextChunkSchema`, `SingleCommunitySchema`, `CommunitySchema` in `nano_graphrag/base.py`), but nodes/edges and several function signatures still rely on untyped `dict`. Introducing a consolidated `schemas.py` and annotating key functions can be done without runtime changes. Care is needed to align field names with current structures and avoid duplicating existing schemas.

## Current State
- Existing TypedDicts:
  - `TextChunkSchema`, `SingleCommunitySchema`, `CommunitySchema` in `nano_graphrag/base.py`.
- Untyped/dynamic dict usage persists in:
  - `nano_graphrag/_extraction.py`: node/edge shapes (`entity_type`, `description`, `source_id`, weights, orders), extraction return payloads.
  - `nano_graphrag/_community.py`: community report payloads and context packing.
  - `nano_graphrag/_query.py`: context assembly for entities, relations, text units.
  - LLM messaging: provider paths accept `history` as `List[Dict[str, str]]` rather than a typed message.
- Storage interfaces (`BaseGraphStorage`, KV/Vector) return `dict` payloads with implicit shapes.

## Proposal Fit
- Ticket aligns with the codebase’s needs: adding a `schemas.py` with core TypedDicts and applying them to function signatures improves clarity and IDE support without changing runtime behavior.
- Adjustments recommended for fit:
  - Reuse and/or alias existing `TextChunkSchema`, `SingleCommunitySchema`, `CommunitySchema` instead of introducing parallel `ChunkSchema`/`CommunityReport` unless mapping is explicit.
  - Shape alignment: the ticket’s draft `NodeSchema` includes `id` and `entity_name`, while current storage returns node data without `id` and uses external node_id as the key. Prefer a NodeData schema reflecting current storage (`entity_type`, `description`, `source_id`, optional `name`) and a separate high‑level `NodeView` schema used in query contexts.
  - Mark rarely present fields as optional (`total=False`) to avoid typing friction and keep “no runtime change” contract.
  - LLM message schema (`LLMMessage`) is a good addition and fits provider interfaces.

## Impacted Areas (typing only, no behavior changes)
- Add `nano_graphrag/schemas.py` with TypedDicts for:
  - NodeData, EdgeData (storage shape); NodeView, EdgeView (query/context shape)
  - LLMMessage, EmbeddingResult (optional)
  - Consider `TypedDict(total=False)` for optional fields to match current payloads.
- Update type annotations in:
  - `_extraction.py` (extraction inputs/outputs and helpers)
  - `_query.py` (context assembly and returns)
  - `_community.py` (report structures used internally)
  - `llm/base.py` for typed `history` messages and return hints
  - Keep storage protocol types unchanged (ticket defers protocol changes).

## Backward Compatibility
- Safe: Purely additive type hints and new `schemas.py`. No runtime changes, no field renames.
- Existing tests and behavior remain intact.

## Risks & Mitigations
- Risk: Schema drift or mismatched field names (e.g., `id` vs node_id, `relation` vs `relationship`).
  - Mitigation: Mirror current field names exactly in TypedDicts used at each layer; introduce distinct “view” vs “storage” schema names when needed.
- Risk: Duplication with existing TypedDicts.
  - Mitigation: Import and reuse `TextChunkSchema`, `SingleCommunitySchema`, `CommunitySchema` instead of redefining; or alias new names to existing ones.
- Risk: Over‑strict typing causing annotation errors.
  - Mitigation: Use optional fields (`total=False`) and conservative, minimal required keys.

## Test Impact
- No behavior change; existing tests should pass unchanged.
- Optionally, add a mypy/pyright configuration and a “types” CI check in a follow‑up PR (not part of this ticket).

## Effort Estimate
- Small to medium (S/M): author `schemas.py`, annotate key function signatures, and ensure imports don’t create cycles. No refactors to calling code.

## Recommendation
- Proceed with NGRAF‑009, with the noted adjustments:
  - Avoid duplicating existing schemas; align field names with current payloads.
  - Use optional fields and clearly separate “storage data” vs “view/context” schemas.
  - Add `LLMMessage` and adopt in provider `history` typing.

