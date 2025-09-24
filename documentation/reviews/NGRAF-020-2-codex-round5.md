# NGRAF-020-2 – Round 5 Code Review

## High Findings
- [CODEX-006]: nano_graphrag/_extraction.py:301, nano_graphrag/entity_extraction/llm.py:170, nano_graphrag/_extraction.py:505 | High | `sanitize_str` returns `None` when the NDJSON field is `null` or empty. The call sites immediately do `sanitize_str(...).upper()`, so a `null` value from the LLM (e.g., `{"name": null}`) raises `AttributeError` and aborts extraction. This regression affects both the legacy `_extraction.extract_entities` path and the refactored `LLMEntityExtractor`. | Make `sanitize_str` return `""` instead of `None` (or guard before `.upper()`), and add a regression test that feeds NDJSON with `null` fields to prove extraction stays resilient.

## Positive Observations
- [CODEX-GOOD-002]: tests/test_ndjson_extraction.py:1-130 | The new NDJSON-focused tests exercise the parser, newline handling, and sanitisation helpers, giving us much better coverage of the format change.

## Recommended Next Steps
1. Harden the sanitiser so `null`/empty values no longer crash `.upper()` calls.
2. Extend the NDJSON tests to cover `null` fields once the guard is in place.
3. Re-run the extraction/query smoke tests to confirm ingestion still succeeds on the updated code.
