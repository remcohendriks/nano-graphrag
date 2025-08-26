**NGRAF-002 Review — Round 2 (New-Only)**

- Ticket: `tickets/NGRAF-002-config-management-simplification.md`
- Reports: `reports/NGRAF-002-implementation-report.md`, `reports/NGRAF-002-review-fixes.md`
- Scope: Config system, provider factories, new wrappers (`get_chunks_v2`, `extract_entities_from_chunks`, `summarize_community`), GraphRAG integration

**Summary**

- Good progress: the new wrappers and backend restrictions simplify the API and reduce side effects. However, GraphRAG’s integration has several functional mismatches with the ops/storage layer (query call signatures, community schema handling, vector upserts, and prompt keys). Addressing these with small, targeted changes will make the new-only pipeline run end-to-end with low complexity and high readability.

**What Improved**

- Wrappers: `get_chunks_v2`, `extract_entities_from_chunks`, `summarize_community` add clean, side‑effect‑free surfaces.
- Backends: `StorageConfig` now restricts to implemented backends only (nano/hnswlib + networkx/json).
- Persistence: `_flush_storage()` ensures KV/graph/vector stores are saved.
- Structure: `GraphRAG` setup remains readable via `_init_*` helpers.

**Blocking Issues**

- Local/Global/Naive query call signatures mismatch `_op` functions.
  - In `GraphRAG.aquery`, the calls to `local_query/global_query/naive_query` don’t match the updated signatures that require `tokenizer_wrapper` and a `global_config` dict. This will error at runtime.

- Community schema usage is incorrect and clustering is skipped.
  - `_generate_community_reports` fetches `community_schema()` but doesn’t call `clustering()` first; on a fresh graph this likely returns empty.
  - The loop treats each schema value as a node-id list, but values are `SingleCommunitySchema` objects. Passing them to `summarize_community` will break.

- Vector DB upserts use the wrong interface.
  - `NanoVectorDBStorage.upsert(data: dict)` is called with `ids=..., documents=..., metadatas=...` (OpenAI-style). Needs a dict payload keyed by id with a `content` field.

- Graph API mismatch for nodes/edges upsert.
  - `GraphRAG` calls `upsert_nodes` / `upsert_edges`, but storage defines `upsert_nodes_batch` / `upsert_edges_batch` and expects specific shapes (including `source_id` on nodes/edges used downstream).

- Extract prompt key typo.
  - `extract_entities_from_chunks` uses `PROMPTS["entity_extraction_continue"]`, but prompts expose `"entiti_continue_extraction"` and `"entiti_if_loop_extraction"`.

- Global report shape mismatch.
  - `global_query` expects community reports shaped with `report_json`, `report_string`, `nodes`, `edges`, `occurrence`, etc. The new `summarize_community` output isn’t normalized to that schema, so global queries will not work as written.

- Default LLM model diverges from guidelines.
  - `LLMConfig.model` default is `"gpt-5-mini"`, while the documented baseline is `gpt-4o` / `gpt-4o-mini`.

**Low-Complexity Fixes (Concrete Snippets)**

- Build `global_config` once and pass correct params to queries
  - Add a helper in `GraphRAG`:
    ```python
    def _global_config(self) -> dict:
        return {
            "best_model_func": self.best_model_func,
            "cheap_model_func": self.cheap_model_func,
            "convert_response_to_json_func": self.convert_response_to_json_func,
        }
    ```
  - Update `aquery` calls:
    ```python
    if param.mode == "local":
        return await local_query(
            query,
            self.chunk_entity_relation_graph,
            self.entities_vdb,
            self.community_reports,
            self.text_chunks,
            param,
            self.tokenizer_wrapper,
            self._global_config(),
        )

    elif param.mode == "global":
        return await global_query(
            query,
            self.chunk_entity_relation_graph,
            self.entities_vdb,
            self.community_reports,
            self.text_chunks,
            param,
            self.tokenizer_wrapper,
            self._global_config(),
        )

    elif param.mode == "naive":
        return await naive_query(
            query,
            self.chunks_vdb,
            self.text_chunks,
            param,
            self.tokenizer_wrapper,
            self._global_config(),
        )
    ```

- Cluster before building community schema and pass the right data
  - Replace `_generate_community_reports` with:
    ```python
    async def _generate_community_reports(self):
        await self.chunk_entity_relation_graph.clustering(
            self.config.graph_clustering.algorithm
        )
        schema = await self.chunk_entity_relation_graph.community_schema()
        for key, comm in schema.items():
            node_ids = comm["nodes"]
            report_json = await summarize_community(
                node_ids,
                self.chunk_entity_relation_graph,
                self.best_model_func,
                self.config.llm.max_tokens,
                self.convert_response_to_json_func,
                self.tokenizer_wrapper,
            )
            report_str = _community_report_json_to_str(report_json)
            await self.community_reports.upsert({
                key: {
                    "report_string": report_str,
                    "report_json": report_json,
                    **comm,
                }
            })
    ```
    - Note: `_community_report_json_to_str` exists in `_op.py`; reuse it to normalize report text.

- Fix vector upserts for chunks and entities
  - Chunks:
    ```python
    if self.config.query.enable_naive_rag and self.chunks_vdb:
        data = {
            compute_mdhash_id(c["content"], "chunk-"): {
                "content": c["content"],
                "doc_id": doc_id,
            }
            for c in chunks
        }
        await self.chunks_vdb.upsert(data)
    ```
  - Entities: set meta to `name` and gather nodes from schema
    ```python
    # When creating entities VDB
    self.entities_vdb = self._get_vector_storage("entities", global_config, meta_fields={"name"})

    # After reports
    all_nodes = sorted({n for c in schema.values() for n in c["nodes"]})
    nodes = await self.chunk_entity_relation_graph.get_nodes_batch(all_nodes)
    data = {}
    for i, node in enumerate(nodes):
        if not node: continue
        nid = all_nodes[i]
        name = node.get("name", nid)
        desc = node.get("description", "")
        data[nid] = {"content": f"{name} {desc}", "name": name}
    if data:
        await self.entities_vdb.upsert(data)
    ```

- Use the correct graph upsert methods and include required fields
  - Transform results from `extract_entities_from_chunks` to storage shape and batch upsert:
    ```python
    # nodes: expect {id -> {entity_type, description, source_id}}
    node_items = []
    for n in entities["nodes"]:
        node_items.append((n["id"], {
            "entity_type": n.get("type", "UNKNOWN").upper(),
            "description": n.get("description", ""),
            "source_id": doc_id,
            "name": n.get("name", n["id"]),
        }))
    if node_items:
        await self.chunk_entity_relation_graph.upsert_nodes_batch(node_items)

    # edges: expect (src, tgt, {weight, description, source_id})
    edge_items = []
    for e in entities["edges"]:
        src = e.get("source") or e.get("from")
        tgt = e.get("target") or e.get("to")
        if not src or not tgt: continue
        edge_items.append((src, tgt, {
            "weight": 1.0,
            "description": e.get("description", ""),
            "source_id": doc_id,
        }))
    if edge_items:
        await self.chunk_entity_relation_graph.upsert_edges_batch(edge_items)
    ```

- Fix prompt key for continued extraction
  - In `extract_entities_from_chunks`, replace `entity_extraction_continue` with `entiti_continue_extraction` and add the optional loop check with `entiti_if_loop_extraction` if you want multi‑glean behavior.

- Align default LLM model with docs
  - In `LLMConfig`, set `model="gpt-4o-mini"` by default to match the documented baseline.

**Polish & Readability**

- Logging: add concise logs in `_generate_community_reports` for cluster counts and report progress; and in `ainsert` for nodes/edges upsert sizes.
- Examples: update `examples/using_config.py` to demonstrate the new-only path and ensure it runs after the fixes.
- Tests: add targeted tests for `get_chunks_v2`, `extract_entities_from_chunks`, and `summarize_community`; update integration tests to use the config constructor and new query call shapes.

**Verdict**

- The architectural direction is strong. With the small integration fixes above (query signatures, community schema handling, graph/vector upserts, prompt key), the new-only pipeline will work end‑to‑end while staying simple and readable. Aligning LLM defaults with the docs will also remove surprises for users.

