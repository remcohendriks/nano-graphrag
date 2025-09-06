# Viability Report for Ticket NGRAF-009: TypedDict Schemas

**Date:** 2025-09-04
**Author:** Gemini (Requirements Analyst and QA Lead)

## 1. Assessment Summary

The ticket is **highly viable and critically important** for the health and maintainability of the codebase. My analysis confirms that the project currently relies heavily on untyped `dict` and `list[dict]` objects for its core data structures. This creates exactly the problems the ticket describes: poor IDE support, high risk of `KeyError` from typos, and a lack of clear, enforceable contracts between different parts of the system.

The proposed solution to introduce a central `schemas.py` file and annotate function signatures is the correct and standard approach to resolving this technical debt.

## 2. Evidence from the Codebase

*   **`nano_graphrag/base.py`**: This file defines some `TypedDict` schemas like `TextChunkSchema` and `CommunitySchema`, which is a good start. However, it also defines storage protocols like `BaseGraphStorage` with many methods that return `dict`, `list[dict]`, or `Union[dict, None]`. This confirms the inconsistency and the need for a more comprehensive schema definition.

*   **`nano_graphrag/_extraction.py`**: This module is a prime example of the problem.
    *   The function `_merge_nodes_then_upsert` takes a `nodes_data: list[dict]`. It's impossible to know the expected structure of these dictionaries without reading the function's implementation in detail.
    *   The function `extract_entities` returns `Union[BaseGraphStorage, None]`, but its real work is creating nodes and edges with specific, yet undocumented, dictionary structures.
    *   The code is full of string-based key access like `dp["entity_type"]` and `if_entities["entity_name"]`, which is fragile and prone to typos.

*   **`nano_graphrag/_community.py`**: This module shows similar issues.
    *   The function `_pack_single_community_describe` takes `already_reports: dict[str, CommunitySchema]`, which is good, but it also accesses nested, untyped dictionaries like `c["report_json"].get("rating", -1)`.
    *   The return types are often complex tuples like `tuple[str, int, set, set]`, which are difficult to understand without a clear schema definition.

## 3. Proposed Solution Assessment

The technical solution outlined in NGRAF-009 is excellent and well-considered.

*   **Central `schemas.py` File**: Creating a dedicated file for all data schemas is a best practice. It provides a single source of truth for the project's data models, making them easy to find, understand, and import.
*   **Incremental Approach**: The decision to focus on defining schemas and annotating function signatures first, while **deferring changes to the storage layer's runtime behavior**, is a very wise and pragmatic approach. It reduces the scope of the ticket, minimizes risk, and allows the benefits of type safety to be realized immediately in the application logic without requiring a major, simultaneous refactoring of all storage backends.
*   **Runtime Validation**: The suggestion to add runtime validation helpers like `is_valid_node` is a valuable addition. While `TypedDict` provides static analysis, these helpers can prevent errors from malformed data coming from external sources (like an LLM call) at runtime.

## 4. Conclusion

Ticket NGRAF-009 addresses a clear and present source of technical debt in the codebase. The lack of explicit data contracts makes the code harder to read, riskier to change, and more difficult for new contributors to learn. The proposed solution is well-scoped, follows best practices, and will deliver significant improvements in code quality, developer experience, and reliability.

I strongly recommend proceeding with this ticket as specified. It is a foundational cleanup task that will benefit all future development.
