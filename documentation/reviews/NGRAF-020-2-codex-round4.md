# NGRAF-020-2 – Round 4 Code Review

## Critical Findings
- [CODEX-001]: nano_graphrag/entity_extraction/llm.py:52 | Critical | `LLMEntityExtractor` still tokenises the LLM output with the legacy tuple/CSV logic (`split_string_by_multi_markers` + regex). With the prompt now emitting NDJSON, every line fails the `re.search("\\((.*)\\)")` check, so no entities/relationships are produced and GraphRAG indexing/querying breaks. | Rework `extract_single` (and helpers) to iterate over the NDJSON lines, `json.loads` each object, and populate nodes/edges exactly as the legacy `_extraction` path now does.

## High Findings
- [CODEX-002]: nano_graphrag/_extraction.py:276 | High | When converting `strength` to `float`, the new code does `float(obj.get('strength', 1.0))` inside the NDJSON parser. If the model returns `null` or a non-numeric string (common with LLM drift), this raises `TypeError` which isn’t caught, aborting extraction for the chunk. | Wrap the conversion in a guarded helper (mirroring the old `is_float_regex` behaviour) that tolerates `None`/bad values and falls back to `1.0` without throwing.

## Medium Findings
- [CODEX-003]: nano_graphrag/_extraction.py:244 | Medium | Gleaning responses are concatenated with `final_result += glean_result`. If the continuation string lacks a leading newline, the trailing JSON object from the previous batch and the first object of the new batch merge into invalid JSON, so both records are dropped. | When appending gleaned text, inject a newline (`\n`) when needed before concatenation.
- [CODEX-004]: nano_graphrag/_extraction.py:286 | Medium | The NDJSON path no longer calls `clean_str`. Any leading/trailing whitespace or control chars the model emits now flow straight into entity IDs/descriptions, risking mismatched hashes and messy graph data. | Reapply lightweight sanitisation (e.g. `clean_str(...).strip()`) after `json.loads` for names/descriptions to keep identifiers canonical.

## Low Findings
- [CODEX-005]: tests/ | Low | No automated coverage was added for the NDJSON pipeline. The test suite only adjusts the Qdrant hybrid expectation, so regressions in the new parser or prompt contract will go unnoticed. | Add unit/integration tests that feed NDJSON lines through both `_extraction.extract_entities` and `LLMEntityExtractor` once updated, asserting that entities/relationships round-trip without quotes.

## Positive Observations
- [CODEX-GOOD-001]: nano_graphrag/prompt.py:200 | The refreshed prompt and worked examples clearly communicate the NDJSON contract, which should help models stay on-spec and aids future debugging.

## Open Questions / Assumptions
- I assumed no other extraction strategy (e.g. DSPy) relies on the legacy tuple prompts. If they share the same prompt, they’ll need equivalent NDJSON support.

## Recommended Next Steps
1. Update `LLMEntityExtractor` to the NDJSON contract and add regression tests.
2. Harden the NDJSON parser (`strength` conversion, newline joins, sanitisation).
3. Re-run end-to-end extraction/query smoke tests once fixes land to verify the quote regressions remain solved.
