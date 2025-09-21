"""Qdrant vector storage implementation."""

import asyncio
import os
import xxhash
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from ..base import BaseVectorStorage
from .._utils import logger, ensure_dependency


@dataclass
class QdrantVectorStorage(BaseVectorStorage):
    """Qdrant vector storage backend using AsyncQdrantClient."""
    
    def __post_init__(self):
        """Initialize Qdrant client and collection."""
        ensure_dependency("qdrant_client", "qdrant-client", "Qdrant vector storage")

        from qdrant_client import AsyncQdrantClient, models

        # Check Qdrant client version for hybrid search compatibility
        try:
            import qdrant_client
            client_version = qdrant_client.__version__
            major, minor = map(int, client_version.split('.')[:2])
            if major < 1 or (major == 1 and minor < 10):
                logger.warning(
                    f"Qdrant client version {client_version} detected. "
                    f"Hybrid search requires version 1.10.0 or higher. "
                    f"Some features may not work correctly."
                )
        except Exception as e:
            logger.debug(f"Could not check Qdrant version: {e}")

        # Get configuration - check addon_params first, then top-level
        addon_params = self.global_config.get("addon_params", {})
        self._url = addon_params.get("qdrant_url",
                                     self.global_config.get("qdrant_url", "http://localhost:6333"))
        self._api_key = addon_params.get("qdrant_api_key",
                                         self.global_config.get("qdrant_api_key", None))
        self._collection_params = addon_params.get("qdrant_collection_params",
                                                   self.global_config.get("qdrant_collection_params", {}))

        # Store models for later use (needed before client creation)
        self._models = models

        # Defer client creation to avoid potential sync issues
        self._client = None
        self._AsyncQdrantClient = AsyncQdrantClient

        # Collection will be created on first use
        self._collection_initialized = False

        # Get hybrid search config from StorageConfig if available
        from nano_graphrag.config import HybridSearchConfig
        if isinstance(self.global_config, dict) and 'hybrid_search' in self.global_config:
            self._hybrid_config = self.global_config['hybrid_search']
        elif hasattr(self.global_config, 'hybrid_search'):
            self._hybrid_config = self.global_config.hybrid_search
        else:
            # Fallback to env-based config for backward compatibility
            self._hybrid_config = HybridSearchConfig.from_env()

        self._enable_hybrid = self._hybrid_config.enabled

        logger.info(f"Initialized Qdrant storage for namespace: {self.namespace}")
    
    async def _get_client(self):
        """Get or create the Qdrant client."""
        if self._client is None:
            self._client = self._AsyncQdrantClient(
                url=self._url,
                api_key=self._api_key
            )
        return self._client
    
    async def _ensure_collection(self):
        """Ensure collection exists with proper configuration."""
        if self._collection_initialized:
            return

        logger.debug(f"Checking if Qdrant collection '{self.namespace}' exists...")

        # Get client
        client = await self._get_client()

        # Check if collection exists
        collections = await client.get_collections()
        exists = any(c.name == self.namespace for c in collections.collections)

        if not exists:
            logger.info(f"Creating Qdrant collection: {self.namespace}")
            try:
                # Configure vectors for dense or hybrid
                if self._enable_hybrid:
                    vectors_config = {
                        "dense": self._models.VectorParams(
                            size=self.embedding_func.embedding_dim,
                            distance=self._models.Distance.COSINE
                        ),
                        "sparse": self._models.SparseVectorParams()
                    }
                    logger.info(f"Creating hybrid collection with dense and sparse vectors")
                else:
                    vectors_config = self._models.VectorParams(
                        size=self.embedding_func.embedding_dim,
                        distance=self._models.Distance.COSINE
                    )

                await client.create_collection(
                    collection_name=self.namespace,
                    vectors_config=vectors_config,
                    **self._collection_params
                )
                logger.info(f"Created Qdrant collection: {self.namespace}")
            except Exception as e:
                # Handle race condition where another process created it
                if "already exists" in str(e).lower() or "conflict" in str(e).lower():
                    logger.debug(f"Collection {self.namespace} was created by another process")
                else:
                    raise
        else:
            logger.debug(f"Qdrant collection '{self.namespace}' already exists")

        self._collection_initialized = True
    
    async def upsert(self, data: Dict[str, Dict]):
        """Upsert vectors to Qdrant collection."""
        if not data:
            logger.warning("Empty data provided for upsert")
            return
        
        await self._ensure_collection()
        logger.info(f"Inserting {len(data)} vectors to {self.namespace}")
        
        # Prepare points
        points = []
        contents_to_embed = []
        keys_to_embed = []
        
        # First pass: collect items that need embeddings
        for content_key, content_data in data.items():
            if "embedding" not in content_data:
                # Need to generate embedding from content
                content = content_data.get("content", "")
                contents_to_embed.append(content)
                keys_to_embed.append(content_key)
        
        if contents_to_embed:
            logger.debug(f"Generating {len(contents_to_embed)} embeddings")
        
        # Generate embeddings in batch if needed
        if contents_to_embed:
            embeddings = await self.embedding_func(contents_to_embed)
        else:
            embeddings = []

        # Generate sparse embeddings if hybrid enabled
        sparse_embeddings = None
        if self._enable_hybrid:
            from ..llm.providers.sparse import SparseEmbeddingProvider
            provider = SparseEmbeddingProvider(config=self._hybrid_config)
            all_contents = [d.get("content", "") for d in data.values()]
            sparse_embeddings = await provider.embed(all_contents)
            logger.debug(f"Generated sparse embeddings for {len(all_contents)} documents")

        # Second pass: create points
        embedding_idx = 0
        sparse_idx = 0
        
        for content_key, content_data in data.items():
            # Use xxhash for deterministic ID generation
            point_id = xxhash.xxh64_intdigest(content_key.encode())
            
            # Get or use provided embedding
            if "embedding" in content_data:
                embedding = content_data["embedding"]
            else:
                embedding = embeddings[embedding_idx]
                embedding_idx += 1
            
            # Convert numpy array to list if needed
            if hasattr(embedding, 'tolist'):
                embedding = embedding.tolist()
            
            # Prepare payload (all fields except embedding)
            payload = {
                "id": content_key,  # Store original key for retrieval
                "content": content_data.get("content", content_key),
                **{k: v for k, v in content_data.items() if k not in ["embedding", "content"]}
            }
            
            # Add metadata fields if specified
            for field in self.meta_fields:
                if field in content_data and field not in payload:
                    payload[field] = content_data[field]

            # Create point with dense or hybrid vectors
            if self._enable_hybrid and sparse_embeddings:
                vector_data = {
                    "dense": embedding,
                    "sparse": self._models.SparseVector(
                        indices=sparse_embeddings[sparse_idx]["indices"],
                        values=sparse_embeddings[sparse_idx]["values"]
                    )
                }
                sparse_idx += 1
            else:
                vector_data = embedding

            points.append(
                self._models.PointStruct(
                    id=point_id,
                    vector=vector_data,
                    payload=payload
                )
            )
        
        # Upsert to Qdrant in batches
        batch_size = 100  # Configurable batch size for better performance
        total_batches = (len(points) + batch_size - 1) // batch_size
        
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            client = await self._get_client()
            await client.upsert(
                collection_name=self.namespace,
                points=batch,
                wait=True  # Ensure consistency
            )
            
            if batch_num % 10 == 0 or batch_num == total_batches:
                logger.debug(f"Upserted batch {batch_num}/{total_batches}")
        
        logger.info(f"Successfully upserted {len(points)} points to Qdrant")
    
    async def _query_hybrid(self, client, query: str, query_embedding: list, top_k: int):
        """Execute hybrid search with sparse and dense vectors."""
        from ..llm.providers.sparse import SparseEmbeddingProvider
        provider = SparseEmbeddingProvider(config=self._hybrid_config)
        sparse_result = await provider.embed([query])
        sparse_data = sparse_result[0]

        if not sparse_data["indices"]:
            logger.debug("Sparse embedding empty, using dense-only")
            return await self._query_dense(client, query_embedding, top_k, use_named=True)

        logger.debug(f"Hybrid search with {len(sparse_data['indices'])} sparse dimensions")
        return await client.query_points(
            collection_name=self.namespace,
            prefetch=[
                self._models.Prefetch(
                    query=self._models.SparseVector(
                        indices=sparse_data["indices"],
                        values=sparse_data["values"]
                    ),
                    using="sparse",
                    limit=min(int(top_k * self._hybrid_config.sparse_top_k_multiplier), 100),
                ),
                self._models.Prefetch(
                    query=query_embedding,
                    using="dense",
                    limit=min(int(top_k * self._hybrid_config.dense_top_k_multiplier), 50),
                ),
            ],
            query=self._models.FusionQuery(fusion=self._models.Fusion.RRF),
            limit=top_k,
            with_payload=True
        )

    async def _query_dense(self, client, query_embedding: list, top_k: int, use_named: bool = False):
        """Execute dense-only search."""
        query_vector = ("dense", query_embedding) if use_named else query_embedding
        return await client.query_points(
            collection_name=self.namespace,
            query=query_vector,
            limit=top_k,
            with_payload=True
        )

    def _format_results(self, response) -> List[Dict[str, Any]]:
        """Format Qdrant response for GraphRAG compatibility."""
        formatted_results = []
        for hit in response.points:
            result = {
                "id": hit.payload.get("id", str(hit.id)),
                "content": hit.payload.get("content", ""),
                "score": hit.score,
                **hit.payload
            }
            formatted_results.append(result)
        return formatted_results

    async def query(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Query Qdrant collection for similar vectors."""
        await self._ensure_collection()

        # Get query embedding
        query_embedding = (await self.embedding_func([query]))[0]
        if hasattr(query_embedding, 'tolist'):
            query_embedding = query_embedding.tolist()

        client = await self._get_client()

        # Execute search
        try:
            if self._enable_hybrid:
                response = await self._query_hybrid(client, query, query_embedding, top_k)
            else:
                response = await self._query_dense(client, query_embedding, top_k)
        except Exception as e:
            if self._enable_hybrid:
                logger.warning(f"Hybrid search failed, falling back to dense: {e}")
                response = await self._query_dense(client, query_embedding, top_k, use_named=True)
            else:
                raise

        # Format and return results
        formatted_results = self._format_results(response)
        logger.debug(f"Query returned {len(formatted_results)} results")
        return formatted_results
    
    async def index_done_callback(self):
        """Called when indexing is complete."""
        # Qdrant persists automatically, but we can force a sync if needed
        logger.info(f"Indexing complete for Qdrant collection: {self.namespace}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close client."""
        if hasattr(self, '_client'):
            if self._client:
                await self._client.close()