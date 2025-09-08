"""Qdrant vector storage implementation."""

import asyncio
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
        
        # Get configuration
        self._url = self.global_config.get("qdrant_url", "http://localhost:6333")
        self._api_key = self.global_config.get("qdrant_api_key", None)
        self._collection_params = self.global_config.get("qdrant_collection_params", {})
        
        # Initialize async client
        self._client = AsyncQdrantClient(
            url=self._url,
            api_key=self._api_key
        )
        
        # Store models for later use
        self._models = models
        
        # Collection will be created on first use
        self._collection_initialized = False
        
        logger.info(f"Initialized Qdrant storage for namespace: {self.namespace}")
    
    async def _ensure_collection(self):
        """Ensure collection exists with proper configuration."""
        if self._collection_initialized:
            return
        
        # Check if collection exists
        collections = await self._client.get_collections()
        exists = any(c.name == self.namespace for c in collections.collections)
        
        if not exists:
            # Create collection with cosine distance
            await self._client.create_collection(
                collection_name=self.namespace,
                vectors_config=self._models.VectorParams(
                    size=self.embedding_func.embedding_dim,
                    distance=self._models.Distance.COSINE
                ),
                **self._collection_params
            )
            logger.info(f"Created Qdrant collection: {self.namespace}")
        
        self._collection_initialized = True
    
    async def upsert(self, data: Dict[str, Dict]):
        """Upsert vectors to Qdrant collection."""
        if not data:
            logger.warning("Empty data provided for upsert")
            return
        
        await self._ensure_collection()
        
        logger.info(f"Upserting {len(data)} vectors to Qdrant collection: {self.namespace}")
        
        # Prepare points
        points = []
        for content_key, content_data in data.items():
            # Use simple hash for ID (positive integer)
            point_id = abs(hash(content_key)) % (10 ** 15)  # Keep it within reasonable range
            
            # Get embedding
            if "embedding" in content_data:
                # Use provided embedding
                embedding = content_data["embedding"]
            else:
                # Generate embedding from content
                embedding = (await self.embedding_func([content_data["content"]]))[0]
            
            # Prepare payload (all fields except embedding)
            payload = {
                "content": content_data.get("content", content_key),
                **{k: v for k, v in content_data.items() if k not in ["embedding", "content"]}
            }
            
            # Add metadata fields if specified
            for field in self.meta_fields:
                if field in content_data and field not in payload:
                    payload[field] = content_data[field]
            
            points.append(
                self._models.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )
            )
        
        # Upsert to Qdrant
        await self._client.upsert(
            collection_name=self.namespace,
            points=points,
            wait=True  # Ensure consistency
        )
        
        logger.info(f"Successfully upserted {len(points)} points to Qdrant")
    
    async def query(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Query Qdrant collection for similar vectors."""
        await self._ensure_collection()
        
        # Get query embedding
        query_embedding = (await self.embedding_func([query]))[0]
        
        # Search in Qdrant
        results = await self._client.search(
            collection_name=self.namespace,
            query_vector=query_embedding,
            limit=top_k,
            with_payload=True
        )
        
        # Format results for GraphRAG compatibility
        formatted_results = []
        for hit in results:
            result = {
                "content": hit.payload.get("content", ""),
                "score": hit.score,  # Qdrant returns similarity score (0-1)
                **hit.payload  # Include all payload fields
            }
            formatted_results.append(result)
        
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
            await self._client.close()