Debug reviewer ready.

# NGRAF-008 — Legacy Boundary Cleanup (Round 1)

This review evaluates the implementation against the NGRAF-008 ticket and highlights any defects, risks, and improvement opportunities from a debugging and security perspective.

## Scope Adherence
- Deprecation warnings added for legacy LLM functions and global client getters:
  - `nano_graphrag/_utils.py`: Introduces `deprecated_llm_function` decorator with once-per-session warnings (lines ~18–69).
  - `nano_graphrag/_llm.py`: Applies deprecation to global getters and enhances docstrings with migration examples (e.g., lines ~42–88).
  - Provider legacy helpers decorated (call-site warnings):
    - OpenAI: `gpt_4o_complete`, `gpt_4o_mini_complete`, `openai_embedding` (openai.py lines ~357–405)
    - Azure: `azure_gpt_4o_complete`, `azure_gpt_4o_mini_complete`, `azure_openai_embedding` (azure.py lines ~132–176)
    - Bedrock: `create_amazon_bedrock_complete_function`, `amazon_bedrock_embedding` (bedrock.py lines ~133–165)
- Migration guide added at `docs/migration_guide.md` with clear before/after patterns and timeline.
- Tests added: `tests/test_legacy_deprecation.py` cover warnings, once-per-session behavior, and backward compatibility.

Deviation from ticket (documented, acceptable rationale):
- No `llm/legacy.py` module or lazy warning exports in `llm/__init__.py`. The implementation opts for decorating the existing provider-level functions and global getters instead. This still meets the core goal (clear deprecation warnings and migration path) with less churn.

## Critical Issues (must fix before merge)
- None found. Backward compatibility preserved; legacy functions continue to work and tests validate behavior.

## High Priority Issues (should fix soon)
- Import-time guidance (optional but valuable)
  - Files: `nano_graphrag/_llm.py`, `readme.md`
  - Observation: The current approach warns at call-time. Adding a module-level deprecation notice in `_llm.py` on import would more proactively steer users away from legacy paths.
  - Recommendation: At the top of `_llm.py`, issue a single `warnings.warn("_llm is deprecated…", DeprecationWarning, stacklevel=2)` behind a guard to avoid repeated warnings. Also add a brief note/link to `docs/migration_guide.md` in `readme.md` where `_llm` is referenced.

## Medium Priority Suggestions (improvements)
- Legacy exports visibility in providers package
  - File: `nano_graphrag/llm/providers/__init__.py`
  - Suggestion: Consider adding a short module docstring note that legacy helpers are deprecated and refer users to providers’ classes. This complements call-time warnings without introducing import-time noise.

- Thread-safety of warning registry
  - File: `nano_graphrag/_utils.py`
  - Note: `_deprecation_warnings_shown` is a global `set`. In multi-threaded use, set mutation is not atomic. The practical risk is minimal, but if concurrency is expected, consider a `threading.Lock` or using `warnings.filterwarnings` for process-wide control. Not a blocker.

- Coverage breadth
  - Ensure examples that still import from `_llm` (e.g., `examples/using_hnsw_as_vectorDB.py`, readme snippets) either include a deprecation note or are updated to provider usage in a future docs PR.

## Low Priority Notes (nice to have)
- The decorator’s `removal_version` default is `0.2.0` and is included in messages as required. Good.
- Docstrings in `_llm.py` show concrete migration examples, which is helpful in IDE hovers.
- Tests clear the internal `_deprecation_warnings_shown` set between assertions; this is fine for tests but keep it non-public in the library API.

## Positive Observations (well done)
- Clean, minimal surface change: Deprecations are applied where the legacy functions live, avoiding intrusive plumbing changes.
- Good DX: Warnings are informative (name, replacement, removal version) and shown once per session per function to avoid spam.
- Migration guide is comprehensive with provider-based examples for OpenAI, Azure, and Bedrock, including suppression instructions.
- Backward compatibility is preserved and validated by tests.

## Verification Highlights
- Calling any of the decorated legacy functions emits `DeprecationWarning` exactly once per process (verified in tests/test_legacy_deprecation.py).
- Global client getters now warn and still return a client when mocked (no credential requirements in CI).
- No impact to core provider classes; the deprecation layer is additive.

## Conclusion

Implementation aligns with NGRAF-008’s intent and is production-ready. The only recommended follow-ups are documentation polish and an optional import-time deprecation nudge in `_llm.py`. Approved from a debugging/security perspective.

