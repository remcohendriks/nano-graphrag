import asyncio
import os
import time
from functools import partial
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

from .config import GraphRAGConfig
from .llm.providers import get_llm_provider, get_embedding_provider
from ._chunking import (
    chunking_by_token_size,
    get_chunks_v2,
)
from ._community import (
    generate_community_report,
)
from ._extraction import (
    get_relation_patterns,
    map_relation_type,
)
from ._query import (
    local_query,
    global_query,
    naive_query,
)
from ._storage.factory import StorageFactory, _register_backends
from ._utils import (
    EmbeddingFunc,
    compute_mdhash_id,
    limit_async_func_call,
    convert_response_to_json,
    always_get_an_event_loop,
    logger,
    TokenizerWrapper,
)
from .base import (
    BaseGraphStorage,
    BaseVectorStorage,
    QueryParam,
)


class GraphRAG:
    """GraphRAG with simplified configuration management."""
    
    def __init__(self, config: Optional[GraphRAGConfig] = None):
        """Initialize GraphRAG with configuration object.

        Args:
            config: GraphRAGConfig object. If None, uses defaults.
        """
        self.config = config or GraphRAGConfig()
        self._init_working_dir()
        self._init_tokenizer()
        self._init_providers()
        self._init_storage()
        self._init_functions()
        self._init_extractor()

        logger.info(f"GraphRAG initialized with config: {self.config}")
    
    def _init_working_dir(self):
        """Initialize working directory."""
        working_dir = Path(self.config.storage.working_dir)
        if not working_dir.exists():
            logger.info(f"Creating working directory {working_dir}")
            working_dir.mkdir(parents=True, exist_ok=True)
        self.working_dir = str(working_dir)
    
    def _init_tokenizer(self):
        """Initialize tokenizer wrapper."""
        self.tokenizer_wrapper = TokenizerWrapper(
            tokenizer_type=self.config.chunking.tokenizer,
            model_name=self.config.chunking.tokenizer_model
        )
    
    def _init_providers(self):
        """Initialize LLM and embedding providers."""
        # Get LLM provider
        self.llm_provider = get_llm_provider(
            provider_type=self.config.llm.provider,
            model=self.config.llm.model,
            config=self.config.llm
        )
        
        # Get embedding provider
        self.embedding_provider = get_embedding_provider(
            provider_type=self.config.embedding.provider,
            model=self.config.embedding.model,
            config=self.config.embedding
        )
        
        # Create function wrappers for compatibility
        # These need to handle the hashing_kv parameter that will be added by _init_functions
        async def best_model_wrapper(prompt, system_prompt=None, history=None, **kwargs):
            hashing_kv = kwargs.pop("hashing_kv", None)
            return await self.llm_provider.complete_with_cache(
                prompt, system_prompt, history, hashing_kv=hashing_kv, **kwargs
            )
        
        async def cheap_model_wrapper(prompt, system_prompt=None, history=None, **kwargs):
            hashing_kv = kwargs.pop("hashing_kv", None)
            return await self.llm_provider.complete_with_cache(
                prompt, system_prompt, history, hashing_kv=hashing_kv, **kwargs
            )
        
        self.best_model_func = best_model_wrapper
        self.cheap_model_func = cheap_model_wrapper
        
        # Create embedding wrapper that returns np.ndarray directly
        async def embedding_wrapper(texts):
            response = await self.embedding_provider.embed(texts)
            return response["embeddings"]
        
        # Wrap embedding function with attributes for compatibility
        self.embedding_func = EmbeddingFunc(
            embedding_dim=self.config.embedding.dimension,
            max_token_size=8192,  # Default for OpenAI
            func=embedding_wrapper
        )
    
    def _init_storage(self):
        """Initialize storage backends using factory pattern."""
        # Register backends lazily
        _register_backends()
        
        # Get global config dict for storage classes
        global_config = self.config.to_dict()
        
        # Initialize KV storage
        self.full_docs = StorageFactory.create_kv_storage(
            backend=self.config.storage.kv_backend,
            namespace="full_docs",
            global_config=global_config
        )
        self.text_chunks = StorageFactory.create_kv_storage(
            backend=self.config.storage.kv_backend,
            namespace="text_chunks",
            global_config=global_config
        )
        self.community_reports = StorageFactory.create_kv_storage(
            backend=self.config.storage.kv_backend,
            namespace="community_reports",
            global_config=global_config
        )
        
        # Initialize LLM cache if enabled
        self.llm_response_cache = (
            StorageFactory.create_kv_storage(
                backend=self.config.storage.kv_backend,
                namespace="llm_response_cache",
                global_config=global_config
            )
            if self.config.llm.cache_enabled
            else None
        )
        
        # Initialize graph storage
        self.chunk_entity_relation_graph = StorageFactory.create_graph_storage(
            backend=self.config.storage.graph_backend,
            namespace="chunk_entity_relation",
            global_config=global_config
        )
        
        # Create a namespace prefix for vector storage to avoid collisions
        # Use working_dir basename or a custom prefix from environment
        import os
        namespace_prefix = os.getenv("QDRANT_NAMESPACE_PREFIX")
        if not namespace_prefix:
            # Use working directory basename as prefix
            namespace_prefix = Path(self.working_dir).name
        
        # Initialize vector storage with prefixed namespaces
        if self.config.query.enable_local:
            self.entities_vdb = StorageFactory.create_vector_storage(
                backend=self.config.storage.vector_backend,
                namespace=f"{namespace_prefix}_entities",
                global_config=global_config,
                embedding_func=self.embedding_func,
                meta_fields={"entity_name", "entity_type"}
            )
        else:
            self.entities_vdb = None
        
        if self.config.query.enable_naive_rag:
            self.chunks_vdb = StorageFactory.create_vector_storage(
                backend=self.config.storage.vector_backend,
                namespace=f"{namespace_prefix}_chunks",
                global_config=global_config,
                embedding_func=self.embedding_func,
                meta_fields={"doc_id"}
            )
        else:
            self.chunks_vdb = None
    
    
    def _init_functions(self):
        """Initialize rate-limited functions."""
        # Apply rate limiting to embedding function
        self.embedding_func = limit_async_func_call(self.config.embedding.max_concurrent)(
            self.embedding_func
        )
        
        # Apply rate limiting and caching to model functions
        self.best_model_func = limit_async_func_call(self.config.llm.max_concurrent)(
            partial(self.best_model_func, hashing_kv=self.llm_response_cache)
        )
        self.cheap_model_func = limit_async_func_call(self.config.llm.max_concurrent)(
            partial(self.cheap_model_func, hashing_kv=self.llm_response_cache)
        )
        
        # Entity extraction function will be initialized separately
        self.entity_extraction_func = None
        
        # Set chunk function
        self.chunk_func = chunking_by_token_size
        
        # Set conversion function
        self.convert_response_to_json_func = convert_response_to_json

    def _init_extractor(self):
        """Initialize entity extractor based on configuration."""
        from nano_graphrag.entity_extraction.factory import create_extractor

        self.entity_extractor = create_extractor(
            strategy=self.config.entity_extraction.strategy,
            model_func=self.best_model_func,
            model_name=self.config.llm.model,
            entity_types=self.config.entity_extraction.entity_types,
            max_gleaning=self.config.entity_extraction.max_gleaning,
            max_continuation_attempts=self.config.entity_extraction.max_continuation_attempts,
            summary_max_tokens=self.config.entity_extraction.summary_max_tokens
        )

        # Keep compatibility with legacy extraction function
        self.entity_extraction_func = self._extract_entities_wrapper

    async def _extract_entities_wrapper(
        self,
        chunks: Dict[str, Any],
        knwoledge_graph_inst: BaseGraphStorage,
        entity_vdb: BaseVectorStorage,
        tokenizer_wrapper: TokenizerWrapper,
        global_config: Dict[str, Any],
        **kwargs  # Accept but ignore additional args like using_amazon_bedrock
    ) -> Optional[BaseGraphStorage]:
        """Wrapper to use new extractor with legacy interface."""
        from nano_graphrag._extraction import (
            _merge_nodes_then_upsert,
            _merge_edges_then_upsert
        )
        from nano_graphrag._utils import compute_mdhash_id
        from collections import defaultdict

        # Initialize extractor if needed
        await self.entity_extractor.initialize()

        # Extract entities using new abstraction
        result = await self.entity_extractor.extract(chunks)

        # Validate extraction result
        if hasattr(self.entity_extractor, 'validate_result'):
            if not self.entity_extractor.validate_result(result):
                logger.warning("Extraction result validation failed, clamping to configured limits")
                # Clamp to configured maximums
                max_entities = self.entity_extractor.config.max_entities_per_chunk * len(chunks)
                max_edges = self.entity_extractor.config.max_relationships_per_chunk * len(chunks)

                if len(result.nodes) > max_entities:
                    logger.warning(f"Clamping entities from {len(result.nodes)} to {max_entities}")
                    result.nodes = dict(list(result.nodes.items())[:max_entities])

                if len(result.edges) > max_edges:
                    logger.warning(f"Clamping relationships from {len(result.edges)} to {max_edges}")
                    result.edges = result.edges[:max_edges]

        # Convert to legacy format and store
        maybe_nodes = defaultdict(list)
        maybe_edges = defaultdict(list)

        for node_id, node_data in result.nodes.items():
            maybe_nodes[node_id].append(node_data)

        relation_patterns = get_relation_patterns()

        for edge in result.edges:
            src_id, tgt_id, edge_data = edge
            if "relation_type" not in edge_data:
                description = edge_data.get("description", "")
                edge_data["relation_type"] = map_relation_type(description, relation_patterns)
            maybe_edges[(src_id, tgt_id)].append(edge_data)

        # Merge and upsert nodes
        all_entities_data = await asyncio.gather(
            *[
                _merge_nodes_then_upsert(k, v, knwoledge_graph_inst, global_config, tokenizer_wrapper)
                for k, v in maybe_nodes.items()
            ]
        )

        # Merge and upsert edges
        await asyncio.gather(
            *[
                _merge_edges_then_upsert(k[0], k[1], v, knwoledge_graph_inst, global_config, tokenizer_wrapper)
                for k, v in maybe_edges.items()
            ]
        )

        if not len(all_entities_data):
            logger.warning("Didn't extract any entities, maybe your LLM is not working")
            return None

        # Update entity vector DB
        if entity_vdb is not None:
            # Use config setting instead of environment variable
            enable_type_prefix = global_config.get("entity_extraction", {}).get("enable_type_prefix_embeddings", True)

            data_for_vdb = {}
            for dp in all_entities_data:
                entity_id = compute_mdhash_id(dp["entity_name"], prefix="ent-")
                if enable_type_prefix and "entity_type" in dp:
                    content = dp["entity_name"] + f"[{dp['entity_type']}] " + dp["description"]
                else:
                    content = dp["entity_name"] + dp["description"]

                data_for_vdb[entity_id] = {
                    "content": content,
                    "entity_name": dp["entity_name"],
                }

            await entity_vdb.upsert(data_for_vdb)

        return knwoledge_graph_inst

    def insert(self, string_or_strings: Union[str, List[str]]):
        """Insert documents synchronously."""
        loop = always_get_an_event_loop()
        return loop.run_until_complete(self.ainsert(string_or_strings))
    
    def query(self, query: str, param: QueryParam = QueryParam()):
        """Query synchronously."""
        loop = always_get_an_event_loop()
        return loop.run_until_complete(self.aquery(query, param))
    
    async def ainsert(self, string_or_strings: Union[str, List[str]]):
        """Insert documents asynchronously with parallel processing."""
        insert_start = time.time()
        logger.info(f"[INSERT] === Starting ainsert ===")

        if isinstance(string_or_strings, str):
            string_or_strings = [string_or_strings]
            logger.info(f"[INSERT] Processing single document")
        else:
            logger.info(f"[INSERT] Processing {len(string_or_strings)} documents")

        # Create semaphore to limit parallelism based on LLM max concurrent
        max_parallel = self.config.llm.max_concurrent
        logger.info(f"[INSERT] Using parallel processing with max_concurrent={max_parallel}")
        semaphore = asyncio.Semaphore(max_parallel)

        async def process_single_document(doc_string: str, doc_idx: int):
            """Process a single document - can run in parallel."""
            async with semaphore:
                doc_id = compute_mdhash_id(doc_string, prefix="doc-")
                logger.info(f"[INSERT] Document {doc_idx+1}: {doc_id} ({len(doc_string)} chars) - started")

                # Store full document
                await self.full_docs.upsert({doc_id: {"content": doc_string}})

                # Chunk the document
                chunks = await get_chunks_v2(
                    doc_string,
                    self.tokenizer_wrapper,
                    self.chunk_func,
                    self.config.chunking.size,
                    self.config.chunking.overlap
                )
                logger.info(f"[INSERT] Document {doc_idx+1}: Created {len(chunks)} chunks")

                # Store chunks
                for chunk_idx, chunk in enumerate(chunks):
                    # Include doc_id in hash to prevent cross-document chunk collisions
                    chunk_id_content = f"{doc_id}::{chunk['content']}"
                    chunk_id = compute_mdhash_id(chunk_id_content, prefix="chunk-")
                    chunk["doc_id"] = doc_id
                    await self.text_chunks.upsert({chunk_id: chunk})

                # Extract entities if local query is enabled
                if self.config.query.enable_local:
                    extraction_start = time.time()
                    chunk_map = {}
                    for chunk in chunks:
                        # Include doc_id in hash to prevent cross-document chunk collisions
                        chunk_id_content = f"{doc_id}::{chunk['content']}"
                        chunk_id = compute_mdhash_id(chunk_id_content, prefix="chunk-")
                        chunk_map[chunk_id] = chunk

                    await self.entity_extraction_func(
                        chunk_map,
                        self.chunk_entity_relation_graph,
                        self.entities_vdb,
                        self.tokenizer_wrapper,
                        self._global_config(),
                        using_amazon_bedrock=False
                    )
                    extraction_time = time.time() - extraction_start
                    logger.info(f"[INSERT] Document {doc_idx+1}: Entity extraction complete in {extraction_time:.2f}s")

                # Store chunks in vector DB if naive RAG is enabled
                if self.config.query.enable_naive_rag and self.chunks_vdb:
                    chunk_dict = {}
                    for chunk in chunks:
                        # Include doc_id in hash to prevent cross-document chunk collisions
                        chunk_id_content = f"{doc_id}::{chunk['content']}"
                        chunk_id = compute_mdhash_id(chunk_id_content, prefix="chunk-")
                        chunk_dict[chunk_id] = {
                            "content": chunk["content"],
                            "doc_id": doc_id,
                        }
                    await self.chunks_vdb.upsert(chunk_dict)

                logger.info(f"[INSERT] Document {doc_idx+1}: {doc_id} - completed")

        # Process all documents in parallel (limited by semaphore)
        await asyncio.gather(*[
            process_single_document(doc_string, doc_idx)
            for doc_idx, doc_string in enumerate(string_or_strings)
        ])

        logger.info(f"[INSERT] All documents processed, starting clustering...")

        # Generate community reports if local query is enabled (single clustering operation)
        if self.config.query.enable_local:
            logger.info(f"[INSERT] Generating community reports...")
            report_start = time.time()
            await self._generate_community_reports()
            report_time = time.time() - report_start
            logger.info(f"[INSERT] Community reports generated in {report_time:.2f}s")

        # Flush all storage to ensure persistence
        logger.info(f"[INSERT] Flushing storage...")
        await self._flush_storage()
        total_time = time.time() - insert_start
        logger.info(f"[INSERT] === Insert complete in {total_time:.2f}s ===")
    
    async def _generate_community_reports(self):
        """Generate community reports for graph clusters."""
        # First run clustering algorithm
        await self.chunk_entity_relation_graph.clustering(
            algorithm=self.config.graph_clustering.algorithm
        )
        
        # Use the original generate_community_report function for proper format
        global_config = self.config.to_dict()
        global_config["best_model_func"] = self.best_model_func
        global_config["convert_response_to_json_func"] = self.convert_response_to_json_func
        
        # Only add response_format for OpenAI API (not for LMStudio or other local endpoints)
        # LMStudio doesn't support response_format parameter
        import os
        if not os.getenv("LLM_BASE_URL"):  # If no custom base URL, assume OpenAI
            global_config["special_community_report_llm_kwargs"] = {"response_format": {"type": "json_object"}}
        else:
            global_config["special_community_report_llm_kwargs"] = {}
        
        await generate_community_report(
            self.community_reports,
            self.chunk_entity_relation_graph,
            self.tokenizer_wrapper,
            global_config
        )
        
        # Update entities vector DB with embeddings
        if self.entities_vdb and self.config.query.enable_local:
            # Get all unique node IDs from community schema
            schema = await self.chunk_entity_relation_graph.community_schema()
            all_node_ids = sorted({node_id for comm in schema.values() for node_id in comm.get("nodes", [])})

            use_payload_update = (
                hasattr(self.entities_vdb, 'update_payload') and
                (self.config.storage.hybrid_search.enabled
                 if hasattr(self.config.storage, 'hybrid_search')
                 else self.global_config.get("enable_hybrid_search", False))
            )

            if use_payload_update:
                # Payload-only update to preserve embeddings
                from nano_graphrag._utils import compute_mdhash_id
                updates = {}
                for node_id in all_node_ids:
                    try:
                        node_data = await self.chunk_entity_relation_graph.get_node(node_id)
                        if not node_data:
                            continue
                        description = (node_data.get("description", "") or "").strip()
                        if not description:
                            entity_name = (node_data.get("name") or node_id).strip()
                            entity_type = node_data.get("entity_type", "UNKNOWN")
                            description = f"{entity_name} ({entity_type})"

                        entity_name = node_data.get("name", node_id)
                        entity_key = compute_mdhash_id(entity_name, prefix='ent-')
                        updates[entity_key] = {
                            "entity_name": entity_name,
                            "entity_type": node_data.get("entity_type", "UNKNOWN"),
                            "community_description": description,
                        }
                    except Exception as e:
                        logger.debug(f"Could not update {node_id}: {e}")

                if updates:
                    logger.info(f"[COMMUNITY] Updating {len(updates)} entity payloads (preserving vectors)")
                    await self.entities_vdb.update_payload(updates)
            else:
                # Fallback: full re-embedding path (recreates vectors, used when hybrid disabled)
                entity_dict = {}
                for node_id in all_node_ids:
                    # Get individual node data (batch method may not exist)
                    try:
                        node_data = await self.chunk_entity_relation_graph.get_node(node_id)
                        if node_data:
                            # Get description and ensure it's not empty for embedding
                            description = node_data.get("description", "").strip()
                            if not description:
                                # Use entity name and type as fallback content
                                entity_name = node_data.get("name", node_id).strip() if node_data.get("name") else node_id
                                entity_type = node_data.get("entity_type", "UNKNOWN")
                                description = f"{entity_name} ({entity_type})"

                            # Final check to ensure description is not empty
                            if description and description != " (UNKNOWN)":
                                entity_dict[node_id] = {
                                    "content": description,
                                    "entity_name": node_data.get("name", node_id),
                                    "entity_type": node_data.get("entity_type", "UNKNOWN"),
                                }
                            else:
                                logger.debug(f"Skipping entity {node_id} with empty description")
                    except Exception as e:
                        # Node might not exist, skip it
                        logger.debug(f"Could not get node {node_id}: {e}")
                        continue

                if entity_dict:
                    # Generate embeddings for the updated entity descriptions
                    # This ensures both dense and sparse embeddings are created
                    logger.info(f"[COMMUNITY] Updating {len(entity_dict)} entities with new embeddings")
                    await self.entities_vdb.upsert(entity_dict)
    
    def _global_config(self) -> dict:
        """Build global config with all required fields including function references."""
        return {
            **self.config.to_legacy_dict(),
            "best_model_func": self.best_model_func,
            "cheap_model_func": self.cheap_model_func,
            "convert_response_to_json_func": self.convert_response_to_json_func,
        }
    
    async def aquery(self, query: str, param: QueryParam = QueryParam()):
        """Query asynchronously."""
        # Validate query mode
        if param.mode == "local" and not self.config.query.enable_local:
            raise ValueError("Local query mode is disabled in config")
        if param.mode == "naive" and not self.config.query.enable_naive_rag:
            raise ValueError("Naive RAG mode is disabled in config")

        # Use config value for local_max_token_for_text_unit
        param.local_max_token_for_text_unit = self.config.query.local_max_token_for_text_unit
        
        # Override response_format for LMStudio (it doesn't support json_object format)
        import os
        if os.getenv("LLM_BASE_URL") and param.mode == "global":
            # Clear the response_format for LMStudio
            param.global_special_community_map_llm_kwargs = {}
        
        # Get complete global config
        cfg = self._global_config()
        
        # Execute query based on mode
        if param.mode == "local":
            return await local_query(
                query,
                self.chunk_entity_relation_graph,
                self.entities_vdb,
                self.community_reports,
                self.text_chunks,
                param,
                self.tokenizer_wrapper,
                cfg
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
                cfg
            )
        elif param.mode == "naive":
            return await naive_query(
                query,
                self.chunks_vdb,
                self.text_chunks,
                param,
                self.tokenizer_wrapper,
                cfg
            )
        else:
            raise ValueError(f"Unknown query mode: {param.mode}")
    
    async def _flush_storage(self):
        """Flush all storage backends to ensure persistence."""
        # Flush KV storage
        if hasattr(self.full_docs, 'index_done_callback'):
            await self.full_docs.index_done_callback()
        if hasattr(self.text_chunks, 'index_done_callback'):
            await self.text_chunks.index_done_callback()
        if hasattr(self.community_reports, 'index_done_callback'):
            await self.community_reports.index_done_callback()
        if self.llm_response_cache and hasattr(self.llm_response_cache, 'index_done_callback'):
            await self.llm_response_cache.index_done_callback()
        
        # Flush graph storage
        if hasattr(self.chunk_entity_relation_graph, 'index_done_callback'):
            await self.chunk_entity_relation_graph.index_done_callback()
        
        # Flush vector storage
        if self.entities_vdb and hasattr(self.entities_vdb, 'index_done_callback'):
            await self.entities_vdb.index_done_callback()
        if self.chunks_vdb and hasattr(self.chunks_vdb, 'index_done_callback'):
            await self.chunks_vdb.index_done_callback()