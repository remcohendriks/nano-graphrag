"""Base LLM Provider abstraction."""

import os
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional, Any
import numpy as np
from ..base import BaseKVStorage
from .._utils import compute_args_hash


class BaseLLMProvider(ABC):
    """Base class for all LLM providers."""
    
    env_key: str = ""  # Override in subclasses
    
    def __init__(
        self, 
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: int = 32768,
        temperature: float = 0.0,
        **kwargs
    ):
        self.model = model
        self.api_key = api_key or os.getenv(self.env_key)
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.config = kwargs
        
    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> str:
        """Generate a single completion."""
        pass
    
    @abstractmethod
    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream completions."""
        pass
    
    async def complete_with_cache(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        hashing_kv: Optional[BaseKVStorage] = None,
        **kwargs
    ) -> str:
        """Complete with optional caching support."""
        if hashing_kv is not None:
            messages = self._build_messages(prompt, system_prompt, history)
            args_hash = compute_args_hash(self.model, messages)
            cached_result = await hashing_kv.get_by_id(args_hash)
            if cached_result is not None:
                return cached_result["return"]
        
        result = await self.complete(prompt, system_prompt, history, **kwargs)
        
        if hashing_kv is not None:
            await hashing_kv.upsert({
                args_hash: {"return": result, "model": self.model}
            })
            await hashing_kv.index_done_callback()
        
        return result
    
    async def stream_with_cache(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        hashing_kv: Optional[BaseKVStorage] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream with optional caching support."""
        if hashing_kv is not None:
            messages = self._build_messages(prompt, system_prompt, history)
            args_hash = compute_args_hash(self.model, messages)
            cached_result = await hashing_kv.get_by_id(args_hash)
            if cached_result is not None:
                yield cached_result["return"]
                return
        
        full_response = ""
        async for chunk in self.stream(prompt, system_prompt, history, **kwargs):
            full_response += chunk
            yield chunk
        
        if hashing_kv is not None:
            await hashing_kv.upsert({
                args_hash: {"return": full_response, "model": self.model}
            })
    
    def _build_messages(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, str]]:
        """Build message list for API calls."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        return messages


class BaseEmbeddingProvider(ABC):
    """Base class for embedding providers."""
    
    embedding_dim: int = 1536
    max_token_size: int = 8192
    
    @abstractmethod
    async def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for texts."""
        pass