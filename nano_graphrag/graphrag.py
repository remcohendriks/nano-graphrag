import asyncio
import os
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Dict, List, Optional, Union, cast

from .config import GraphRAGConfig
from .llm.providers import get_llm_provider, get_embedding_provider
from ._op import (
    chunking_by_token_size,
    extract_entities,
    generate_community_report,
    get_chunks,
    get_chunks_v2,
    extract_entities_from_chunks,
    summarize_community,
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
    BaseKVStorage,
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
        self.best_model_func = self.llm_provider.complete
        self.cheap_model_func = self.llm_provider.complete  # Can use different model later
        self.embedding_func = self.embedding_provider.embed
    
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
        
        # Initialize vector storage
        if self.config.query.enable_local:
            self.entities_vdb = StorageFactory.create_vector_storage(
                backend=self.config.storage.vector_backend,
                namespace="entities",
                global_config=global_config,
                embedding_func=self.embedding_func,
                meta_fields={"entity_name", "entity_type"}
            )
        else:
            self.entities_vdb = None
        
        if self.config.query.enable_naive_rag:
            self.chunks_vdb = StorageFactory.create_vector_storage(
                backend=self.config.storage.vector_backend,
                namespace="chunks",
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
        
        # Set entity extraction function
        self.entity_extraction_func = extract_entities
        
        # Set chunk function
        self.chunk_func = chunking_by_token_size
        
        # Set conversion function
        self.convert_response_to_json_func = convert_response_to_json
    
    def insert(self, string_or_strings: Union[str, List[str]]):
        """Insert documents synchronously."""
        loop = always_get_an_event_loop()
        return loop.run_until_complete(self.ainsert(string_or_strings))
    
    def query(self, query: str, param: QueryParam = QueryParam()):
        """Query synchronously."""
        loop = always_get_an_event_loop()
        return loop.run_until_complete(self.aquery(query, param))
    
    async def ainsert(self, string_or_strings: Union[str, List[str]]):
        """Insert documents asynchronously."""
        if isinstance(string_or_strings, str):
            string_or_strings = [string_or_strings]
        
        # Process each document
        for doc_string in string_or_strings:
            doc_id = compute_mdhash_id(doc_string, prefix="doc-")
            logger.info(f"Inserting document {doc_id}")
            
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
            
            # Store chunks
            for chunk in chunks:
                chunk_id = compute_mdhash_id(chunk["content"], prefix="chunk-")
                chunk["doc_id"] = doc_id
                await self.text_chunks.upsert({chunk_id: chunk})
                
            # Extract entities if local query is enabled
            if self.config.query.enable_local:
                entities = await extract_entities_from_chunks(
                    chunks,
                    self.cheap_model_func,
                    self.tokenizer_wrapper,
                    self.config.entity_extraction.max_gleaning,
                    self.config.entity_extraction.summary_max_tokens,
                    self.convert_response_to_json_func
                )
                
                # Store entities in graph using batch upsert with proper shapes
                if entities["nodes"]:
                    node_items = [
                        (
                            node["id"],
                            {
                                "entity_type": node.get("type", "UNKNOWN").upper(),
                                "description": node.get("description", ""),
                                "source_id": doc_id,
                                "name": node.get("name", node["id"]),
                            },
                        )
                        for node in entities["nodes"]
                    ]
                    await self.chunk_entity_relation_graph.upsert_nodes_batch(node_items)
                
                if entities["edges"]:
                    edge_items = []
                    for edge in entities["edges"]:
                        src = edge.get("source") or edge.get("from")
                        tgt = edge.get("target") or edge.get("to")
                        if src and tgt:
                            edge_items.append(
                                (
                                    src,
                                    tgt,
                                    {
                                        "weight": 1.0,
                                        "description": edge.get("description", ""),
                                        "source_id": doc_id,
                                    },
                                )
                            )
                    if edge_items:
                        await self.chunk_entity_relation_graph.upsert_edges_batch(edge_items)
            
            # Store chunks in vector DB if naive RAG is enabled
            if self.config.query.enable_naive_rag and self.chunks_vdb:
                chunk_dict = {}
                for chunk in chunks:
                    chunk_id = compute_mdhash_id(chunk["content"], prefix="chunk-")
                    chunk_dict[chunk_id] = {
                        "content": chunk["content"],
                        "doc_id": doc_id,
                    }
                await self.chunks_vdb.upsert(chunk_dict)
        
        # Generate community reports if local query is enabled
        if self.config.query.enable_local:
            await self._generate_community_reports()
        
        # Flush all storage to ensure persistence
        await self._flush_storage()
    
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
        global_config["special_community_report_llm_kwargs"] = {"response_format": {"type": "json_object"}}
        
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
            
            # Batch fetch node data
            entity_dict = {}
            for node_id in all_node_ids:
                # Get individual node data (batch method may not exist)
                try:
                    node_data = await self.chunk_entity_relation_graph.get_node(node_id)
                    if node_data:
                        entity_dict[node_id] = {
                            "content": node_data.get("description", ""),
                            "entity_name": node_data.get("name", node_id),
                            "entity_type": node_data.get("entity_type", "UNKNOWN"),
                        }
                except:
                    # Node might not exist, skip it
                    continue
            
            if entity_dict:
                await self.entities_vdb.upsert(entity_dict)
    
    def _global_config(self) -> dict:
        """Build global config with all required fields including function references."""
        return {
            **self.config.to_dict(),
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