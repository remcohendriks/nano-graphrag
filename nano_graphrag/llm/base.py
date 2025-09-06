"""Base LLM Provider abstraction."""

import os
import asyncio
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional, Any, TypedDict, Union
import numpy as np
from ..base import BaseKVStorage
from .._utils import compute_args_hash
from ..schemas import LLMMessage


# Vendor-neutral parameter definitions
class CompletionParams(TypedDict, total=False):
    """Vendor-neutral completion parameters."""
    max_output_tokens: int  # Maximum tokens to generate
    temperature: float  # Randomness (0.0-2.0)
    top_p: float  # Nucleus sampling
    frequency_penalty: float  # Penalize frequent tokens
    presence_penalty: float  # Penalize already-present tokens
    stop_sequences: List[str]  # Stop generation sequences
    seed: Optional[int]  # Reproducibility seed


class StreamChunk(TypedDict):
    """Standard streaming response chunk."""
    text: str
    finish_reason: Optional[str]


class CompletionResponse(TypedDict):
    """Standard completion response."""
    text: str
    finish_reason: str
    usage: Dict[str, int]  # prompt_tokens, completion_tokens, total_tokens
    raw: Any  # Original vendor response for debugging


# Error hierarchy
class LLMError(Exception):
    """Base exception for LLM operations."""
    pass


class LLMAuthError(LLMError):
    """Authentication or authorization failed."""
    pass


class LLMRateLimitError(LLMError):
    """Rate limit exceeded."""
    retry_after: Optional[float] = None
    
    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMTimeoutError(LLMError):
    """Request timed out."""
    pass


class LLMServerError(LLMError):
    """Server error (5xx)."""
    pass


class LLMBadRequestError(LLMError):
    """Bad request (4xx except auth/rate limit)."""
    pass


class RetryConfig(TypedDict, total=False):
    """Retry configuration."""
    max_retries: int
    retry_on_status: List[int]
    backoff_factor: float
    max_backoff: float


class BaseLLMProvider(ABC):
    """Base class for all LLM providers."""
    
    env_key: str = ""  # Override in subclasses
    
    def __init__(
        self, 
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        request_timeout: float = 30.0,
        connect_timeout: float = 10.0,
        retry_config: Optional[RetryConfig] = None,
        **kwargs
    ):
        self.model = model
        self.api_key = api_key or os.getenv(self.env_key)
        self.base_url = base_url
        self.request_timeout = request_timeout
        self.connect_timeout = connect_timeout
        self.retry_config = retry_config or {
            "max_retries": 3,
            "retry_on_status": [429, 500, 502, 503, 504],
            "backoff_factor": 2.0,
            "max_backoff": 60.0
        }
        self.config = kwargs
        
    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[LLMMessage]] = None,
        params: Optional[CompletionParams] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> CompletionResponse:
        """Generate a single completion with vendor-neutral parameters.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system message
            history: Optional conversation history
            params: Vendor-neutral completion parameters
            timeout: Override request timeout for this call
            **kwargs: Additional provider-specific parameters (discouraged)
            
        Returns:
            CompletionResponse with text, usage, and metadata
            
        Raises:
            LLMAuthError: Authentication failed
            LLMRateLimitError: Rate limit exceeded
            LLMTimeoutError: Request timed out
            LLMServerError: Server error
            LLMBadRequestError: Invalid request
        """
        pass
    
    @abstractmethod
    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[LLMMessage]] = None,
        params: Optional[CompletionParams] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """Stream completions with vendor-neutral parameters.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system message
            history: Optional conversation history
            params: Vendor-neutral completion parameters
            timeout: Override request timeout for this call
            **kwargs: Additional provider-specific parameters (discouraged)
            
        Yields:
            StreamChunk with text and optional finish_reason
            
        Raises:
            Same as complete()
        """
        pass
    
    @abstractmethod
    def _translate_params(self, params: CompletionParams) -> Dict[str, Any]:
        """Translate vendor-neutral params to provider-specific format.
        
        This method MUST be implemented by each provider to map
        vendor-neutral parameter names to their specific API format.
        """
        pass
    
    @abstractmethod
    def _translate_error(self, error: Exception) -> LLMError:
        """Translate vendor-specific errors to standard LLMError types."""
        pass
    
    async def complete_with_cache(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[LLMMessage]] = None,
        hashing_kv: Optional[BaseKVStorage] = None,
        params: Optional[CompletionParams] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> str:
        """Complete with optional caching support."""
        if hashing_kv is not None:
            messages = self._build_messages(prompt, system_prompt, history)
            args_hash = compute_args_hash(self.model, messages)
            cached_result = await hashing_kv.get_by_id(args_hash)
            if cached_result is not None:
                return cached_result["return"]
        
        response = await self.complete(prompt, system_prompt, history, params, timeout, **kwargs)
        result = response["text"]
        
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
        history: Optional[List[LLMMessage]] = None,
        hashing_kv: Optional[BaseKVStorage] = None,
        params: Optional[CompletionParams] = None,
        timeout: Optional[float] = None,
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
        async for chunk in self.stream(prompt, system_prompt, history, params, timeout, **kwargs):
            text = chunk["text"]
            full_response += text
            yield text
        
        if hashing_kv is not None:
            await hashing_kv.upsert({
                args_hash: {"return": full_response, "model": self.model}
            })
    
    def _build_messages(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[LLMMessage]] = None
    ) -> List[LLMMessage]:
        """Build message list for API calls."""
        messages: List[LLMMessage] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        return messages


class EmbeddingResponse(TypedDict):
    """Standard embedding response."""
    embeddings: np.ndarray
    dimensions: int
    model: str
    usage: Dict[str, int]  # prompt_tokens, total_tokens


class BaseEmbeddingProvider(ABC):
    """Base class for embedding providers."""
    
    embedding_dim: int = 1536
    max_token_size: int = 8192
    max_batch_size: int = 100
    env_key: str = ""  # Override in subclasses
    
    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        request_timeout: float = 30.0,
        retry_config: Optional[RetryConfig] = None,
        **kwargs
    ):
        self.model = model
        self.api_key = api_key or os.getenv(self.env_key)
        self.request_timeout = request_timeout
        self.retry_config = retry_config or {
            "max_retries": 3,
            "retry_on_status": [429, 500, 502, 503, 504],
            "backoff_factor": 2.0,
            "max_backoff": 60.0
        }
        self.config = kwargs
    
    @abstractmethod
    async def embed(
        self, 
        texts: List[str],
        timeout: Optional[float] = None
    ) -> EmbeddingResponse:
        """Generate embeddings for texts.
        
        Args:
            texts: List of texts to embed
            timeout: Override request timeout
            
        Returns:
            EmbeddingResponse with embeddings and metadata
            
        Raises:
            LLMAuthError: Authentication failed
            LLMRateLimitError: Rate limit exceeded
            LLMTimeoutError: Request timed out
            LLMServerError: Server error
            LLMBadRequestError: Invalid request
        """
        pass
    
    @abstractmethod
    def _translate_error(self, error: Exception) -> LLMError:
        """Translate vendor-specific errors to standard LLMError types."""
        pass