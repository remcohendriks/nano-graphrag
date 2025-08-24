"""OpenAI LLM Provider implementation."""

import os
from typing import AsyncIterator, Dict, List, Optional
import numpy as np
from openai import AsyncOpenAI, APIConnectionError, RateLimitError
from openai.lib.streaming.chat import ChatCompletionStreamState
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ..base import BaseLLMProvider, BaseEmbeddingProvider


class OpenAIProvider(BaseLLMProvider):
    """OpenAI LLM provider implementation."""
    
    env_key = "OPENAI_API_KEY"
    
    def __init__(
        self,
        model: str = "gpt-5-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs
    ):
        super().__init__(model, api_key, base_url, **kwargs)
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
    )
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> str:
        """Generate completion using OpenAI API."""
        messages = self._build_messages(prompt, system_prompt, history)
        
        # Use max_completion_tokens for gpt-5 models, max_tokens for others
        max_tokens_param = "max_completion_tokens" if "gpt-5" in self.model else "max_tokens"
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=kwargs.get("temperature", self.temperature),
            **{max_tokens_param: kwargs.get("max_tokens", self.max_tokens)},
            **{k: v for k, v in kwargs.items() if k not in ["temperature", "max_tokens"]}
        )
        
        return response.choices[0].message.content
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
    )
    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream completions from OpenAI API."""
        messages = self._build_messages(prompt, system_prompt, history)
        
        # Use max_completion_tokens for gpt-5 models, max_tokens for others
        max_tokens_param = "max_completion_tokens" if "gpt-5" in self.model else "max_tokens"
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=kwargs.get("temperature", self.temperature),
            **{max_tokens_param: kwargs.get("max_tokens", self.max_tokens)},
            **{k: v for k, v in kwargs.items() if k not in ["temperature", "max_tokens", "stream"]}
        )
        
        completion = ChatCompletionStreamState()
        async for chunk in response:
            completion.handle_chunk(chunk)
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI embedding provider."""
    
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        embedding_dim: int = 1536
    ):
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.embedding_dim = embedding_dim
        self.client = AsyncOpenAI(api_key=self.api_key)
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
    )
    async def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings using OpenAI API."""
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            encoding_format="float"
        )
        return np.array([dp.embedding for dp in response.data])


# Factory functions for backward compatibility
async def gpt_4o_complete(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: Optional[List[Dict[str, str]]] = None,
    **kwargs
) -> str:
    """Backward compatible function for gpt-4o completions."""
    provider = OpenAIProvider(model="gpt-5")
    return await provider.complete_with_cache(
        prompt, system_prompt, history_messages, 
        hashing_kv=kwargs.pop("hashing_kv", None),
        **kwargs
    )


async def gpt_4o_mini_complete(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: Optional[List[Dict[str, str]]] = None,
    **kwargs
) -> str:
    """Backward compatible function for gpt-4o-mini completions."""
    provider = OpenAIProvider(model="gpt-5-mini")
    return await provider.complete_with_cache(
        prompt, system_prompt, history_messages,
        hashing_kv=kwargs.pop("hashing_kv", None),
        **kwargs
    )


async def openai_embedding(texts: List[str]) -> np.ndarray:
    """Backward compatible OpenAI embedding function."""
    provider = OpenAIEmbeddingProvider()
    return await provider.embed(texts)