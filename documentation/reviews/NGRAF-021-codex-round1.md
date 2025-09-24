# NGRAF-021 – Round 1 Review (Debug/Security)

## Summary
Configurable query templates land with good coverage and documentation, but a formatting edge case will currently crash query execution instead of degrading gracefully.

## Critical Findings
- **CDX-001** – `nano_graphrag/_query.py:353-362` (and `:403-410`): When a custom template includes any placeholder beyond the required ones, `_validate_template` returns `True`, yet the subsequent `.format(...)` call is executed without guarding against unknown keys. Python `str.format` raises `KeyError`, so a template like `"Custom: {context_data}\nTone: {response_type}\nMode: {mode}"` will raise at runtime, breaking local/global queries (contradicting the documented "graceful fallback"). _Fix_: wrap the `.format` call in `try/except KeyError` and fall back to the default template (with a warning), or extend the formatter to tolerate extra placeholders (e.g., `str.format_map(DefaultDict(str, ...))`).

## Positive Notes
- Template fields integrated cleanly into `QueryConfig` and plumbed through `GraphRAG._global_config`.
- Readme updates give clear inline/file/ENV examples.
- New tests cover loading/validation/fallback behaviour (once the formatting issue is addressed, keep them—they’re valuable).

## Recommendation
Address CDX-001 so custom templates can safely include extra tokens (or degrade to defaults) before merging the feature.
