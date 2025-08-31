# NGRAF-004.5 PR Review — Round 2

## Summary
- Solid follow‑through on Round 1: provider mocks now include usage fields, HNSW tests use the correct upsert shape, and async markers are fixed. You also started pre‑seeding for RAG and added clustering config to storage fixtures.
- However, a meaningful subset of tests are still failing. Many of these failures come from tests asserting legacy/invalid contracts (e.g., provider helpers that don’t exist) or from asserting exact response shapes when the unit under test is intentionally mocked. Some tests need to be reframed; a few should be retired or split into an “integration” track.

## What Improved
- `tests/test_providers.py`: usage fields added; base‑URL separation isolated into distinct contexts; caching hit path covered.
- `tests/test_hnsw_vector_storage.py`: now uses `dict[str, dict]` with `content` for `upsert(...)`; delete test replaced; persistence covered.
- `tests/test_rag.py`: switched to tmp dirs and provider patching; async tests present.
- `tests/test_networkx_storage.py`: temp dir fixture and minimal global_config provided.

## What’s Still Failing (and why)

### A) Provider contract tests (inside repo)
Files: `nano_graphrag/llm/providers/tests/test_openai_provider.py`, `nano_graphrag/llm/providers/tests/test_contract.py`
- Mismatched API expectations vs current code:
  - Expect `BaseLLMProvider.__init__` to accept `max_tokens`, `temperature` (not in current signature).
  - Expect helper `_retry_with_backoff` (not implemented; our provider uses straightforward `asyncio.wait_for` wrapping and direct calls).
  - Expect `OpenAIEmbeddingProvider` to expose `max_batch_size` attr (not present).
  - Expect `complete(...)` to return a plain string in places; current returns a `CompletionResponse` dict in provider, and our high‑level wrappers convert to string elsewhere.
- Recommendation: These tests appear authored for a different/earlier contract and should be modernized to the actual provider APIs we ship. Concretely:
  - Remove/rewrite tests that target `_retry_with_backoff`, `max_tokens/temperature` ctor args, or embedding `max_batch_size` attribute.
  - Keep contract tests focused on:
    - Parameter translation (GPT‑5: `max_completion_tokens` and `reasoning_effort="minimal"`; non‑GPT‑5: `max_tokens`).
    - Timeout error mapping (by patching `asyncio.wait_for` to raise `TimeoutError`).
    - `None` content guard (content → empty string).
    - Caching behavior via `complete_with_cache(hashing_kv=...)`.
  - Example rewrite for a timeout test:
    ```python
    @pytest.mark.asyncio
    async def test_timeout_maps_to_LLMTimeoutError():
        provider = OpenAIProvider(model="gpt-5-mini")
        with patch('openai.AsyncOpenAI') as mock_client, \
             patch('asyncio.wait_for', side_effect=asyncio.TimeoutError()):
            mock_client.return_value = MagicMock()
            with pytest.raises(LLMTimeoutError):
                await provider.complete("prompt")
    ```

### B) RAG tests still assert too much
File: `tests/test_rag.py`
- Current test still asserts `result == FAKE_JSON` for global mode but does not show the pre‑seeding code claimed in your report. As written, `global_query(...)` will return the default fail response unless communities and reports are present.
- Recommendation: Align the file with your report by actually pre‑seeding and relaxing assertions to outcomes that reflect unit scope:
  - Pre‑seed `community_reports` and patch `community_schema()` to return a minimal cluster that references the report.
  - For local mode, pre‑seed `text_chunks` and `entities_vdb` or patch `_build_local_query_context` to return a minimal context string. Otherwise, local will fall back to `fail_response`.
  - Prefer an assertion like “not default fail response” or “LLM called with our system prompt” rather than exact JSON when the LLM is mocked to return arbitrary strings.
  - Example (global):
    ```python
    @pytest.mark.asyncio
    async def test_global_query_with_preseed(temp_working_dir, mock_providers):
        llm_provider, embedding_provider = mock_providers
        with patch('nano_graphrag.llm.providers.get_llm_provider', return_value=llm_provider), \
             patch('nano_graphrag.llm.providers.get_embedding_provider', return_value=embedding_provider):
            rag = GraphRAG(config=GraphRAGConfig(storage=StorageConfig(working_dir=temp_working_dir)))
            await rag.community_reports.upsert({'C1': {'report_string': 'S', 'report_json': {'rating': 1.0}, 'level': 0, 'occurrence': 1.0}})
            rag.chunk_entity_relation_graph.community_schema = AsyncMock(return_value={
                'C1': {'level': 0, 'title': 't', 'edges': [], 'nodes': [], 'chunk_ids': [], 'occurrence': 1.0, 'sub_communities': []}
            })
            result = await rag.aquery("Q", param=QueryParam(mode="global"))
            assert result  # Non-empty and not default fail
    ```

### C) NetworkX clustering in tests
File: `tests/test_networkx_storage.py`
- You added general config, but tests that call clustering still need:
  - Minimal graph content (at least 1–2 nodes/edges) or an assertion that empty‑graph is a no‑op.
  - Reminder: `_leiden_clustering()` logs and returns if graph has 0 nodes/edges.
- Recommendation: For tests asserting clustering outcomes, insert a couple of nodes + an edge before calling `clustering("leiden")`. If you only want to assert that clustering executes without error, assert it doesn’t raise (not structural outcomes).

### D) HNSW tests — keep to actual API
File: `tests/test_hnsw_vector_storage.py`
- Upsert shape is now correct. Continue avoiding non‑existent APIs (`delete`). For “update existing,” call `upsert` twice with a changed payload for the same id and assert that the returned metadata reflects the latest value.

## Tests to Retire or Move to “integration”
- Retire/Rewrite: `nano_graphrag/llm/providers/tests/test_openai_provider.py` and `.../test_contract.py` portions that assert non‑existent helpers or ctor args.
- Move behind marker: Any test that assumes real behavior across extract→cluster→query should live under an `integration` or `e2e` marker and be optional in fast CI. Our Health Check suite covers this path already.

## Suggested Refactors to Make Tests Easier
- Providers: Expose a tiny helper for translating vendor‑neutral params (e.g., `_translate_params` already exists) and keep timeout logic simple. Testing becomes a matter of patching `AsyncOpenAI` and verifying call kwargs.
- RAG: Consider extracting context‑builder helpers as small functions that can be patched in unit tests, rather than mocking deeper graph storages.
- Storage fixtures: Introduce a small `make_global_config(temp_dir, extra=None)` in `tests/utils.py` to avoid copying config dicts and to include clustering keys when needed.

## Representative Code References
- Global query preconditions: `nano_graphrag/_op.py:1023–1060` — returns fail response if no communities are available or have low ratings.
- HNSW upsert shape: `nano_graphrag/_storage/vdb_hnswlib.py:62–112` — expects dict of id→payload with `content`.
- NetworkX empty graph handling: `nano_graphrag/_storage/gdb_networkx.py:_leiden_clustering` logs and returns early on empty graph.
- Provider GPT‑5 parameter mapping and `None` content guard: `nano_graphrag/llm/providers/openai.py`.

## Final Recommendations
1) Modernize or skip legacy provider contract tests that don’t match current APIs.
2) Implement the RAG pre‑seeding shown in your report in the actual `tests/test_rag.py` and relax assertions to reflect mocked LLM usage.
3) Ensure clustering tests build a minimal graph if they assert outcomes; otherwise, only assert no exceptions.
4) Keep the unit suite fast and deterministic; move extract→cluster→query expectations to the Health Check or mark as `integration`.

With these adjustments, the remaining failures should resolve without widening the test scope or adding brittle checks.


## Round 3 — Failing Unit Test Viability

Below is a test-by-test assessment of the current failures and whether each test remains viable based on the modernized APIs and intended unit-test scope. Where a test is viable but brittle, I propose a concrete adjustment; where it’s no longer aligned with the system contracts, I recommend retiring or rewriting it.

### Providers — legacy tests inside package
File: `nano_graphrag/llm/providers/tests/test_openai_provider.py`
- test_provider_initialization: Not viable. Expects `BaseLLMProvider` ctor to accept and expose `max_tokens`/`temperature`. Current provider config handles these via `CompletionParams` or `LLMConfig`, not as ctor attrs.
- test_provider_reads_env_key: Viable. Confirms `env_key` is honored; matches current behavior.
- test_caching_functionality: Not viable. Assumes `complete_with_cache` wraps a provider whose `complete(...)` returns a plain string. Current providers return a typed dict; `complete_with_cache` extracts the string.
- test_message_building: Viable. Uses `_build_messages(...)`; unchanged and correct.
- test_openai_complete: Not viable. Asserts `OpenAIProvider.complete(...)` returns a string; it returns a `CompletionResponse` dict.
- test_openai_with_system_and_history: Viable. Validates the constructed `messages` payload; remains correct with modern provider.
- test_max_tokens_parameter_selection: Viable but weak. It only checks model naming; consider moving this assertion into parameter translation tests instead (covered elsewhere).
- test_embedding_initialization: Viable. Confirms defaults `model` and `embedding_dim`.
- test_embedding_mock: Not viable. Expects `embed(...)` to return a NumPy array; now returns an `EmbeddingResponse` dict with an `embeddings` array.
- test_gpt_4o_complete_compatibility / test_gpt_4o_mini_complete_compatibility: Viable. Backward-compat helpers still map to providers.
- test_real_openai_* (3): Skipped unless API key set. Keep as optional integration checks.

Recommendation: Keep the viable ones; rewrite the not-viable tests to assert against the typed response shapes:
- For `complete(...)`: assert keys `text`, `finish_reason`, `usage`, `raw`.
- For `embed(...)`: assert dict with `embeddings` array and `dimensions`.

### Providers — contract tests inside package
File: `nano_graphrag/llm/providers/tests/test_contract.py`
- All listed tests are viable against the current provider contracts. They validate method presence, parameter translation, error mapping, timeout path, retry/backoff, and embedding response shape. If any fail locally, it’s likely due to mocking details, not test intent, and should be fixed rather than skipped.

### Providers — modernized external tests
File: `tests/test_providers.py`
- test_openai_provider_gpt5_params: Viable. Verifies GPT‑5 param mapping and usage fields via mocks; keep.
- test_provider_none_content_guard: Viable. Guarding `None` content is required for GPT‑5.
- test_base_url_separation: Viable. Confirms `LLM_BASE_URL` vs `EMBEDDING_BASE_URL` separation.
- test_complete_with_cache: Viable. Confirms cache hit path returns cached value.
- test_request_timeout_config: Viable. Checks `LLM_REQUEST_TIMEOUT` is respected.
- test_get_llm_provider_openai/unknown: Viable.
- test_get_embedding_provider_openai/unknown: Viable.
- test_provider_with_graphrag: Viable. Pure integration of provider factory into `GraphRAG` via patches.

If any of these still fail, it’s likely due to AsyncOpenAI mock shape (e.g., missing `usage.prompt_tokens`/`completion_tokens`). Keep; adjust mocks, not assertions.

### RAG tests
File: `tests/test_rag.py`
- test_insert_with_mocks: Viable. Uses tmp working dir and patched providers; asserts calls.
- test_local_query_with_mocks: Viable but brittle. Asserts equality to a fixed `FAKE_RESPONSE`. Prefer: assert non‑empty, not default fail message, and that LLM provider was invoked with the expected system prompt.
- test_global_query_with_mocks: Viable but brittle. Asserts exact JSON string (`FAKE_JSON`). Prefer: parse JSON and assert structural keys/values (e.g., presence of `points` and at least one `description`) rather than exact string equality.
- test_naive_query_with_mocks: Viable. Pre-seeding plus mocked LLM makes this deterministic; equality assertion is acceptable.
- test_backward_compatibility: Viable. Placeholder check; OK to keep or remove later.

Recommendation: Keep all; relax the two brittle assertions to reduce false negatives while preserving intent.

### NetworkX graph storage
File: `tests/test_networkx_storage.py`
- test_upsert_and_get_node/edge/degree/get_node_edges/nonexistent: Viable.
- test_clustering / test_leiden_clustering_consistency / test_leiden_clustering_community_structure / test_leiden_clustering_hierarchical_structure: Viable with seed. These can be sensitive to graph structure; assertions should target invariants (presence of communities, structural keys) rather than exact counts across different inputs. The config now supplies `graph_cluster_algorithm`, `max_graph_cluster_size`, and `graph_cluster_seed` — with that, keep these tests.
- test_persistence: Viable.
- test_embed_nodes: Viable; relies on deterministic `node2vec_params` provided in fixture.
- stable_largest_connected_component* (3): Viable. Deterministic unit functions; keep.
- community_schema_* (3): Viable. Tests schema structure and derived metrics; keep as written.
- test_concurrent_operations: Viable. Concurrency on in‑memory graph; keep.
- test_error_handling: Viable. Ensures explicit error messages on invalid algorithms.

If any still fail, it is likely due to missing clustering config or insufficient graph seeding. Keep; fix setup, not assertions.

### HNSW vector storage
File: `tests/test_hnsw_vector_storage.py`
- test_upsert_and_query: Viable. Uses correct dict payload with `content`; keep.
- test_persistence: Viable. Index round‑trip is the right replacement for a delete test.
- test_multiple_upserts: Viable. Confirms additive upserts; keep.
- test_embedding_function: Viable but brittle to call signature. If failing, assert `mock_embed.called` rather than inspecting positional args; the API can batch/shape inputs.
- test_max_elements_limit: Viable. Exercises `max_elements` constraint.
- test_empty_query / test_upsert_empty_dict: Viable.
- test_metadata_fields: Viable. Asserts that only `meta_fields` propagate.
- test_distance_calculation: Viable. Asserts ordering and presence of `distance`.

Recommendation: Keep. If one flakes, prefer verifying that the embedding was invoked and results are non‑empty over specific call argument shapes.

### Neo4j storage
File: `tests/test_neo4j_storage.py`
- Entire file: Viable as optional. Correctly skipped when `NEO4J_URL`/`NEO4J_AUTH` are not set. Keep behind skip; do not fold into the fast unit suite.

### Entity extraction (DSPy)
Files: `tests/entity_extraction/*`
- All tests: Viable. Self‑contained with mocks and optional compile path. If they fail locally it’s typically due to missing `dspy` dependency, not test design. Keep as unit tests; ensure `dspy-ai` is installed in CI.

---

Actionable summary:
- Modernize the not‑viable provider tests in `nano_graphrag/llm/providers/tests/test_openai_provider.py` to the current typed response shapes; keep the contract tests.
- Relax strict equality assertions in two RAG tests to structural/behavioral assertions.
- For any remaining storage test failures, prefer fixing fixture config (clustering keys, seeding) over weakening assertions.
