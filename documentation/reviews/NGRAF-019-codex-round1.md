# NGRAF-019 — Round 1 Review (expert-codex)

## Scope & Diff Summary

- Change category: New Feature (query-time use of typed relations + type-aware embeddings)
- Branch: feature/ngraf-019-typed-relation-query-improvements
- Commits reviewed: e361192 (feature), 2431b8c (style), 189b79e (report)
- Changed files (since merge-base with origin/main):
  - M `nano_graphrag/_query.py` (add relation_type to CSV; direction logic)
  - M `nano_graphrag/_community.py` (add relation_type/weight to community relationships)
  - M `nano_graphrag/graphrag.py` (type-prefix entity embeddings; env toggle)
  - M `nano_graphrag/prompt.py` (update local prompt + example)
  - A `tests/test_typed_query_improvements.py` (coverage for typed relations & embeddings)
  - A `documentation/reports/NGRAF-019-round1-implementation.md`

## Critical Issues

- CODEX-019-001: nano_graphrag/_community.py + storage community_schema | High | Directionality lost in community reports
  - Evidence:
    - NetworkX community_schema populates edges with `tuple(sorted(e))` (gdb_networkx.py: around lines 180–200) so direction is discarded.
    - Neo4j community_schema also sorts: `tuple(sorted([node_id, str(connected)]))` (gdb_neo4j.py: ~690–710).
    - `_pack_single_community_describe` then emits `edge[0]` → `edge[1]` (sorted order) as source/target (nano_graphrag/_community.py: 199–236), yielding potential inversions (e.g., B SUPERSEDES A).
  - Impact: Community report contexts can invert semantics for directional relation types, contradicting ACs and confusing the LLM.
  - Recommendation: Preserve extraction-time source→target for community edges:
    - Do not sort edges when constructing community_schema; or
    - Record stored direction in edge attributes (e.g., src_id/tgt_id) and reconstruct source/target for report emission; or
    - For Neo4j, query `MATCH (s)-[r:RELATED]->(t)` to produce directed pairs for the community edges set.

- CODEX-019-002: nano_graphrag/_query.py:141–176 | High | Direction derived from adjacency, not extraction
  - Evidence: Dedup uses `sorted_edge` for `seen` but appends `e` (adjacency order) to `all_edges`. When `relation_type` is present, `src_tgt = edge` (adjacency order), not necessarily the original extracted source→target.
  - Impact: For typed edges where only the target entity appears in the initial top-k entity set, the preserved direction can be inverted (e.g., if node_datas contains B, edge will be (B, A) even if extraction was A→B).
  - Recommendation: Reconstruct direction using stored orientation instead of adjacency:
    - Store `src`/`tgt` on edge_data at upsert; or
    - For Neo4j, rely on `get_edges_batch` with directed pairs and prefer stored direction; for NetworkX, read stored src/tgt fields.
    - As a minimal mitigation, prefer the directed pair returned from a storage method that can guarantee direction when `relation_type` is present.

## High Priority

- CODEX-019-003: nano_graphrag/prompt.py | Medium | Global prompts not updated
  - Evidence: Local prompt includes a note about `relation_type` and direction; no equivalent guidance observed for global mapping/reduction.
  - Impact: Inconsistent LLM behavior between local/global queries; global may underutilize relation_type.
  - Recommendation: Add concise notes to global prompts explaining the relation_type column and direction semantics if relationships are surfaced there, or explicitly state that relation types currently inform only local contexts.

## Medium Priority

- CODEX-019-004: Truncation policy does not shorten description first
  - Evidence: `_build_local_query_context` truncates by dropping rows based on `description` size; `_community` truncation uses entire row length via `format_row`.
  - Impact: Under tight token budgets, high-signal rows may be dropped instead of shortening descriptions while retaining `relation_type` and direction.
  - Recommendation: When near budget, shorten descriptions preferentially before dropping rows, ensuring `relation_type` and source→target are preserved.

- CODEX-019-005: Env flag for embeddings instead of config
  - Evidence: `ENABLE_TYPE_PREFIX_EMBEDDINGS` gating in `graphrag.py` (lines ~312–330).
  - Impact: Configuration becomes split between env and config objects; harder to audit in code.
  - Recommendation: Mirror this flag in `GraphRAGConfig` for programmatic control, keeping env as an override.

## Low Priority

- CODEX-019-006: Test coverage misses full community report pipeline
  - Evidence: Tests hit `_pack_single_community_describe` directly; they do not validate `generate_community_report` with storage-provided `community_schema` (which currently sorts edges).
  - Impact: Direction inversion risk in end-to-end community report generation remains untested.
  - Recommendation: Add an end-to-end test invoking `generate_community_report` to ensure direction is preserved in emitted reports for both backends.

## Positive Observations

- CODEX-GOOD-019-001: Query CSV enrichment
  - relation_type column added with sensible default; direction preservation attempt demonstrates attention to semantics.
- CODEX-GOOD-019-002: Prompt clarity
  - Local prompt and examples updated to explain the new relation_type semantics and directionality.
- CODEX-GOOD-019-003: Type-aware embeddings with feature flag
  - Clean, minimal toggle via env; default-on to realize benefits while allowing opt-out.
- CODEX-GOOD-019-004: Tests target key risks
  - Directionality unit tests for query contexts, fallbacks, and token budget handling reflect deliberate coverage.

## Additional Notes

- Performance: Changes are lightweight (string ops, small list manipulations). Token budget increase is controlled; keep an eye on worst-case contexts.
- Security: No new injection risk surfaced. Neo4j relationship property handling continues to sanitize.
- Backward compatibility: Defaults (RELATED) and opt-out embedding flag are sound; document behavioral changes in release notes.

## Conclusion

Good progress toward making typed relationships and entity types actionable at query time. The remaining blocker is directionality in community reports (and, more subtly, adjacency-based direction in query edges), which can invert semantics for critical relation types. Address these with storage-aware direction preservation and add an end-to-end test for community report generation.

Once directionality is robust across both query and reporting paths, this feature will meet the intent of NGRAF-019 without architectural churn.

*** End of Round 1 Review ***

