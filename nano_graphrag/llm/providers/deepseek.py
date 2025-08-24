"""DeepSeek LLM Provider implementation."""

import os
import json
from typing import AsyncIterator, Dict, List, Optional
from openai import AsyncOpenAI, BadRequestError
from openai.lib.streaming.chat import ChatCompletionStreamState

from ..base import BaseLLMProvider


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek LLM provider implementation."""
    
    env_key = "DEEPSEEK_API_KEY"
    base_url = "https://api.deepseek.com"
    
    def __init__(
        self,
        model: str = "deepseek-chat",
        api_key: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=self.base_url,
            **kwargs
        )
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
    
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> str:
        """Generate completion using DeepSeek API."""
        messages = self._build_messages(prompt, system_prompt, history)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                **{k: v for k, v in kwargs.items() if k not in ["temperature", "max_tokens"]}
            )
            return response.choices[0].message.content
        except BadRequestError as e:
            # Handle DeepSeek-specific errors
            raise RuntimeError(f"DeepSeek API error: {e}")
    
    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        knowledge: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream completions from DeepSeek API."""
        # Handle executive order knowledge injection if provided
        if knowledge and system_prompt:
            system_prompt = f"{system_prompt}\n<knowledge>{knowledge}</knowledge>"
        
        messages = self._build_messages(prompt, system_prompt, history)
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            **{k: v for k, v in kwargs.items() if k not in ["temperature", "max_tokens", "stream", "knowledge"]}
        )
        
        completion = ChatCompletionStreamState()
        async for chunk in response:
            completion.handle_chunk(chunk)
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content


# Factory functions for backward compatibility
async def deepseek_model_if_cache(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: Optional[List[Dict[str, str]]] = None,
    **kwargs
) -> str:
    """Backward compatible DeepSeek completion function."""
    model = os.getenv("DEEPSEEK_GOOD_MODEL", "deepseek-chat")
    provider = DeepSeekProvider(model=model)
    return await provider.complete_with_cache(
        prompt, system_prompt, history_messages,
        hashing_kv=kwargs.pop("hashing_kv", None),
        **kwargs
    )


async def stream_deepseek_model_if_cache(
    prompt: str,
    system_prompt: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    **kwargs
) -> AsyncIterator[str]:
    """Backward compatible DeepSeek streaming function."""
    model = os.getenv("DEEPSEEK_GOOD_MODEL", "deepseek-chat")
    provider = DeepSeekProvider(model=model)
    
    # Extract knowledge if provided (for executive orders)
    knowledge = kwargs.pop("knowledge", None)
    
    async for chunk in provider.stream_with_cache(
        prompt, system_prompt, history,
        hashing_kv=kwargs.pop("hashing_kv", None),
        knowledge=knowledge,
        **kwargs
    ):
        yield chunk