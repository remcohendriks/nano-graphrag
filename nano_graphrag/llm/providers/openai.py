"""OpenAI LLM Provider implementation."""

import os
import asyncio
from typing import AsyncIterator, Dict, List, Optional, Any
import numpy as np
from openai import AsyncOpenAI, APIConnectionError, RateLimitError, AuthenticationError, BadRequestError
from openai.lib.streaming.chat import ChatCompletionStreamState
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ..base import (
    BaseLLMProvider, 
    BaseEmbeddingProvider,
    CompletionParams,
    CompletionResponse,
    StreamChunk,
    EmbeddingResponse,
    LLMError,
    LLMAuthError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMServerError,
    LLMBadRequestError
)
from ..._utils import deprecated_llm_function


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
        self.client = AsyncOpenAI(
            api_key=self.api_key, 
            base_url=self.base_url,
            timeout=self.request_timeout,
            max_retries=0  # We handle retries ourselves
        )
    
    def _translate_params(self, params: CompletionParams) -> Dict[str, Any]:
        """Translate vendor-neutral params to OpenAI format."""
        if not params:
            return {}
        
        api_params = {}
        
        # Handle max tokens based on model
        if "max_output_tokens" in params:
            if "gpt-5" in self.model:
                api_params["max_completion_tokens"] = params["max_output_tokens"]
            else:
                api_params["max_tokens"] = params["max_output_tokens"]
        
        # Direct mappings
        if "temperature" in params:
            api_params["temperature"] = params["temperature"]
        if "top_p" in params:
            api_params["top_p"] = params["top_p"]
        if "frequency_penalty" in params:
            api_params["frequency_penalty"] = params["frequency_penalty"]
        if "presence_penalty" in params:
            api_params["presence_penalty"] = params["presence_penalty"]
        if "stop_sequences" in params:
            api_params["stop"] = params["stop_sequences"]
        if "seed" in params:
            api_params["seed"] = params["seed"]
        
        return api_params
    
    def _translate_error(self, error: Exception) -> LLMError:
        """Translate OpenAI errors to standard LLMError types."""
        error_name = error.__class__.__name__
        
        if error_name == "AuthenticationError" or isinstance(error, AuthenticationError):
            return LLMAuthError(str(error))
        elif error_name == "RateLimitError" or isinstance(error, RateLimitError):
            # Try to extract retry-after from headers if available
            retry_after = getattr(error, 'retry_after', None)
            return LLMRateLimitError(str(error), retry_after)
        elif isinstance(error, asyncio.TimeoutError):
            return LLMTimeoutError("Request timed out")
        elif error_name == "APIConnectionError" or isinstance(error, APIConnectionError):
            return LLMServerError(f"Connection error: {error}")
        elif error_name == "BadRequestError" or isinstance(error, BadRequestError):
            return LLMBadRequestError(str(error))
        elif hasattr(error, 'status_code'):
            status = getattr(error, 'status_code', 500)
            if status >= 500:
                return LLMServerError(str(error))
            elif status >= 400:
                return LLMBadRequestError(str(error))
        return LLMError(str(error))
    
    async def _retry_with_backoff(self, func, *args, **kwargs):
        """Retry with exponential backoff based on retry config."""
        last_error = None
        for attempt in range(self.retry_config["max_retries"]):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = self._translate_error(e)
                if isinstance(last_error, (LLMRateLimitError, LLMServerError, LLMTimeoutError)):
                    if attempt < self.retry_config["max_retries"] - 1:
                        wait_time = min(
                            self.retry_config["backoff_factor"] ** attempt,
                            self.retry_config["max_backoff"]
                        )
                        if isinstance(last_error, LLMRateLimitError) and last_error.retry_after:
                            wait_time = last_error.retry_after
                        await asyncio.sleep(wait_time)
                        continue
                raise last_error
        raise last_error
    
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        params: Optional[CompletionParams] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> CompletionResponse:
        """Generate completion using OpenAI API."""
        messages = self._build_messages(prompt, system_prompt, history)
        api_params = self._translate_params(params or {})
        
        # Handle max_tokens in kwargs
        if "max_tokens" in kwargs:
            max_tokens = kwargs.pop("max_tokens")
            if "gpt-5" in self.model:
                kwargs["max_completion_tokens"] = max_tokens
            else:
                # For non-GPT-5 models (including LMStudio), use max_tokens directly
                kwargs["max_tokens"] = max_tokens
        
        # Merge kwargs but api_params take precedence
        final_params = {**kwargs, **api_params}
        
        # Add reasoning_effort for GPT-5 models to get faster responses
        if "gpt-5" in self.model and "reasoning_effort" not in final_params:
            final_params["reasoning_effort"] = "minimal"
        
        # Ensure we have enough tokens for GPT-5 models
        if "gpt-5" in self.model:
            if "max_completion_tokens" not in final_params and "max_tokens" not in final_params:
                final_params["max_completion_tokens"] = 2000  # Default for GPT-5
        else:
            # For non-GPT-5 models, ensure max_tokens is set to prevent context overflow
            if "max_tokens" not in final_params:
                final_params["max_tokens"] = 2000  # Default for other models
        
        async def _make_request():
            return await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    **final_params
                ),
                timeout=timeout or self.request_timeout
            )
        
        try:
            response = await self._retry_with_backoff(_make_request)
        except LLMError:
            raise
        except Exception as e:
            raise self._translate_error(e)
        
        # Handle potentially None content from GPT-5 models
        content = response.choices[0].message.content
        if content is None:
            content = ""
            # Log warning for debugging
            import logging
            logging.warning(f"Got None content from {self.model}, finish_reason: {response.choices[0].finish_reason}")
        
        return CompletionResponse(
            text=content,
            finish_reason=response.choices[0].finish_reason,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            },
            raw=response
        )
    
    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        params: Optional[CompletionParams] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """Stream completions from OpenAI API with per-chunk idle timeout."""
        messages = self._build_messages(prompt, system_prompt, history)
        api_params = self._translate_params(params or {})

        # Merge kwargs but api_params take precedence
        final_params = {**kwargs, **api_params, "stream": True}

        # Add reasoning_effort for GPT-5 models
        if "gpt-5" in self.model and "reasoning_effort" not in final_params:
            final_params["reasoning_effort"] = "minimal"

        # Ensure we have enough tokens for GPT-5 models
        if "gpt-5" in self.model:
            if "max_completion_tokens" not in final_params and "max_tokens" not in final_params:
                final_params["max_completion_tokens"] = 2000
        else:
            if "max_tokens" not in final_params:
                final_params["max_tokens"] = 2000

        # Use idle timeout (per-chunk) instead of global timeout
        idle_timeout = timeout or self.request_timeout

        async def _make_request():
            # No wait_for wrapper - let the stream run as long as needed
            return await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                **final_params
            )

        try:
            response = await self._retry_with_backoff(_make_request)
        except LLMError:
            raise
        except Exception as e:
            raise self._translate_error(e)

        # Iterate with per-chunk idle timeout
        completion = ChatCompletionStreamState()
        ait = response.__aiter__()

        try:
            while True:
                try:
                    # Only timeout if no chunk arrives within idle_timeout seconds
                    chunk = await asyncio.wait_for(ait.__anext__(), timeout=idle_timeout)
                    completion.handle_chunk(chunk)
                    if chunk.choices and chunk.choices[0].delta.content is not None:
                        yield StreamChunk(
                            text=chunk.choices[0].delta.content,
                            finish_reason=chunk.choices[0].finish_reason
                        )
                except StopAsyncIteration:
                    break  # Normal end of stream
                except asyncio.TimeoutError:
                    raise LLMTimeoutError(f"No data received for {idle_timeout}s during stream - connection may be stalled")
        except LLMError:
            raise
        except Exception as e:
            raise self._translate_error(e)


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI embedding provider."""
    
    env_key = "OPENAI_API_KEY"
    
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        embedding_dim: int = 1536,
        **kwargs
    ):
        super().__init__(model, api_key, **kwargs)
        self.embedding_dim = embedding_dim
        self.base_url = base_url
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.request_timeout,
            max_retries=0  # We handle retries ourselves
        )
    
    def _translate_error(self, error: Exception) -> LLMError:
        """Translate OpenAI errors to standard LLMError types."""
        error_name = error.__class__.__name__
        
        if error_name == "AuthenticationError" or isinstance(error, AuthenticationError):
            return LLMAuthError(str(error))
        elif error_name == "RateLimitError" or isinstance(error, RateLimitError):
            retry_after = getattr(error, 'retry_after', None)
            return LLMRateLimitError(str(error), retry_after)
        elif isinstance(error, asyncio.TimeoutError):
            return LLMTimeoutError("Request timed out")
        elif error_name == "APIConnectionError" or isinstance(error, APIConnectionError):
            return LLMServerError(f"Connection error: {error}")
        elif error_name == "BadRequestError" or isinstance(error, BadRequestError):
            return LLMBadRequestError(str(error))
        elif hasattr(error, 'status_code'):
            status = getattr(error, 'status_code', 500)
            if status >= 500:
                return LLMServerError(str(error))
            elif status >= 400:
                return LLMBadRequestError(str(error))
        return LLMError(str(error))
    
    async def _retry_with_backoff(self, func, *args, **kwargs):
        """Retry with exponential backoff based on retry config."""
        last_error = None
        for attempt in range(self.retry_config["max_retries"]):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = self._translate_error(e)
                if isinstance(last_error, (LLMRateLimitError, LLMServerError, LLMTimeoutError)):
                    if attempt < self.retry_config["max_retries"] - 1:
                        wait_time = min(
                            self.retry_config["backoff_factor"] ** attempt,
                            self.retry_config["max_backoff"]
                        )
                        if isinstance(last_error, LLMRateLimitError) and last_error.retry_after:
                            wait_time = last_error.retry_after
                        await asyncio.sleep(wait_time)
                        continue
                raise last_error
        raise last_error
    
    async def embed(
        self, 
        texts: List[str],
        timeout: Optional[float] = None
    ) -> EmbeddingResponse:
        """Generate embeddings using OpenAI API."""
        # Batch texts if needed
        all_embeddings = []
        for i in range(0, len(texts), self.max_batch_size):
            batch = texts[i:i + self.max_batch_size]
            
            async def _make_request():
                return await asyncio.wait_for(
                    self.client.embeddings.create(
                        model=self.model,
                        input=batch,
                        encoding_format="float"
                    ),
                    timeout=timeout or self.request_timeout
                )
            
            try:
                response = await self._retry_with_backoff(_make_request)
            except LLMError:
                raise
            except Exception as e:
                raise self._translate_error(e)
            
            all_embeddings.extend([dp.embedding for dp in response.data])
        
        embeddings_array = np.array(all_embeddings)
        
        return EmbeddingResponse(
            embeddings=embeddings_array,
            dimensions=self.embedding_dim,
            model=self.model,
            usage={
                "prompt_tokens": len(texts) * 10,  # Estimate
                "total_tokens": len(texts) * 10
            }
        )


# Factory functions for backward compatibility
@deprecated_llm_function("nano_graphrag.llm.providers.OpenAIProvider")
async def gpt_4o_complete(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: Optional[List[Dict[str, str]]] = None,
    **kwargs
) -> str:
    """Backward compatible function for gpt-4o completions.
    
    DEPRECATED: Use OpenAIProvider instead.
    This function will be removed in v0.2.0.
    """
    provider = OpenAIProvider(model="gpt-5")
    return await provider.complete_with_cache(
        prompt, system_prompt, history_messages, 
        hashing_kv=kwargs.pop("hashing_kv", None),
        **kwargs
    )


@deprecated_llm_function("nano_graphrag.llm.providers.OpenAIProvider")
async def gpt_4o_mini_complete(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: Optional[List[Dict[str, str]]] = None,
    **kwargs
) -> str:
    """Backward compatible function for gpt-4o-mini completions.
    
    DEPRECATED: Use OpenAIProvider instead.
    This function will be removed in v0.2.0.
    """
    provider = OpenAIProvider(model="gpt-5-mini")
    return await provider.complete_with_cache(
        prompt, system_prompt, history_messages,
        hashing_kv=kwargs.pop("hashing_kv", None),
        **kwargs
    )


@deprecated_llm_function("nano_graphrag.llm.providers.OpenAIEmbeddingProvider")
async def openai_embedding(texts: List[str]) -> np.ndarray:
    """Backward compatible OpenAI embedding function.
    
    DEPRECATED: Use OpenAIEmbeddingProvider instead.
    This function will be removed in v0.2.0.
    """
    provider = OpenAIEmbeddingProvider()
    response = await provider.embed(texts)
    return response["embeddings"]