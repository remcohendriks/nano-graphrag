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
from ._storage import (
    JsonKVStorage,
    NanoVectorDBStorage,
    NetworkXStorage,
)
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
        """Initialize storage backends."""
        # Get global config dict for storage classes
        global_config = self.config.to_dict()
        
        # Initialize KV storage
        self.full_docs = self._get_kv_storage("full_docs", global_config)
        self.text_chunks = self._get_kv_storage("text_chunks", global_config)
        self.community_reports = self._get_kv_storage("community_reports", global_config)
        
        # Initialize LLM cache if enabled
        self.llm_response_cache = (
            self._get_kv_storage("llm_response_cache", global_config)
            if self.config.llm.cache_enabled
            else None
        )
        
        # Initialize graph storage
        self.chunk_entity_relation_graph = self._get_graph_storage(
            "chunk_entity_relation", global_config
        )
        
        # Initialize vector storage
        self.entities_vdb = (
            self._get_vector_storage(
                "entities", 
                global_config,
                meta_fields={"entity_name"}
            )
            if self.config.query.enable_local
            else None
        )
        
        self.chunks_vdb = (
            self._get_vector_storage("chunks", global_config)
            if self.config.query.enable_naive_rag
            else None
        )
    
    def _get_kv_storage(self, namespace: str, global_config: dict) -> BaseKVStorage:
        """Get KV storage instance based on config."""
        if self.config.storage.kv_backend == "json":
            return JsonKVStorage(namespace=namespace, global_config=global_config)
        else:
            raise ValueError(f"Unknown KV backend: {self.config.storage.kv_backend}")
    
    def _get_graph_storage(self, namespace: str, global_config: dict) -> BaseGraphStorage:
        """Get graph storage instance based on config."""
        if self.config.storage.graph_backend == "networkx":
            return NetworkXStorage(namespace=namespace, global_config=global_config)
        else:
            raise ValueError(f"Unknown graph backend: {self.config.storage.graph_backend}")
    
    def _get_vector_storage(
        self, 
        namespace: str, 
        global_config: dict,
        meta_fields: Optional[set] = None
    ) -> BaseVectorStorage:
        """Get vector storage instance based on config."""
        kwargs = {
            "namespace": namespace,
            "global_config": global_config,
            "embedding_func": self.embedding_func,
        }
        if meta_fields:
            kwargs["meta_fields"] = meta_fields
            
        if self.config.storage.vector_backend == "nano":
            return NanoVectorDBStorage(**kwargs)
        elif self.config.storage.vector_backend == "hnswlib":
            # Import dynamically to avoid dependency if not used
            from ._storage import HNSWVectorStorage
            return HNSWVectorStorage(**kwargs)
        else:
            raise ValueError(f"Unknown vector backend: {self.config.storage.vector_backend}")
    
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
                
                # Store entities in graph
                if entities["nodes"]:
                    await self.chunk_entity_relation_graph.upsert_nodes(entities["nodes"])
                if entities["edges"]:
                    await self.chunk_entity_relation_graph.upsert_edges(entities["edges"])
            
            # Store chunks in vector DB if naive RAG is enabled
            if self.config.query.enable_naive_rag and self.chunks_vdb:
                chunk_contents = [c["content"] for c in chunks]
                chunk_ids = [compute_mdhash_id(c, prefix="chunk-") for c in chunk_contents]
                await self.chunks_vdb.upsert(
                    ids=chunk_ids,
                    documents=chunk_contents,
                    metadatas=[{"doc_id": doc_id} for _ in chunks]
                )
        
        # Generate community reports if local query is enabled
        if self.config.query.enable_local:
            await self._generate_community_reports()
        
        # Flush all storage to ensure persistence
        await self._flush_storage()
    
    async def _generate_community_reports(self):
        """Generate community reports for graph clusters."""
        # Get graph clusters using community schema
        try:
            communities = await self.chunk_entity_relation_graph.community_schema()
        except AttributeError:
            # Fallback if community_schema not available
            logger.warning("Graph storage doesn't support community_schema, skipping reports")
            return
        
        # Generate report for each community
        for community_id, node_ids in communities.items():
            if node_ids:  # Only process non-empty communities
                report = await summarize_community(
                    node_ids,
                    self.chunk_entity_relation_graph,
                    self.best_model_func,
                    self.config.llm.max_tokens,
                    self.convert_response_to_json_func,
                    self.tokenizer_wrapper
                )
                await self.community_reports.upsert({f"community-{community_id}": report})
        
        # Update entities vector DB with embeddings
        if self.entities_vdb:
            all_entities = await self.chunk_entity_relation_graph.get_all_nodes()
            entity_texts = [e["description"] for e in all_entities]
            entity_ids = [e["id"] for e in all_entities]
            
            await self.entities_vdb.upsert(
                ids=entity_ids,
                documents=entity_texts,
                metadatas=[{"entity_name": e["name"]} for e in all_entities]
            )
    
    async def aquery(self, query: str, param: QueryParam = QueryParam()):
        """Query asynchronously."""
        # Validate query mode
        if param.mode == "local" and not self.config.query.enable_local:
            raise ValueError("Local query mode is disabled in config")
        if param.mode == "naive" and not self.config.query.enable_naive_rag:
            raise ValueError("Naive RAG mode is disabled in config")
        
        # Execute query based on mode
        if param.mode == "local":
            return await local_query(
                query,
                self.chunk_entity_relation_graph,
                self.entities_vdb,
                self.community_reports,
                self.text_chunks,
                param,
                self.best_model_func,
                self.config.llm.max_tokens,
                self.config.query.similarity_threshold,
                self.convert_response_to_json_func
            )
        elif param.mode == "global":
            return await global_query(
                query,
                self.community_reports,
                self.best_model_func,
                self.config.llm.max_tokens,
                self.convert_response_to_json_func
            )
        elif param.mode == "naive":
            return await naive_query(
                query,
                self.chunks_vdb,
                self.text_chunks,
                param,
                self.best_model_func,
                self.config.llm.max_tokens
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