"""Azure OpenAI LLM Provider implementation."""

import os
from typing import AsyncIterator, Dict, List, Optional
import numpy as np
from openai import AsyncAzureOpenAI, APIConnectionError, RateLimitError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ..base import BaseLLMProvider, BaseEmbeddingProvider
from ..._utils import wrap_embedding_func_with_attrs, deprecated_llm_function


class AzureOpenAIProvider(BaseLLMProvider):
    """Azure OpenAI LLM provider implementation."""
    
    env_key = "AZURE_OPENAI_API_KEY"
    
    def __init__(
        self,
        model: str = "gpt-5",
        api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        **kwargs
    ):
        super().__init__(model, api_key, **kwargs)
        self.azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
        
        self.client = AsyncAzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.azure_endpoint,
            api_version=self.api_version
        )
    
    @retry(
        stop=stop_after_attempt(3),
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
        """Generate completion using Azure OpenAI API."""
        messages = self._build_messages(prompt, system_prompt, history)
        
        response = await self.client.chat.completions.create(
            model=self.model,  # This is the deployment name in Azure
            messages=messages,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            **{k: v for k, v in kwargs.items() if k not in ["temperature", "max_tokens"]}
        )
        
        return response.choices[0].message.content
    
    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream completions from Azure OpenAI API."""
        messages = self._build_messages(prompt, system_prompt, history)
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            **{k: v for k, v in kwargs.items() if k not in ["temperature", "max_tokens", "stream"]}
        )
        
        async for chunk in response:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content


class AzureOpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """Azure OpenAI embedding provider."""
    
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        embedding_dim: int = 1536
    ):
        self.model = model
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self.azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
        self.embedding_dim = embedding_dim
        
        self.client = AsyncAzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.azure_endpoint,
            api_version=self.api_version
        )
    
    @wrap_embedding_func_with_attrs(embedding_dim=1536, max_token_size=8192)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
    )
    async def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings using Azure OpenAI API."""
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            encoding_format="float"
        )
        return np.array([dp.embedding for dp in response.data])


# Backward compatibility functions
@deprecated_llm_function("nano_graphrag.llm.providers.AzureOpenAIProvider")
async def azure_gpt_4o_complete(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: Optional[List[Dict[str, str]]] = None,
    **kwargs
) -> str:
    """Backward compatible Azure GPT-4o completion.
    
    DEPRECATED: Use AzureOpenAIProvider instead.
    This function will be removed in v0.2.0.
    """
    provider = AzureOpenAIProvider(model="gpt-5")
    return await provider.complete_with_cache(
        prompt, system_prompt, history_messages,
        hashing_kv=kwargs.pop("hashing_kv", None),
        **kwargs
    )


@deprecated_llm_function("nano_graphrag.llm.providers.AzureOpenAIProvider")
async def azure_gpt_4o_mini_complete(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: Optional[List[Dict[str, str]]] = None,
    **kwargs
) -> str:
    """Backward compatible Azure GPT-4o-mini completion.
    
    DEPRECATED: Use AzureOpenAIProvider instead.
    This function will be removed in v0.2.0.
    """
    provider = AzureOpenAIProvider(model="gpt-5-mini")
    return await provider.complete_with_cache(
        prompt, system_prompt, history_messages,
        hashing_kv=kwargs.pop("hashing_kv", None),
        **kwargs
    )


@deprecated_llm_function("nano_graphrag.llm.providers.AzureOpenAIEmbeddingProvider")
async def azure_openai_embedding(texts: List[str]) -> np.ndarray:
    """Backward compatible Azure OpenAI embedding.
    
    DEPRECATED: Use AzureOpenAIEmbeddingProvider instead.
    This function will be removed in v0.2.0.
    """
    provider = AzureOpenAIEmbeddingProvider()
    return await provider.embed(texts)