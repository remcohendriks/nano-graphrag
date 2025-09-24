# NGRAF-021 – Configurable Query Response Prompt Template

## Summary
Allow deployments to override the hard-coded Local/Global query response prompts with a configurable template while retaining the existing defaults.

## Motivation
The current implementation uses fixed prompt strings within `PROMPTS["local_rag_response"]` and `PROMPTS["global_map_rag_points"]` (see `nano_graphrag/_query.py:208-240`). Teams that need alternate response formats—e.g., bullet-only summaries, tone-controlled outputs, or additional metadata—must modify source code, which is impractical and error-prone. Providing a configuration hook aligns with the project’s goal of making GraphRAG adaptable without code edits.

## Requirements
1. Introduce an optional configuration entry (e.g., `QueryConfig.response_prompt_template`) that can carry either a raw string or a path to a template file. Refer to `nano_graphrag/config.py` for existing config patterns.
2. Update the query pipeline (`nano_graphrag/_query.py:208-240` and `nano_graphrag/_query.py:396-423`) to select the configured template when present, otherwise fall back to the current defaults in `PROMPTS`.
3. Support the existing placeholder contract (`{context_data}`, `{response_type}`, etc.). Any missing placeholders should raise a clear error during formatting to aid debugging.
4. Document the new option in `readme.md` (Configuration → Query section) with an example template snippet.
5. Add test coverage demonstrating that:
   - Default behavior remains unchanged when no template is supplied.
   - A supplied template overrides the default and formats the response as expected.
   See `tests/test__query.py` for existing query tests that can be extended.

## Design Notes
- Prefer integrating this alongside existing config load paths (e.g., `config.from_env` or YAML). Keep the interface consistent with other optional overrides (e.g., `StorageConfig.hybrid_search`).
- Template loading can be simple string substitution (standard `.format`). There is no requirement for a templating engine.
- The configuration should be available to both Local and Global query flows to avoid divergence.
- **Validation**: Templates should be validated at initialization time, not query time, to catch missing placeholders early.
- **Error Handling**: When template formatting fails, provide clear error messages showing which placeholders are missing. Consider falling back to default templates if custom template fails.
- **Metadata Exposure**: Consider exposing additional context variables like `{confidence}`, `{sources}`, `{timestamp}` for richer customization needs.

## Enhanced Configuration Design
Support both inline templates and file paths:
```python
# In GraphRAGConfig or QueryConfig
response_template_config = {
    "local": "./templates/local_response.txt",  # File path
    "global": "Answer based on context: {context_data}",  # Inline string
    "validate_on_startup": True,  # Validate templates during initialization
    "fallback_on_error": True,  # Use default template if custom fails
}
```

## Placeholder Contract
Document available placeholders for each query type:
- **Local Query**: `{context_data}`, `{response_type}`, `{query}`, `{entities}`
- **Global Query**: `{context_data}`, `{response_type}`, `{query}`, `{reports}`
- **Future-Proof**: Consider versioning the placeholder contract or supporting optional placeholders that default to empty strings

## Testing Requirements
Beyond basic override testing:
- Template with missing required placeholders (should fail validation)
- Template with unknown placeholders (should warn but continue)
- Unicode and special characters in templates
- Very long templates approaching token limits
- Template file not found or unreadable
- Malformed template syntax
- Placeholder injection attempts (security consideration)

## Acceptance Criteria
- Configuration file / environment variable can specify a custom query response template.
- Local and Global query functions use the custom template when provided, otherwise default prompts.
- Template validation occurs at startup with clear error messages.
- Tests confirm both default and override behavior.
- Tests verify error handling for invalid templates.
- Documentation clearly explains how to configure the template and which placeholders are supported.
- Documentation includes example templates for common use cases (academic citations, business reports, technical documentation).
