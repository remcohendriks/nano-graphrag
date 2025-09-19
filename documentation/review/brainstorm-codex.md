# nano-graphrag — Extending Graph Logic with Domain-Specific Entity Types

Author: Codex CLI

Date: 2025-09-19

## Context

This review analyzes the developer deep dive on extending nano-graphrag with domain-specific entity types (example: U.S. Executive Orders) and cross-references the original GraphRAG paper to assess practicality, feasibility, impact, and usefulness.

Inputs considered:

- documentation/other/brainstorm-dev.md
- documentation/other/graphrag.md
- Current codebase (notably `nano_graphrag/entity_extraction/*`, `nano_graphrag/graphrag.py`, `nano_graphrag/prompt.py`, `nano_graphrag/base.py`)

Key current capabilities observed in code:

- Two extraction strategies already exist and are selectable via factory:
  - LLM prompt-based: `LLMEntityExtractor`
  - DSPy-based with self-refine option: `DSPyEntityExtractor`
- Entity types for LLM extraction are injected at runtime into the prompt from extractor config, though `GraphRAG._init_extractor` currently hardcodes a default set.
- Graph nodes store `entity_type`, `description`, `source_id`. Edges store `description`, `weight`, and optional `order` (from DSPy). There is no explicit `relation_type` field yet.
- Community summarization and global QA follow the GraphRAG approach of building summaries from graph elements, then answering queries from these summaries.

## Proposal Summary (from dev deep dive)

- Problem: Generic extraction loses important domain semantics (e.g., legal relationships like “supersedes”, “amends”, “implements”).
- Four strategy options:
  1) Configuration-based extension (simple new types and patterns)
  2) Custom extractor implementation (deterministic patterns per-domain)
  3) Hybrid prompt engineering (LLM-led with domain-specific guidance)
  4) Schema-driven architecture (typed entities, properties, validators, relation schemas)
- Phased plan: Quick config → Semantic enrichment → Schema foundation → Domain specialization.

## Opinion — Practicality

- Pragmatic path exists today with minimal changes.
  - The code already supports multiple extraction strategies and allows passing entity types to the LLM extractor. The primary gap is that `GraphRAG._init_extractor` hardcodes the default list instead of reading types from configuration. Fixing this is low-effort and unlocks user-configurable types.
  - Per-domain prompts can be added without structural changes: `prompt.py` can host variants, selected based on a new “extraction profile” in config.
- Typed relationships require a small surface change to be truly practical.
  - Edges currently store text `description` and numeric `weight` (plus `order`). Adding an optional `relation_type` string preserves backward compatibility but enables typed reasoning and more precise community summaries. This change is localized to graph storage and extraction post-processing and is therefore practical.
- Schema-driven architecture is powerful but heavy.
  - Introducing Pydantic/typed schemas for entities/relations plus validators will deliver strong guarantees, but it touches multiple subsystems (extraction, graph storage, summarization, query) and needs migration/versioning. Practical only with incremental rollout and feature flags.

## Opinion — Feasibility

Short-term (1–2 weeks): Highly feasible

- Add `entity_types` to `EntityExtractionConfig` and thread it through `GraphRAG._init_extractor` to the factory. Deprecate internal hardcoded list. Keep a sensible default.
- Introduce "extraction profiles" in config (e.g., `domain: "legal"`, `profile: "executive_orders"`) to switch prompts and post-processing.
- Add a post-processor that maps relationship descriptions to a small controlled vocabulary when obvious (e.g., regex/keyword rules for “supersedes”, “amends”, “implements”, “revokes”). Store mapped type as `relation_type` alongside the original `description`.
- Keep both LLM and DSPy strategies operational; profiles and post-processing should be strategy-agnostic.

Mid-term (1–2 months): Moderately feasible

- Expand prompts per-domain and property extraction (e.g., EO number, date, president). Introduce light validators that run post-extraction (e.g., EO numbers are 5 digits; dates parse; relation targets exist in graph).
- Extend community summarization to optionally prioritize/aggregate by `relation_type` (e.g., produce a “revocation chain” section). This is a straight enhancement to the summarization inputs, not a rewrite.
- Add metrics and tests: extraction precision/recall on a labeled slice; summarize token costs; validate impact on global answer quality.

Long-term (quarter+): Feasible with guardrails

- Move toward a schema-first model with `EntityTypeSchema`, `RelationSchema`, validators, and versioning. Begin by implementing schemas only for types covered by a profile (e.g., `EXECUTIVE_ORDER`, `STATUTE`) while the default path remains schema-light.
- Migrations: keep old data compatible (relation_type default to `RELATED`), and add a background enrichment job for existing edges to infer `relation_type`.

## Opinion — Impact

User value

- High for domains with dense, typed relationships (legal, medical, financial). Users can ask precise questions (e.g., “Which EOs supersede 13800 and what statutory authority do they implement?”) and get grounded answers across the corpus.

System quality

- Typed relations enable more precise community-level narratives and reduce “lossy” summarization of relationship semantics. They also help with deduplication and graph cleanup by distinguishing relation categories.

Performance and cost

- Prompt enrichment increases tokens moderately; post-processing and validation add minimal runtime cost. DSPy can lower LLM calls in stable domains; LLM route remains best for capturing implicit relationships.

Maintainability

- Profiles isolate domain-specific logic and prevent “prompt sprawl.” Optional `relation_type`—rather than enforcing schemas everywhere—keeps maintenance ergonomic while opening a path to stricter models where needed.

## Opinion — Usefulness

- Executive Orders are a strong pilot domain: well-structured identifiers, small relation vocabulary, and clear utility in queries. Success here generalizes to other regulated domains (e.g., pharmacovigilance, compliance reports, corporate filings).
- Typing relations meaningfully upgrades GraphRAG’s global answers: communities and rollups can organize by relation semantics (“revocations timeline”, “implementation chains”) rather than generic relatedness.

## Gaps and Suggested Low-Effort Changes

1) Configurable entity types end-to-end

- Add `entity_types: List[str]` to `EntityExtractionConfig` with defaults matching current behavior.
- In `GraphRAG._init_extractor`, pass `config.entity_extraction.entity_types` to `create_extractor` instead of hardcoding.

2) Optional `relation_type` on edges (backward-compatible)

- Extend edge data model and storage adapters to accept `relation_type: Optional[str]`.
- Add light post-processing that sets `relation_type` using regex/keyword rules per profile; keep original `description` untouched.

3) Extraction profiles

- Add `extraction.profile: Optional[str]` and `extraction.domain: Optional[str]` to config. Map these to:
  - Prompt template selection (e.g., legal EOs prompt as drafted in the deep dive)
  - Relation vocabulary and post-processing rules
  - Property extraction hints (e.g., EO number, title, signing date)

4) Summarization awareness

- Update community summarization input assembly to optionally group/weight by `relation_type`. Maintain current behavior if absent.

5) Tests and metrics

- Add small labeled set (~50–100 snippets) for each profile to compute P/R for entities and typed relations. Track token usage and latency.

## Risks and Trade-offs

- Prompt complexity risk: Profiles might drift. Mitigate via unit tests on prompts, prompt evaluation suites, and keeping profiles concise.
- Schema overreach risk: A full ontology can stall delivery. Mitigate by starting with the `relation_type` and light validators; introduce schemas gradually and only where ROI is clear.
- Cost risk: More tokens if prompts get verbose. Mitigate via extract-then-refine pattern, adaptive gleaning, and cheap model for enrichment steps.
- Data migration risk: Adding `relation_type` must not break existing graphs. Keep it optional; default to `RELATED` for old edges; provide a no-op migration path.

## Alignment with GraphRAG Paper

- The paper’s pipeline (entities → communities → summaries → map-reduce answers) benefits from typed relations:
  - Better prioritization (e.g., legal supersession chains are likely high-signal edges)
  - Richer, structured community summaries (sections by relation type)
  - More faithful global answers for sensemaking questions that hinge on relation semantics, not just co-occurrence

## Recommended Plan (Incremental)

Phase 0 — Enable configurability (low lift)

- Add `entity_types` to config and wire through to extractor.
- Ship a first “legal.executive_orders” profile: small relation vocabulary, simple post-processing, no schema changes.

Phase 1 — Enrich semantics (medium lift)

- Add `relation_type` field + post-processors, and update community summarization to optionally leverage it.
- Introduce property extraction for profile-critical fields (EO number, title, date signed) with validators.

Phase 2 — Foundation for schemas (higher lift)

- Introduce optional `EntityTypeSchema` and `RelationSchema` for the EO profile only. Keep default path schema-light. Add versioning scaffolding.

Phase 3 — Domain expansion (ongoing)

- Package profiles (legal, medical, financial) and build a small marketplace-style pattern for community contributions.

## Success Criteria

- Functional: System answers domain-specific relation questions that were previously unanswerable or brittle.
- Quality: On a labeled set, typed relation P/R > baseline; fewer hallucinated relations.
- Cost/Perf: Token usage and latency increase <30% for typical doc sizes; DSPy routes are neutral or cheaper.
- Maintainability: Profiles are small, readable, and test-covered; default path remains simple.

## Final Verdict

- Strongly supportive of the direction with an incremental scope.
- Practical short-term wins exist in today’s code with very low risk (configurable types, profiles, typed relation post-processing).
- Schema-driven architecture is worth pursuing only after validating ROI on one or two profiles; guard against a “big rewrite.”

## Concrete Next Steps (low effort, high value)

- Add `entity_types` to `EntityExtractionConfig`; thread to `create_extractor`; remove hardcoded list in `GraphRAG._init_extractor`.
- Add optional `relation_type` to edge payloads and storage adapters; default to absent.
- Implement a “legal.executive_orders” extraction profile with:
  - Prompt additions for EO properties and legal relation terms
  - Post-processor mapping obvious relations to `relation_type` using regex/keywords
  - Minimal validators (EO number format, date parse)
- Add a couple of targeted tests and a sample dataset to measure lift and cost.

