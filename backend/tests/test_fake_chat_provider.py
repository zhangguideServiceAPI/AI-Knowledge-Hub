import asyncio

import pytest

from app.ai.exceptions import (
    ProviderError,
    ProviderRateLimitError,
    ProviderStreamError,
    ProviderTimeoutError,
)
from app.ai.provider import (
    ChatDelta,
    ChatDone,
    ChatEvent,
    ChatMessage,
    ChatRole,
    ChatUsageEvent,
    FinishReason,
    ProviderChatRequest,
    TokenUsage,
)
from app.ai.providers.fake import FakeChatProvider


def _provider_request() -> ProviderChatRequest:
    return ProviderChatRequest(
        request_id="request-1",
        messages=(
            ChatMessage(
                role=ChatRole.USER,
                content="Explain AI Gateway.",
            ),
        ),
        provider_model="test-model",
        temperature=0.7,
        max_output_tokens=128,
    )


async def _collect_stream_events(
    provider: FakeChatProvider,
    request: ProviderChatRequest,
) -> list[ChatEvent]:
    return [event async for event in provider.stream(request)]


async def _append_stream_events(
    provider: FakeChatProvider,
    request: ProviderChatRequest,
    collected_events: list[ChatEvent],
) -> None:
    async for event in provider.stream(request):
        collected_events.append(event)


async def _close_stream_after_first_event(
    provider: FakeChatProvider,
    request: ProviderChatRequest,
) -> ChatEvent:
    stream = provider.stream(request)
    first_event = await anext(stream)
    await stream.aclose()
    return first_event


async def _cancel_stream_while_waiting(
    provider: FakeChatProvider,
    request: ProviderChatRequest,
    collected_events: list[ChatEvent],
) -> None:
    task = asyncio.create_task(
        _append_stream_events(
            provider,
            request,
            collected_events,
        )
    )

    while provider.last_request is not request:
        await asyncio.sleep(0)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


def test_fake_generate_returns_configured_result_and_records_request() -> None:
    usage = TokenUsage(
        input_tokens=4,
        output_tokens=8,
        total_tokens=12,
    )
    provider = FakeChatProvider(
        content="A stable model boundary.",
        finish_reason=FinishReason.LENGTH,
        usage=usage,
    )
    request = _provider_request()

    result = asyncio.run(provider.generate(request))

    assert provider.last_request is request
    assert result.request_id == request.request_id
    assert result.content == "A stable model boundary."
    assert result.finish_reason is FinishReason.LENGTH
    assert result.usage == usage


def test_fake_generate_supports_missing_usage() -> None:
    provider = FakeChatProvider(content="No usage returned.")

    result = asyncio.run(provider.generate(_provider_request()))

    assert result.finish_reason is FinishReason.STOP
    assert result.usage is None


@pytest.mark.parametrize(
    "configured_error",
    [
        ProviderRateLimitError(),
        ProviderTimeoutError(),
    ],
)
def test_fake_generate_raises_configured_provider_error_and_records_request(
    configured_error: ProviderError,
) -> None:
    provider = FakeChatProvider(
        content="unused",
        generate_error=configured_error,
    )
    request = _provider_request()

    with pytest.raises(type(configured_error)) as error_info:
        asyncio.run(provider.generate(request))

    assert error_info.value is configured_error
    assert provider.last_request is request


def test_fake_stream_yields_configured_events_in_order_and_records_request() -> None:
    request = _provider_request()
    usage = TokenUsage(
        input_tokens=4,
        output_tokens=8,
        total_tokens=12,
    )
    configured_events: tuple[ChatEvent, ...] = (
        ChatDelta(
            request_id=request.request_id,
            content="An AI",
        ),
        ChatUsageEvent(
            request_id=request.request_id,
            usage=usage,
        ),
        ChatDone(
            request_id=request.request_id,
            finish_reason=FinishReason.STOP,
        ),
    )
    provider = FakeChatProvider(
        content="unused",
        stream_events=configured_events,
    )

    events = asyncio.run(_collect_stream_events(provider, request))

    assert events == list(configured_events)
    assert provider.last_request is request
    assert provider.stream_closed is True


def test_fake_stream_raises_configured_error_before_first_event() -> None:
    request = _provider_request()
    configured_error = ProviderTimeoutError()
    provider = FakeChatProvider(
        content="unused",
        stream_events=(
            ChatDelta(
                request_id=request.request_id,
                content="not emitted",
            ),
        ),
        stream_error=configured_error,
        stream_error_after_events=0,
    )
    collected_events: list[ChatEvent] = []

    with pytest.raises(ProviderTimeoutError) as error_info:
        asyncio.run(
            _append_stream_events(
                provider,
                request,
                collected_events,
            )
        )

    assert error_info.value is configured_error
    assert collected_events == []
    assert provider.last_request is request
    assert provider.stream_closed is True


def test_fake_stream_raises_configured_error_after_one_event() -> None:
    request = _provider_request()
    first_event = ChatDelta(
        request_id=request.request_id,
        content="emitted",
    )
    configured_error = ProviderStreamError()
    provider = FakeChatProvider(
        content="unused",
        stream_events=(
            first_event,
            ChatDone(
                request_id=request.request_id,
                finish_reason=FinishReason.STOP,
            ),
        ),
        stream_error=configured_error,
        stream_error_after_events=1,
    )
    collected_events: list[ChatEvent] = []

    with pytest.raises(ProviderStreamError) as error_info:
        asyncio.run(
            _append_stream_events(
                provider,
                request,
                collected_events,
            )
        )

    assert error_info.value is configured_error
    assert collected_events == [first_event]
    assert provider.stream_closed is True


def test_fake_stream_aclose_marks_stream_closed() -> None:
    request = _provider_request()
    first_event = ChatDelta(
        request_id=request.request_id,
        content="emitted",
    )
    provider = FakeChatProvider(
        content="unused",
        stream_events=(
            first_event,
            ChatDone(
                request_id=request.request_id,
                finish_reason=FinishReason.STOP,
            ),
        ),
    )

    emitted_event = asyncio.run(_close_stream_after_first_event(provider, request))

    assert emitted_event is first_event
    assert provider.stream_closed is True


@pytest.mark.parametrize("stream_error_after_events", [-1, 2])
def test_fake_stream_rejects_error_position_outside_event_range(
    stream_error_after_events: int,
) -> None:
    with pytest.raises(ValueError):
        FakeChatProvider(
            content="unused",
            stream_events=(
                ChatDelta(
                    request_id="request-1",
                    content="event",
                ),
            ),
            stream_error_after_events=stream_error_after_events,
        )


def test_fake_stream_propagates_task_cancellation_and_closes_stream() -> None:
    request = _provider_request()
    provider = FakeChatProvider(
        content="unused",
        stream_events=(
            ChatDelta(
                request_id=request.request_id,
                content="not emitted",
            ),
        ),
        stream_delay_seconds=60.0,
    )
    collected_events: list[ChatEvent] = []

    asyncio.run(
        _cancel_stream_while_waiting(
            provider,
            request,
            collected_events,
        )
    )

    assert collected_events == []
    assert provider.last_request is request
    assert provider.stream_closed is True


def test_fake_stream_rejects_negative_delay() -> None:
    with pytest.raises(ValueError):
        FakeChatProvider(
            content="unused",
            stream_delay_seconds=-0.1,
        )
