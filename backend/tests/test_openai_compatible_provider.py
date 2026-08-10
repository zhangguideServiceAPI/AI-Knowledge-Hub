import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from app.ai.exceptions import (
    ProviderError,
    ProviderRateLimitError,
    ProviderStreamError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.ai.provider import (
    ChatDelta,
    ChatDone,
    ChatMessage,
    ChatResult,
    ChatRole,
    ChatUsageEvent,
    FinishReason,
    ProviderChatRequest,
    TokenUsage,
)
from app.ai.providers.openai_compatible import OpenAICompatibleChatProvider


def _provider_request() -> ProviderChatRequest:
    return ProviderChatRequest(
        request_id="request-1",
        messages=(
            ChatMessage(
                role=ChatRole.SYSTEM,
                content="Answer clearly.",
            ),
            ChatMessage(
                role=ChatRole.USER,
                content="Explain AI Gateway.",
            ),
        ),
        provider_model="provider-model",
        temperature=0.3,
        max_output_tokens=128,
    )


def _client_for_create(create: AsyncMock) -> AsyncOpenAI:
    return cast(
        AsyncOpenAI,
        SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create),
            )
        ),
    )


def _request_url() -> httpx.Request:
    return httpx.Request(
        "POST",
        "https://provider.test/v1/chat/completions",
    )


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        request=_request_url(),
    )


def _sdk_chunk(
    *,
    content: str | None = None,
    finish_reason: str | None = None,
    usage: object | None = None,
    choices: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        choices=(
            SimpleNamespace(
                delta=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            ),
        )
        if choices
        else (),
        usage=usage,
    )


def _sdk_usage() -> SimpleNamespace:
    return SimpleNamespace(
        prompt_tokens=8,
        completion_tokens=10,
        total_tokens=18,
    )


class _FakeSDKStream:
    def __init__(
        self,
        events: tuple[object, ...] = (),
        *,
        error: Exception | None = None,
        error_after_events: int = 0,
        wait_event: asyncio.Event | None = None,
    ) -> None:
        self.events = events
        self.error = error
        self.error_after_events = error_after_events
        self.wait_event = wait_event
        self.index = 0
        self.closed = False
        self.started = asyncio.Event()

    def __aiter__(self) -> "_FakeSDKStream":
        return self

    async def __anext__(self) -> object:
        self.started.set()
        if self.wait_event is not None:
            await self.wait_event.wait()

        if self.error is not None and self.index == self.error_after_events:
            raise self.error

        if self.index >= len(self.events):
            raise StopAsyncIteration

        event = self.events[self.index]
        self.index += 1
        return event

    async def close(self) -> None:
        self.closed = True


async def _collect_stream_events(
    provider: OpenAICompatibleChatProvider,
    request: ProviderChatRequest,
) -> list[object]:
    return [event async for event in provider.stream(request)]


def test_generate_maps_request_and_success_response() -> None:
    request = _provider_request()
    sdk_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="An AI Gateway provides a stable boundary."
                ),
                finish_reason="stop",
            )
        ],
        usage=_sdk_usage(),
    )
    create = AsyncMock(return_value=sdk_response)
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    result = asyncio.run(provider.generate(request))

    create.assert_awaited_once_with(
        model="provider-model",
        messages=[
            {
                "role": "system",
                "content": "Answer clearly.",
            },
            {
                "role": "user",
                "content": "Explain AI Gateway.",
            },
        ],
        temperature=0.3,
        max_tokens=128,
        stream=False,
    )
    assert result == ChatResult(
        request_id="request-1",
        content="An AI Gateway provides a stable boundary.",
        finish_reason=FinishReason.STOP,
        usage=TokenUsage(
            input_tokens=8,
            output_tokens=10,
            total_tokens=18,
        ),
    )


def test_generate_allows_missing_usage() -> None:
    sdk_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="No usage returned."),
                finish_reason="stop",
            )
        ],
        usage=None,
    )
    create = AsyncMock(return_value=sdk_response)
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    result = asyncio.run(provider.generate(_provider_request()))

    assert result.usage is None


def test_generate_rejects_missing_choices() -> None:
    sdk_response = SimpleNamespace(choices=[], usage=None)
    create = AsyncMock(return_value=sdk_response)
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    with pytest.raises(ProviderError, match="no choices"):
        asyncio.run(provider.generate(_provider_request()))


def test_generate_rejects_malformed_response() -> None:
    create = AsyncMock(return_value="not-a-chat-completion")
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    with pytest.raises(ProviderError, match="malformed response"):
        asyncio.run(provider.generate(_provider_request()))


def test_generate_rejects_unsupported_finish_reason() -> None:
    sdk_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="unused"),
                finish_reason="tool_calls",
            )
        ],
        usage=None,
    )
    create = AsyncMock(return_value=sdk_response)
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    with pytest.raises(ProviderError, match="unsupported finish reason"):
        asyncio.run(provider.generate(_provider_request()))


@pytest.mark.parametrize(
    (
        "sdk_error",
        "expected_error_type",
        "expected_message",
    ),
    [
        (
            RateLimitError(
                "Raw provider rate limit detail.",
                response=_response(429),
                body=None,
            ),
            ProviderRateLimitError,
            "Provider rate limit exceeded.",
        ),
        (
            APITimeoutError(request=_request_url()),
            ProviderTimeoutError,
            "Provider request timed out.",
        ),
        (
            APIConnectionError(
                message="Raw provider connection detail.",
                request=_request_url(),
            ),
            ProviderUnavailableError,
            "Provider is temporarily unavailable.",
        ),
        (
            InternalServerError(
                "Raw provider server error detail.",
                response=_response(503),
                body=None,
            ),
            ProviderUnavailableError,
            "Provider is temporarily unavailable.",
        ),
        (
            BadRequestError(
                "Raw provider request detail.",
                response=_response(400),
                body=None,
            ),
            ProviderError,
            "Provider request failed.",
        ),
    ],
)
def test_generate_maps_sdk_errors(
    sdk_error: Exception,
    expected_error_type: type[ProviderError],
    expected_message: str,
) -> None:
    create = AsyncMock(side_effect=sdk_error)
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    with pytest.raises(expected_error_type) as error_info:
        asyncio.run(provider.generate(_provider_request()))

    assert str(error_info.value) == expected_message
    assert error_info.value.__cause__ is sdk_error


def test_stream_yields_delta_usage_done_in_order_and_closes_sdk_stream() -> None:
    request = _provider_request()
    sdk_stream = _FakeSDKStream(
        events=(
            _sdk_chunk(content="An AI"),
            _sdk_chunk(content=" Gateway"),
            _sdk_chunk(finish_reason="stop"),
            _sdk_chunk(usage=_sdk_usage(), choices=False),
        )
    )
    create = AsyncMock(return_value=sdk_stream)
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    events = asyncio.run(_collect_stream_events(provider, request))

    assert events == [
        ChatDelta(request_id="request-1", content="An AI"),
        ChatDelta(request_id="request-1", content=" Gateway"),
        ChatUsageEvent(
            request_id="request-1",
            usage=TokenUsage(
                input_tokens=8,
                output_tokens=10,
                total_tokens=18,
            ),
        ),
        ChatDone(
            request_id="request-1",
            finish_reason=FinishReason.STOP,
        ),
    ]
    create.assert_awaited_once_with(
        model="provider-model",
        messages=[
            {
                "role": "system",
                "content": "Answer clearly.",
            },
            {
                "role": "user",
                "content": "Explain AI Gateway.",
            },
        ],
        temperature=0.3,
        max_tokens=128,
        stream=True,
        stream_options={"include_usage": True},
    )
    assert sdk_stream.closed is True


def test_stream_allows_missing_usage() -> None:
    sdk_stream = _FakeSDKStream(
        events=(_sdk_chunk(content="Complete", finish_reason="stop"),)
    )
    create = AsyncMock(return_value=sdk_stream)
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    events = asyncio.run(_collect_stream_events(provider, _provider_request()))

    assert events == [
        ChatDelta(request_id="request-1", content="Complete"),
        ChatDone(
            request_id="request-1",
            finish_reason=FinishReason.STOP,
        ),
    ]
    assert sdk_stream.closed is True


def test_stream_rejects_unsupported_finish_reason() -> None:
    sdk_stream = _FakeSDKStream(events=(_sdk_chunk(finish_reason="tool_calls"),))
    create = AsyncMock(return_value=sdk_stream)
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    with pytest.raises(ProviderStreamError, match="unsupported finish reason"):
        asyncio.run(_collect_stream_events(provider, _provider_request()))

    assert sdk_stream.closed is True


def test_stream_rejects_malformed_event_and_closes_sdk_stream() -> None:
    sdk_stream = _FakeSDKStream(events=("not-a-chat-completion-chunk",))
    create = AsyncMock(return_value=sdk_stream)
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    with pytest.raises(ProviderStreamError, match="malformed stream event"):
        asyncio.run(_collect_stream_events(provider, _provider_request()))

    assert sdk_stream.closed is True


def test_stream_maps_error_after_delta_to_stream_error_and_closes() -> None:
    sdk_error = InternalServerError(
        "Raw provider stream detail.",
        response=_response(503),
        body=None,
    )
    sdk_stream = _FakeSDKStream(
        events=(_sdk_chunk(content="Partial"),),
        error=sdk_error,
        error_after_events=1,
    )
    create = AsyncMock(return_value=sdk_stream)
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    with pytest.raises(ProviderStreamError) as error_info:
        asyncio.run(_collect_stream_events(provider, _provider_request()))

    assert error_info.value.__cause__ is sdk_error
    assert sdk_stream.closed is True


def test_stream_preserves_error_before_first_event() -> None:
    sdk_error = APIConnectionError(request=_request_url())
    sdk_stream = _FakeSDKStream(error=sdk_error)
    create = AsyncMock(return_value=sdk_stream)
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    with pytest.raises(ProviderUnavailableError) as error_info:
        asyncio.run(_collect_stream_events(provider, _provider_request()))

    assert error_info.value.__cause__ is sdk_error
    assert sdk_stream.closed is True


async def _close_stream_after_first_event(
    provider: OpenAICompatibleChatProvider,
    request: ProviderChatRequest,
) -> object:
    stream = provider.stream(request)
    first_event = await anext(stream)
    await stream.aclose()
    return first_event


def test_stream_close_releases_sdk_stream() -> None:
    sdk_stream = _FakeSDKStream(
        events=(
            _sdk_chunk(content="Partial"),
            _sdk_chunk(finish_reason="stop"),
        )
    )
    create = AsyncMock(return_value=sdk_stream)
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    first_event = asyncio.run(
        _close_stream_after_first_event(provider, _provider_request())
    )

    assert first_event == ChatDelta(
        request_id="request-1",
        content="Partial",
    )
    assert sdk_stream.closed is True


async def _cancel_stream_while_waiting(
    provider: OpenAICompatibleChatProvider,
    request: ProviderChatRequest,
    sdk_stream: _FakeSDKStream,
) -> None:
    task = asyncio.create_task(_collect_stream_events(provider, request))

    await sdk_stream.started.wait()

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


def test_stream_propagates_cancellation_and_closes_sdk_stream() -> None:
    wait_event = asyncio.Event()
    sdk_stream = _FakeSDKStream(wait_event=wait_event)
    create = AsyncMock(return_value=sdk_stream)
    provider = OpenAICompatibleChatProvider(_client_for_create(create))

    asyncio.run(
        _cancel_stream_while_waiting(
            provider,
            _provider_request(),
            sdk_stream,
        )
    )

    assert sdk_stream.closed is True
