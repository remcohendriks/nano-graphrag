"""OpenAI Responses API Provider - Modern streaming-first implementation."""

import os
import asyncio
from typing import AsyncIterator, Dict, List, Optional, Any
from openai import AsyncOpenAI, APIConnectionError, RateLimitError, AuthenticationError, BadRequestError

from ..base import (
    BaseLLMProvider,
    CompletionParams,
    CompletionResponse,
    StreamChunk,
    LLMError,
    LLMAuthError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMServerError,
    LLMBadRequestError,
)


class OpenAIResponsesProvider(BaseLLMProvider):
    """OpenAI provider using the modern Responses API with better streaming support."""

    env_key = "OPENAI_API_KEY"

    def __init__(
        self,
        model: str = "gpt-5-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        idle_timeout: float = 30.0,  # Per-chunk timeout
        **kwargs
    ):
        # Use a much longer SDK timeout since we handle idle timeout ourselves
        kwargs.setdefault('request_timeout', 600.0)  # 10 minutes for SDK
        super().__init__(model, api_key, base_url, **kwargs)
        self.idle_timeout = idle_timeout
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.request_timeout,  # This is the SDK/httpx timeout
            max_retries=0  # We handle retries ourselves
        )

    def _build_input(self, prompt: str, system_prompt: Optional[str] = None, history: Optional[List[Dict[str, str]]] = None) -> Any:
        """Build input for Responses API.

        The Responses API accepts either:
        - A string for simple prompts
        - A list of message-like dicts for conversations
        - Mixed content with images
        """
        # For now, concatenate system + history + prompt as a single string
        # The Responses API also supports structured input similar to messages
        parts = []

        if system_prompt:
            parts.append(f"System: {system_prompt}")

        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                parts.append(f"{role.capitalize()}: {content}")

        parts.append(f"User: {prompt}")

        return "\n\n".join(parts)

    def _translate_params(self, params: CompletionParams) -> Dict[str, Any]:
        """Translate vendor-neutral params to Responses API format."""
        if not params:
            return {}

        api_params = {}

        # Responses API uses max_output_tokens instead of max_tokens
        if "max_output_tokens" in params:
            api_params["max_output_tokens"] = params["max_output_tokens"]

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
        """Generate completion using OpenAI Responses API (non-streaming)."""
        input_content = self._build_input(prompt, system_prompt, history)
        api_params = self._translate_params(params or {})

        # Handle max_tokens in kwargs
        if "max_tokens" in kwargs:
            api_params["max_output_tokens"] = kwargs.pop("max_tokens")

        # Set reasonable defaults
        if "max_output_tokens" not in api_params:
            api_params["max_output_tokens"] = 2000

        # Filter out Chat Completions parameters not supported in Responses API
        unsupported_params = ["response_format", "n", "logprobs", "top_logprobs",
                             "presence_penalty", "frequency_penalty", "logit_bias",
                             "user", "tools", "tool_choice", "stream_options"]
        for param in unsupported_params:
            kwargs.pop(param, None)

        # Merge kwargs but api_params take precedence
        final_params = {**kwargs, **api_params}

        # Add reasoning effort for GPT-5 models to get faster responses
        if "gpt-5" in self.model and "reasoning" not in final_params:
            final_params["reasoning"] = {"effort": "minimal"}

        # Add instructions if we have a system prompt
        if system_prompt:
            final_params["instructions"] = system_prompt

        async def _make_request():
            # No global timeout wrapper - rely on SDK timeout
            return await self.client.responses.create(
                model=self.model,
                input=input_content,
                stream=False,  # Non-streaming for complete()
                **final_params
            )

        try:
            response = await self._retry_with_backoff(_make_request)
        except LLMError:
            raise
        except Exception as e:
            raise self._translate_error(e)

        # Extract text from response
        output_text = getattr(response, 'output_text', '')
        if output_text is None:
            output_text = ""
            import logging
            logging.warning(f"Got None output from {self.model}")

        # Build usage info if available
        usage = {}
        if hasattr(response, 'usage'):
            usage_obj = response.usage
            if hasattr(usage_obj, 'input_tokens'):
                usage["prompt_tokens"] = usage_obj.input_tokens
            if hasattr(usage_obj, 'output_tokens'):
                usage["completion_tokens"] = usage_obj.output_tokens
            if hasattr(usage_obj, 'total_tokens'):
                usage["total_tokens"] = usage_obj.total_tokens
            elif "prompt_tokens" in usage and "completion_tokens" in usage:
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

        return CompletionResponse(
            text=output_text,
            finish_reason=getattr(response, 'finish_reason', 'stop'),
            usage=usage,
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
        """Stream completions using OpenAI Responses API with per-chunk idle timeout."""
        input_content = self._build_input(prompt, system_prompt, history)
        api_params = self._translate_params(params or {})

        # Handle max_tokens in kwargs
        if "max_tokens" in kwargs:
            api_params["max_output_tokens"] = kwargs.pop("max_tokens")

        # Set reasonable defaults
        if "max_output_tokens" not in api_params:
            api_params["max_output_tokens"] = 2000

        # Filter out Chat Completions parameters not supported in Responses API
        unsupported_params = ["response_format", "n", "logprobs", "top_logprobs",
                             "presence_penalty", "frequency_penalty", "logit_bias",
                             "user", "tools", "tool_choice", "stream_options"]
        for param in unsupported_params:
            kwargs.pop(param, None)

        # Merge kwargs but api_params take precedence
        final_params = {**kwargs, **api_params}

        # Add reasoning effort for GPT-5 models
        if "gpt-5" in self.model and "reasoning" not in final_params:
            final_params["reasoning"] = {"effort": "minimal"}

        # Add instructions if we have a system prompt
        if system_prompt:
            final_params["instructions"] = system_prompt

        # Use idle timeout (per-chunk) instead of global timeout
        idle_timeout = timeout or self.idle_timeout

        async def _make_request():
            # No wait_for wrapper - let the stream run as long as needed
            return await self.client.responses.create(
                model=self.model,
                input=input_content,
                stream=True,  # Enable streaming
                **final_params
            )

        try:
            stream = await self._retry_with_backoff(_make_request)
        except LLMError:
            raise
        except Exception as e:
            raise self._translate_error(e)

        # Iterate with per-chunk idle timeout
        ait = stream.__aiter__()

        try:
            while True:
                try:
                    # Only timeout if no event arrives within idle_timeout seconds
                    event = await asyncio.wait_for(ait.__anext__(), timeout=idle_timeout)

                    # Handle different event types from Responses API
                    event_type = getattr(event, "type", None)

                    if event_type == "response.output_text.delta":
                        # Text delta event
                        delta_text = getattr(event, "delta", "")
                        if delta_text:
                            yield StreamChunk(
                                text=delta_text,
                                finish_reason=None
                            )
                    elif event_type == "response.completed":
                        # Stream completed successfully
                        yield StreamChunk(
                            text="",
                            finish_reason="stop"
                        )
                        break
                    elif event_type == "response.error":
                        # Stream error
                        error_msg = getattr(event, "error", "Unknown streaming error")
                        raise LLMError(f"Streaming error: {error_msg}")
                    # Ignore other event types (metadata, etc.)

                except StopAsyncIteration:
                    break  # Normal end of stream
                except asyncio.TimeoutError:
                    raise LLMTimeoutError(
                        f"No data received for {idle_timeout}s during stream - connection may be stalled"
                    )
        except LLMError:
            raise
        except Exception as e:
            raise self._translate_error(e)


# Backward compatibility functions using Responses API
async def gpt_4o_complete_responses(
    prompt: str,
    system_prompt: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    **kwargs
):
    """Use GPT-5 via Responses API for better streaming support."""
    provider = OpenAIResponsesProvider(model="gpt-5", **kwargs)
    return await provider.complete(prompt, system_prompt, history, **kwargs)


async def gpt_4o_mini_complete_responses(
    prompt: str,
    system_prompt: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    **kwargs
):
    """Use GPT-5-mini via Responses API for better streaming support."""
    provider = OpenAIResponsesProvider(model="gpt-5-mini", **kwargs)
    return await provider.complete(prompt, system_prompt, history, **kwargs)