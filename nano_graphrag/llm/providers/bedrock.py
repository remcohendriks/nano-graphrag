"""Amazon Bedrock LLM Provider implementation."""

import os
import json
from typing import AsyncIterator, Dict, List, Optional
import numpy as np
import aioboto3
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ..base import BaseLLMProvider, BaseEmbeddingProvider
from ..._utils import wrap_embedding_func_with_attrs


class BedrockProvider(BaseLLMProvider):
    """Amazon Bedrock LLM provider implementation."""
    
    env_key = "AWS_ACCESS_KEY_ID"  # Uses standard AWS credentials
    
    def __init__(
        self,
        model: str = "us.anthropic.claude-3-sonnet-20240229-v1:0",
        region: Optional[str] = None,
        **kwargs
    ):
        super().__init__(model, **kwargs)
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.session = aioboto3.Session()
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> str:
        """Generate completion using Amazon Bedrock API."""
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": [{"text": prompt}]})
        
        inference_config = {
            "temperature": kwargs.get("temperature", self.temperature),
            "maxTokens": kwargs.get("max_tokens", self.max_tokens),
        }
        
        async with self.session.client(
            "bedrock-runtime",
            region_name=self.region
        ) as bedrock_runtime:
            if system_prompt:
                response = await bedrock_runtime.converse(
                    modelId=self.model,
                    messages=messages,
                    inferenceConfig=inference_config,
                    system=[{"text": system_prompt}]
                )
            else:
                response = await bedrock_runtime.converse(
                    modelId=self.model,
                    messages=messages,
                    inferenceConfig=inference_config,
                )
        
        return response["output"]["message"]["content"][0]["text"]
    
    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream completions from Amazon Bedrock API."""
        # Bedrock streaming requires different implementation per model
        # For now, return complete response as single chunk
        result = await self.complete(prompt, system_prompt, history, **kwargs)
        yield result


class BedrockEmbeddingProvider(BaseEmbeddingProvider):
    """Amazon Bedrock embedding provider."""
    
    def __init__(
        self,
        model: str = "amazon.titan-embed-text-v2:0",
        region: Optional[str] = None,
        embedding_dim: int = 1024
    ):
        self.model = model
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.embedding_dim = embedding_dim
        self.session = aioboto3.Session()
    
    @wrap_embedding_func_with_attrs(embedding_dim=1024, max_token_size=8192)
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings using Amazon Bedrock API."""
        async with self.session.client(
            "bedrock-runtime",
            region_name=self.region
        ) as bedrock_runtime:
            embeddings = []
            for text in texts:
                body = json.dumps({
                    "inputText": text,
                    "dimensions": self.embedding_dim,
                })
                response = await bedrock_runtime.invoke_model(
                    modelId=self.model,
                    body=body,
                )
                response_body = await response.get("body").read()
                embeddings.append(json.loads(response_body))
        
        return np.array([dp["embedding"] for dp in embeddings])


def create_amazon_bedrock_complete_function(model_id: str):
    """Factory function for creating Bedrock completion functions."""
    async def bedrock_complete(
        prompt: str,
        system_prompt: Optional[str] = None,
        history_messages: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> str:
        provider = BedrockProvider(model=model_id)
        return await provider.complete_with_cache(
            prompt, system_prompt, history_messages,
            hashing_kv=kwargs.pop("hashing_kv", None),
            **kwargs
        )
    
    bedrock_complete.__name__ = f"{model_id}_complete"
    return bedrock_complete


async def amazon_bedrock_embedding(texts: List[str]) -> np.ndarray:
    """Backward compatible Amazon Bedrock embedding."""
    provider = BedrockEmbeddingProvider()
    return await provider.embed(texts)