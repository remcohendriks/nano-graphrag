**NGRAF-002 Review — Round 3 (New-Only)**

- Ticket: `tickets/NGRAF-002-config-management-simplification.md`
- Reports: `reports/NGRAF-002-implementation-report.md`, `reports/NGRAF-002-review-fixes.md`, `reports/NGRAF-002-round2-fixes.md`
- Scope: Config system, provider factories, new wrappers, GraphRAG integration

**Summary**

- The wrappers and backend restrictions are good, and persistence is addressed. A few final integration gaps remain in `GraphRAG` (query call signatures, community report flow, vector/graph upserts, prompt key), plus a small default mismatch with CLAUDE.md. These are small, low‑risk changes. After applying them, this looks passable.

**What’s Working**

- Wrappers: `get_chunks_v2`, `extract_entities_from_chunks`, `summarize_community` provide clean boundaries.
- Storage: Implemented backend restrictions (nano/hnswlib + networkx/json).
- Persistence: `_flush_storage()` added and used after inserts.
- Structure: `GraphRAG` remains readable via `_init_*` stages.

**Remaining Issues**

- Query signatures not updated in `GraphRAG.aquery`.
  - Current code passes model/thresholds directly to `_op.local_query/global_query/naive_query`, which expect `tokenizer_wrapper` and a `global_config` dict.
  - Impact: runtime type/signature errors for all query modes.

- Community reports built from wrong schema shape and no clustering.
  - `_generate_community_reports` iterates `for community_id, node_ids in communities.items():` but `community_schema()` returns `SingleCommunitySchema` objects (with `nodes`, `edges`, etc.).
  - Clustering isn’t invoked before `community_schema()`, so the schema may be empty.

- Vector upserts use the wrong interface.
  - `NanoVectorDBStorage.upsert` expects a dict keyed by id containing a `content` field, but code calls `upsert(ids=..., documents=..., metadatas=...)`.

- Graph upsert methods and shapes.
  - Code calls `upsert_nodes`/`upsert_edges`; storage implements `upsert_nodes_batch`/`upsert_edges_batch` and expects specific shapes (including `source_id`).

- Prompt key typo in `extract_entities_from_chunks`.
  - Uses `PROMPTS["entity_extraction_continue"]`; correct key is `"entiti_continue_extraction"` (and optional `"entiti_if_loop_extraction"`).

- Default model vs CLAUDE.md.
  - CLAUDE.md shows `gpt-4o`/`gpt-4o-mini` as baseline. `LLMConfig.model` defaults to `gpt-5-mini`. If this is intentional, note it in docs; otherwise switch to `gpt-4o-mini`.

**Final Fixes (Low Complexity)**

- Pass proper `global_config` and `tokenizer_wrapper` to queries
  ```python
  # graphrag.py
  def _global_config(self) -> dict:
      return {
          "best_model_func": self.best_model_func,
          "cheap_model_func": self.cheap_model_func,
          "convert_response_to_json_func": self.convert_response_to_json_func,
      }

  async def aquery(self, query: str, param: QueryParam = QueryParam()):
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

- Use the canonical community report pipeline
  ```python
  # graphrag.py
  async def _generate_community_reports(self):
      # cluster first
      await self.chunk_entity_relation_graph.clustering(
          self.config.graph_clustering.algorithm
      )
      # then use original generator which normalizes {report_json, report_string, nodes, edges, occurrence}
      await generate_community_report(
          self.community_reports,
          self.chunk_entity_relation_graph,
          self.tokenizer_wrapper,
          {
              **self.config.to_dict(),
              "best_model_func": self.best_model_func,
              "convert_response_to_json_func": self.convert_response_to_json_func,
              "special_community_report_llm_kwargs": {},
          },
      )
  ```

- Fix vector upserts for chunks
  ```python
  if self.config.query.enable_naive_rag and self.chunks_vdb:
      chunk_data = {
          compute_mdhash_id(c["content"], prefix="chunk-"): {
              "content": c["content"],
              "doc_id": doc_id,
          }
          for c in chunks
      }
      await self.chunks_vdb.upsert(chunk_data)
  ```

- Batch upsert graph nodes/edges with expected shapes
  ```python
  # nodes
  node_items = [
      (
          n["id"],
          {
              "entity_type": n.get("type", "UNKNOWN").upper(),
              "description": n.get("description", ""),
              "source_id": doc_id,
              "name": n.get("name", n["id"]),
          },
      )
      for n in entities["nodes"]
  ]
  if node_items:
      await self.chunk_entity_relation_graph.upsert_nodes_batch(node_items)

  # edges
  edge_items = []
  for e in entities["edges"]:
      src = e.get("source") or e.get("from")
      tgt = e.get("target") or e.get("to")
      if not src or not tgt:
          continue
      edge_items.append(
          (
              src,
              tgt,
              {
                  "weight": 1.0,
                  "description": e.get("description", ""),
                  "source_id": doc_id,
              },
          )
      )
  if edge_items:
      await self.chunk_entity_relation_graph.upsert_edges_batch(edge_items)
  ```

- Correct the prompt key in `extract_entities_from_chunks`
  ```python
  # _op.py
  # replace: PROMPTS["entity_extraction_continue"]
  # with:
  PROMPTS["entiti_continue_extraction"]
  # optionally add a loop check via PROMPTS["entiti_if_loop_extraction"] if needed
  ```

- Defaults
  - If aligning to CLAUDE.md: set `LLMConfig.model = "gpt-4o-mini"`.
  - If intentionally keeping `gpt-5-mini`, note this deviation in docs to avoid surprise.

**Nits / Polish**

- Logging: add compact logs for cluster counts and per-community report progress; log counts for node/edge upserts.
- Examples: simplify `examples/using_config.py` to a short insert and one query per mode; keep it fast.
- Tests: add light tests for wrappers (`get_chunks_v2`, `extract_entities_from_chunks`) and a smoke test that runs `GraphRAG.insert()` + `query()` in `naive` mode with a dummy embed/model.

**Verdict**

- Close to green. Apply the small integration fixes above and this should be a passable PR with a clear, readable new-only pipeline that matches the documented contracts in CLAUDE.md.

