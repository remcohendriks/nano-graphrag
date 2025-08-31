# NGRAF-004.5 PR Review — Test Modernization

## Summary
- Good lift: tests now align with the refactored config/provider patterns, prefer tmp dirs, and avoid network. Centralizing mocks in `tests/utils.py` is the right move. Execution speed looks solid for core tests.
- Remaining failures are fixable with focused adjustments: a few mismatches with current storage/provider APIs, missing clustering config in storage fixtures, and a couple of pytest mechanics. Also, please avoid deleting unrelated reports/reviews in this PR.

## What Changed (diff vs main)
- Added: `tests/utils.py` (shared mock utilities), `tests/test_providers.py` (provider-level tests).
- Updated: `tests/test_config.py`, `tests/test_rag.py`, `tests/test_networkx_storage.py`, `tests/test_hnsw_vector_storage.py`, `tests/test_neo4j_storage.py`.
- Removed: older NGRAF‑005.5 reports and reviews. These deletions aren’t directly related to test modernization—suggest restoring them or moving deletion to a separate housekeeping PR.

## Passing vs Failing (from your report)
- Passing: config, factory, splitter, JSON parsing, and entity_extraction tests — nice.
- Failing: providers (async mocking details), RAG (preconditions and response shapes), storage tests (config keys and API mismatch).

## Guidance by Area

### 1) Provider tests — async mocking and usage fields
File: `tests/test_providers.py`
- Issue: `OpenAIProvider.complete(...)` accesses `response.usage.prompt_tokens` and `completion_tokens`. The test only sets `total_tokens`, leading to attribute errors.
- Fix: ensure all expected usage fields exist and keep the response awaitable via `AsyncMock`.

```python
# tests/test_providers.py (inside with patch('openai.AsyncOpenAI') ...)
mock_create = AsyncMock()
mock_client.chat.completions.create = mock_create

# Provide full usage object with required attributes
usage = Mock()
usage.prompt_tokens = 10
usage.completion_tokens = 90
usage.total_tokens = 100

mock_response = Mock()
mock_response.choices = [Mock()]
mock_response.choices[0].message.content = "test response"
mock_response.usage = usage

mock_create.return_value = mock_response
```

- Note: The client is not used as an async context manager, so you don’t need `__aenter__/__aexit__` on the mock.
- Base URL separation test: assertion order on `mock_client_class.call_args_list` is brittle. Safer to use separate patch contexts for LLM and embedding or assert via the last call args.

```python
with patch('openai.AsyncOpenAI') as mock_openai:
    mock_openai.return_value = MagicMock()
    llm_provider = get_llm_provider('openai', 'test-model')
    llm_kwargs = mock_openai.call_args.kwargs
    assert llm_kwargs.get('base_url') == 'http://localhost:1234/v1'

with patch('openai.AsyncOpenAI') as mock_openai:
    mock_openai.return_value = MagicMock()
    embed_provider = get_embedding_provider('openai', 'text-embedding-3-small')
    embed_kwargs = mock_openai.call_args.kwargs
    assert embed_kwargs.get('base_url') == 'https://api.openai.com/v1'
```

### 2) RAG tests — preconditions and expectations
File: `tests/test_rag.py`
- Issue: global/local queries depend on the graph/communities being populated; with mock LLM returning arbitrary strings, entity extraction yields no nodes, and global query returns the default fail response ("No context").
- Direction:
  - Either insert pre-populated data (community reports and a minimal community schema) or perform a real `rag.insert(...)` but patch downstream ops to ensure context exists without parsing LLM output.
  - For unit scope, prefer pre-seeding storages so you don’t rely on entity extraction.

Example approach (pre-seed for global):
```python
with patch('nano_graphrag.llm.providers.get_llm_provider') as mock_llm, \
     patch('nano_graphrag.llm.providers.get_embedding_provider') as mock_embed:
    mock_llm.return_value = llm_provider
    mock_embed.return_value = embedding_provider

    rag = GraphRAG(config=GraphRAGConfig(storage=StorageConfig(working_dir=temp_working_dir)))

    # Pre-seed minimal community schema and report
    # 1) Patch community_schema to return one cluster id
    async def fake_schema():
        return { 'C1': { 'level': 0, 'title': 'Cluster 1', 'edges': [], 'nodes': [], 'chunk_ids': [], 'occurrence': 1.0, 'sub_communities': [] } }
    rag.chunk_entity_relation_graph.community_schema = AsyncMock(side_effect=fake_schema)

    # 2) Upsert community_reports data used by global_query
    await rag.community_reports.upsert({
        'C1': { 'report_string': 'Summary', 'report_json': { 'rating': 1.0 }, 'level': 0, 'occurrence': 1.0 }
    })

    result = await rag.aquery('Test', param=QueryParam(mode='global'))
    assert result == FAKE_JSON  # if your mock LLM returns FAKE_JSON
```

For local query, either:
- Pre-seed `entities_vdb` and `text_chunks` with one entity + source chunk and patch `_build_local_query_context` (via `nano_graphrag._op`) to return a synthetic context; or
- Assert behavior is not the fail response rather than an exact string, if your goal is to ensure the plumbing works.

Also, the async tests are not marked correctly. The lines at the bottom:
```python
pytest.mark.asyncio(test_local_query_with_mocks)
```
won’t register markers. Use decorators:
```python
@pytest.mark.asyncio
async def test_local_query_with_mocks(...):
    ...
```

### 3) NetworkX storage — clustering config
File: `tests/test_networkx_storage.py`
- Issue: clustering code in `NetworkXStorage._leiden_clustering` requires keys in `global_config`:
  - `graph_cluster_algorithm`, `max_graph_cluster_size`, `graph_cluster_seed`.
- Fix: augment the fixture’s `global_config` for tests that perform clustering.

```python
global_config = {
    'working_dir': temp_dir,
    'embedding_func': mock_embedding,
    'embedding_batch_num': 32,
    'embedding_func_max_async': 16,
    'graph_cluster_algorithm': 'leiden',
    'max_graph_cluster_size': 10,
    'graph_cluster_seed': 3967219502,
}
```

### 4) HNSW storage — upsert shape and nonexistent delete
File: `tests/test_hnsw_vector_storage.py`
- Issues:
  - `HNSWVectorStorage.upsert` expects a dict mapping id → payload with a `content` field (see `nano_graphrag/_storage/vdb_hnswlib.py`), not a list of dicts.
  - There’s no `delete(...)` API on HNSW; testing it will fail.
- Fixes:
  - Use the API shape expected by storage and include `content` in payload. Use entity names as IDs if that’s the semantic you want to test.

```python
# Build the payload the storage expects
payload = {
    'Apple':  { 'content': 'A fruit that is red or green', 'entity_name': 'Apple' },
    'Banana': { 'content': 'A yellow fruit that is curved', 'entity_name': 'Banana' },
    'Orange': { 'content': 'An orange fruit that is round', 'entity_name': 'Orange' },
}
await hnsw_storage.upsert(payload)
results = await hnsw_storage.query('A fruit', top_k=2)
assert len(results) == 2
assert all('entity_name' in r and 'distance' in r for r in results)
```

  - Replace the delete test with a persistence round‑trip test (call `index_done_callback()` then create a new instance and query again). The storage does not expose a deletion API.

### 5) Neo4j tests — skip strategy
File: `tests/test_neo4j_storage.py`
- Your skip condition looks good and prevents false failures. If/when you add a mock-based test, ensure `AsyncGraphDatabase.driver(...)` is patched to avoid sockets.

## Minor Polish
- `tests/utils.py` is helpful. Consider adding a `create_mock_kv_store()` to pre-seed KV where needed (e.g., community reports) and a small helper to create a clustering-ready `global_config` dict for storage fixtures.
- Keep unrelated report/review files out of this PR; consider restoring removed NGRAF‑005.5 reports/reviews and moving that deletion to a docs cleanup PR.

## Representative Code References
- HNSW API shape: `nano_graphrag/_storage/vdb_hnswlib.py:62-112` — upsert expects `dict[str, dict]` with `content`.
- NetworkX clustering config: `nano_graphrag/_storage/gdb_networkx.py:_leiden_clustering` reads `max_graph_cluster_size` and handles empty graphs.
- Global/local query prerequisites: `nano_graphrag/_op.py:1023-1060 (global_query)` returns default fail response if no communities.
- Provider GPT‑5 param mapping and content guard: `nano_graphrag/llm/providers/openai.py` maps `max_tokens→max_completion_tokens` and guards `None` content.

## Verdict
You’re close. With the targeted fixes above—correct upsert shapes, clustering config in storage fixtures, proper async markers, more complete provider mocks, and pre-seeded storages for RAG queries—the remaining failures should fall quickly while keeping tests fast and deterministic.

