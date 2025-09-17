"""Tests for OpenAI Responses API provider - focusing on streaming timeout fix."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nano_graphrag.llm.providers.openai_responses import OpenAIResponsesProvider
from nano_graphrag.llm.base import LLMTimeoutError, StreamChunk


@pytest.mark.asyncio
async def test_streaming_with_per_chunk_timeout_success():
    """Test that streaming works with per-chunk idle timeout and doesn't timeout on long generations."""

    # Mock response events that simulate a long-running stream
    mock_events = [
        MagicMock(type="response.output_text.delta", delta="This is "),
        MagicMock(type="response.output_text.delta", delta="a very "),
        MagicMock(type="response.output_text.delta", delta="long "),
        MagicMock(type="response.output_text.delta", delta="generation "),
        MagicMock(type="response.output_text.delta", delta="that takes "),
        MagicMock(type="response.output_text.delta", delta="time."),
        MagicMock(type="response.completed"),
    ]

    # Create a mock stream object
    class MockStream:
        async def __aiter__(self):
            """Simulate slow streaming with 0.5s between chunks."""
            for event in mock_events:
                await asyncio.sleep(0.5)  # Simulate network delay between chunks
                yield event

    # Create provider with short idle timeout (1 second)
    provider = OpenAIResponsesProvider(
        model="gpt-5-mini",
        api_key="test-key",
        idle_timeout=1.0  # 1 second idle timeout
    )

    # Mock the client's responses.create to return our mock stream
    mock_stream = MockStream()

    with patch.object(provider.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_stream

        # Collect all streamed chunks
        chunks = []
        async for chunk in provider.stream("Test prompt"):
            chunks.append(chunk["text"])

        # Verify we got all chunks despite total time > idle_timeout
        # Total time is ~3 seconds (6 chunks * 0.5s) but no single gap > 1s
        assert chunks == ["This is ", "a very ", "long ", "generation ", "that takes ", "time.", ""]

        # Verify the API was called correctly
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs['model'] == 'gpt-5-mini'
        assert call_kwargs['stream'] is True
        assert 'Test prompt' in call_kwargs['input']


@pytest.mark.asyncio
async def test_streaming_idle_timeout_triggers_on_stall():
    """Test that idle timeout correctly triggers when stream stalls."""

    # Mock events with a stall in the middle
    mock_events = [
        MagicMock(type="response.output_text.delta", delta="Start "),
        MagicMock(type="response.output_text.delta", delta="text "),
        # Stall will happen here
        MagicMock(type="response.output_text.delta", delta="never arrives"),
    ]

    # Create a mock stream that stalls
    class MockStalledStream:
        async def __aiter__(self):
            """Simulate a stream that stalls after 2 chunks."""
            yield mock_events[0]
            await asyncio.sleep(0.1)
            yield mock_events[1]
            # Simulate indefinite stall - no more data
            await asyncio.sleep(10)  # Much longer than idle timeout
            yield mock_events[2]  # This should never be reached

    # Create provider with very short idle timeout
    provider = OpenAIResponsesProvider(
        model="gpt-5-mini",
        api_key="test-key",
        idle_timeout=0.5  # 500ms idle timeout
    )

    # Mock the client
    mock_stream = MockStalledStream()

    with patch.object(provider.client.responses, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_stream

        # Collect chunks and expect timeout
        chunks = []
        with pytest.raises(LLMTimeoutError) as exc_info:
            async for chunk in provider.stream("Test prompt"):
                chunks.append(chunk["text"])

        # Verify we got the first two chunks before timeout
        assert chunks == ["Start ", "text "]

        # Verify the error message indicates idle timeout
        assert "No data received for 0.5s during stream" in str(exc_info.value)
        assert "connection may be stalled" in str(exc_info.value)