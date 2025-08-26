**NGRAF-002 Implementation Review (New-Only)**

- Ticket: `tickets/NGRAF-002-config-management-simplification.md`
- Report: `reports/NGRAF-002-implementation-report.md`
- Scope: Config simplification, provider factories, GraphRAG refactor (no legacy support)

**Summary**

- Strong move toward clarity with frozen, typed configs and provider factories. To make the new design work end-to-end, align the ops/storage interfaces to the new GraphRAG flow, simplify the chunk/extract/report pipeline, and lock down defaults and backend options for a clean new-only experience.

**Strengths**

- Configs: Frozen dataclasses, `from_env()`, and validation keep state explicit and safe.
- Providers: Factory entry points (`get_llm_provider/get_embedding_provider`) reduce coupling.
- Concurrency: `limit_async_func_call` provides simple, readable throttling.
- Structure: `_init_*` methods in `GraphRAG` are easy to read and reason about.

**Critical Fixes (New-Only)**

- Chunks API: Align to simple inputs/outputs that match `GraphRAG` usage.
  - Current code calls `get_chunks(string, ...)` and iterates over a list; the shipped function expects a doc dict and returns a dict.
  - New-only approach: introduce a thin `get_chunks_v2(text: str|list[str]) -> list[TextChunk]` that wraps the existing tokenizer + chunking function and returns a list of chunk records.

- Entity Extraction: Decouple extraction from storage side effects.
  - Current extractor mutates graph/vector stores and takes `global_config`.
  - New-only approach: add `extract_entities_from_chunks(chunks, model_fn, tokenizer, params) -> {nodes, edges}`. Then have `GraphRAG` handle storage upserts. This keeps responsibilities clean and testable.

- Community Reports: Match the per-community flow in `GraphRAG`.
  - The existing `generate_community_report` expects KV/graph/global_config and processes all levels at once.
  - New-only approach: add a small `summarize_community(nodes, graph, model_fn, max_tokens, to_json)` utility that returns a single community report. `GraphRAG` can then iterate communities discovered via `graph_storage.clustering()` + `graph_storage.community_schema()`.

- Persistence: Add explicit flushes at natural boundaries.
  - Call `index_done_callback()` on KV/vector/graph stores after inserts/updates to ensure durability.

- Defaults: Align model defaults with the documented baseline.
  - Set `LLMConfig.model` to `"gpt-4o-mini"`; reserve `"gpt-5*"` for future support.

- Backends: Keep config values honest and minimal.
  - Restrict `StorageConfig.vector_backend` to `{nano, hnswlib}` until others are implemented, to avoid runtime confusion.

**Suggested Changes (Low Complexity)**

- Chunking modernization
  - Add a wrapper that matches the new flow:
    ```python
    # _op.py
    def get_chunks_v2(text_or_texts, tokenizer_wrapper, chunk_func, size, overlap):
        texts = [text_or_texts] if isinstance(text_or_texts, str) else list(text_or_texts)
        tokens = [tokenizer_wrapper.encode(t) for t in texts]
        doc_keys = [f"doc-{i}" for i in range(len(texts))]
        chunks = chunk_func(tokens, doc_keys=doc_keys, tokenizer_wrapper=tokenizer_wrapper,
                           overlap_token_size=overlap, max_token_size=size)
        return chunks  # list[TextChunk]
    ```
  - In `GraphRAG.ainsert`, use the list directly and then `upsert` once per doc.

- Extraction boundary
  - Add a pure function surface:
    ```python
    # _op.py
    async def extract_entities_from_chunks(chunks, model_fn, tokenizer_wrapper, max_glean, summary_tokens, to_json):
        # produce {nodes, edges} without touching storage
        return {"nodes": nodes_list, "edges": edges_list}
    ```
  - In `GraphRAG.ainsert`, call it once per doc and then upsert nodes/edges into the graph storage; finally batch-upsert entities to VDB if enabled.

- Community summarization
  - Add a single-community helper that matches current `GraphRAG` usage:
    ```python
    # _op.py
    async def summarize_community(node_ids, graph, model_fn, max_tokens, to_json, tokenizer_wrapper):
        # prepare describe string and call model
        return report_json_or_str
    ```
  - In `GraphRAG`, after `graph_storage.clustering()`, fetch schema, loop communities, and call `summarize_community` per community. Upsert each report to `community_reports`.

- Durability flush
  - After inserts and graph/report updates, call:
    ```python
    await self.full_docs.index_done_callback()
    await self.text_chunks.index_done_callback()
    await self.community_reports.index_done_callback()
    if self.entities_vdb: await self.entities_vdb.index_done_callback()
    if self.chunks_vdb: await self.chunks_vdb.index_done_callback()
    await self.chunk_entity_relation_graph.index_done_callback()
    ```

- Defaults and params
  - Change `LLMConfig.model` default to `"gpt-4o-mini"`.
  - In `OpenAIProvider._translate_params`, avoid string checks like `"gpt-5" in model`; prefer a small per-model map for `max_tokens` parameter name.

- Backends scope
  - Limit `StorageConfig.vector_backend` to `{nano, hnswlib}` and raise `NotImplementedError` for others. Expand when implemented.

**Docs and Examples**

- Update `examples/using_config.py` to reflect the new-only flow.
  - Keep it fast: insert a short string, run one query in `global` and one in `naive` mode.
  - Show how to swap LLM/embedding providers via the new config only.

**Tests (New-Only)**

- Add tests that cover the new pipeline surfaces:
  - `get_chunks_v2` returns a list of chunks with expected fields.
  - `extract_entities_from_chunks` returns nodes/edges without storage side effects.
  - `summarize_community` produces a minimal report structure for a toy graph.
  - `GraphRAG` integrates the above: inserts text, clusters, summarizes, and persists to KV/graph/vector stores.

**Risks & Mitigations**

- Mixed paradigms: Old `_op` functions still exist; the new-only wrappers avoid churn while keeping the `GraphRAG` code simple. We can remove the old surfaces in a follow-up once the new ones are stable.
- Provider params: Model-specific quirks can creep in; a small mapping table per provider keeps logic explicit and readable.

Once these adjustments are in, the new-only configuration and provider architecture will read clearly, run end-to-end, and keep surface area small without carrying legacy concerns.
