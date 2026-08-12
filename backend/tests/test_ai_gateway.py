import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from app.ai.exceptions import (
    AIInvalidModelError,
    AIInvalidRequestError,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    ProviderError,
    ProviderRateLimitError,
    ProviderStreamError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.ai.gateway import AIGateway, ChatRequest, GatewayChatResult
from app.ai.provider import (
    ChatDelta,
    ChatDone,
    ChatEvent,
    ChatMessage,
    ChatProvider,
    ChatResult,
    ChatRole,
    ChatUsageEvent,
    FinishReason,
    ProviderChatRequest,
    TokenUsage,
)
from app.ai.providers.fake import FakeChatProvider
from app.core.config import AIModelConfig


def _model_config() -> AIModelConfig:
    return AIModelConfig(
        provider_key="primary",
        provider_model="provider-model",
        default_temperature=0.3,
        default_max_output_tokens=512,
        max_output_tokens=1024,
        context_window_tokens=4096,
    )


def _chat_request() -> ChatRequest:
    return ChatRequest(
        request_id="request-1",
        messages=(ChatMessage(role=ChatRole.USER, content="Hello"),),
    )


def _gateway(
    provider_factory: Mock,
    *,
    max_retry_attempts: int = 0,
    retry_backoff_seconds: float = 0.0,
    total_deadline_seconds: float = 1.0,
    stream_idle_timeout_seconds: float = 1.0,
    stream_total_deadline_seconds: float = 1.0,
) -> AIGateway:
    return AIGateway(
        model_configs={"general": _model_config()},
        default_model_alias="general",
        provider_factory=provider_factory,
        max_retry_attempts=max_retry_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        total_deadline_seconds=total_deadline_seconds,
        stream_idle_timeout_seconds=stream_idle_timeout_seconds,
        stream_total_deadline_seconds=stream_total_deadline_seconds,
    )


@pytest.mark.parametrize(
    (
        "model_alias",
        "temperature",
        "max_output_tokens",
        "expected_model_alias",
        "expected_temperature",
        "expected_max_output_tokens",
    ),
    [
        ("general", 0.7, 256, "general", 0.7, 256),
        (None, None, None, "general", 0.3, 512),
        ("general", 0.0, 1, "general", 0.0, 1),
        ("general", 2.0, 1024, "general", 2.0, 1024),
    ],
)
def test_generate_resolves_model_and_calls_provider(
    model_alias: str | None,
    temperature: float | None,
    max_output_tokens: int | None,
    expected_model_alias: str,
    expected_temperature: float,
    expected_max_output_tokens: int,
) -> None:
    provider = FakeChatProvider(content="Gateway result.")
    provider_factory = Mock(return_value=provider)
    gateway = _gateway(provider_factory)
    message = ChatMessage(role=ChatRole.USER, content="Hello")

    result = asyncio.run(
        gateway.generate(
            ChatRequest(
                request_id="request-1",
                messages=(message,),
                model_alias=model_alias,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        )
    )

    assert result.content == "Gateway result."
    assert result.model_alias == expected_model_alias
    provider_factory.assert_called_once_with("primary")
    assert provider.last_request == ProviderChatRequest(
        request_id="request-1",
        messages=(message,),
        provider_model="provider-model",
        temperature=expected_temperature,
        max_output_tokens=expected_max_output_tokens,
    )


def test_generate_returns_stable_gateway_result_without_provider_model() -> None:
    usage = TokenUsage(
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
    )
    provider = FakeChatProvider(
        content="Gateway result.",
        finish_reason=FinishReason.LENGTH,
        usage=usage,
    )
    gateway = _gateway(Mock(return_value=provider))

    result = asyncio.run(gateway.generate(_chat_request()))

    assert result == GatewayChatResult(
        request_id="request-1",
        model_alias="general",
        content="Gateway result.",
        finish_reason=FinishReason.LENGTH,
        usage=usage,
    )
    assert not hasattr(result, "provider_model")


@pytest.mark.parametrize(
    ("model_alias", "default_model_alias"),
    [
        ("missing", "general"),
        (None, None),
    ],
)
def test_generate_rejects_unconfigured_model_without_calling_factory(
    model_alias: str | None,
    default_model_alias: str | None,
) -> None:
    provider_factory = Mock()
    gateway = AIGateway(
        model_configs={"general": _model_config()},
        default_model_alias=default_model_alias,
        provider_factory=provider_factory,
        max_retry_attempts=0,
        retry_backoff_seconds=0.0,
        total_deadline_seconds=1.0,
        stream_idle_timeout_seconds=1.0,
        stream_total_deadline_seconds=1.0,
    )

    with pytest.raises(AIInvalidModelError):
        asyncio.run(
            gateway.generate(
                ChatRequest(
                    request_id="request-1",
                    messages=(),
                    model_alias=model_alias,
                )
            )
        )

    provider_factory.assert_not_called()


@pytest.mark.parametrize(
    ("provider_error", "expected_error_type", "expected_message"),
    [
        (
            ProviderRateLimitError("raw provider rate-limit detail"),
            AIProviderRateLimitError,
            "AI provider rate limit exceeded.",
        ),
        (
            ProviderTimeoutError("raw provider timeout detail"),
            AIProviderTimeoutError,
            "AI provider request timed out.",
        ),
        (
            ProviderUnavailableError("raw provider unavailable detail"),
            AIProviderUnavailableError,
            "AI provider is unavailable.",
        ),
        (
            ProviderError("raw provider failure detail"),
            AIProviderUnavailableError,
            "AI provider request failed.",
        ),
    ],
)
def test_generate_translates_provider_errors_to_safe_gateway_errors(
    provider_error: ProviderError,
    expected_error_type: type[AIProviderError],
    expected_message: str,
) -> None:
    provider = FakeChatProvider(content="", generate_error=provider_error)
    provider_factory = Mock(return_value=provider)
    gateway = _gateway(provider_factory)

    with pytest.raises(expected_error_type) as error_info:
        asyncio.run(gateway.generate(_chat_request()))

    assert str(error_info.value) == expected_message
    assert error_info.value.__cause__ is provider_error
    assert str(provider_error) not in str(error_info.value)


def test_generate_propagates_cancellation_without_translating_it() -> None:
    # AsyncMock 模拟异步 generate() 在客户端取消时抛出 CancelledError。
    provider = Mock(spec=ChatProvider)
    provider.generate = AsyncMock(side_effect=asyncio.CancelledError())
    gateway = _gateway(Mock(return_value=provider))

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(gateway.generate(_chat_request()))


@pytest.mark.parametrize(
    ("temperature", "max_output_tokens"),
    [
        (-0.1, None),
        (2.1, None),
        (None, 0),
        (None, -1),
        (None, 1025),
    ],
)
def test_generate_rejects_invalid_parameters_without_calling_factory(
    temperature: float | None,
    max_output_tokens: int | None,
) -> None:
    provider_factory = Mock()
    gateway = _gateway(provider_factory)

    with pytest.raises(AIInvalidRequestError):
        asyncio.run(
            gateway.generate(
                ChatRequest(
                    request_id="request-1",
                    messages=(),
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )
            )
        )

    provider_factory.assert_not_called()


def test_generate_accepts_context_window_exact_boundary() -> None:
    provider = FakeChatProvider(content="Within context window.")
    provider_factory = Mock(return_value=provider)
    estimator = Mock(return_value=3_840)
    gateway = AIGateway(
        model_configs={"general": _model_config()},
        default_model_alias="general",
        provider_factory=provider_factory,
        max_retry_attempts=0,
        retry_backoff_seconds=0.0,
        total_deadline_seconds=1.0,
        stream_idle_timeout_seconds=1.0,
        stream_total_deadline_seconds=1.0,
        input_token_estimator=estimator,
    )

    result = asyncio.run(
        gateway.generate(
            ChatRequest(
                request_id="request-1",
                messages=(ChatMessage(role=ChatRole.USER, content="Hello"),),
                max_output_tokens=256,
            )
        )
    )

    assert result.content == "Within context window."
    estimator.assert_called_once_with(
        "provider-model",
        (ChatMessage(role=ChatRole.USER, content="Hello"),),
    )
    provider_factory.assert_called_once_with("primary")


def test_generate_rejects_context_window_overflow_before_creating_provider() -> None:
    provider_factory = Mock()
    estimator = Mock(return_value=3_841)
    gateway = AIGateway(
        model_configs={"general": _model_config()},
        default_model_alias="general",
        provider_factory=provider_factory,
        max_retry_attempts=0,
        retry_backoff_seconds=0.0,
        total_deadline_seconds=1.0,
        stream_idle_timeout_seconds=1.0,
        stream_total_deadline_seconds=1.0,
        input_token_estimator=estimator,
    )

    with pytest.raises(
        AIInvalidRequestError,
        match="exceeds the model context window",
    ):
        asyncio.run(
            gateway.generate(
                ChatRequest(
                    request_id="request-1",
                    messages=(ChatMessage(role=ChatRole.USER, content="Hello"),),
                    max_output_tokens=256,
                )
            )
        )

    estimator.assert_called_once()
    provider_factory.assert_not_called()


def test_generate_uses_default_output_budget_for_context_window_check() -> None:
    provider_factory = Mock()
    estimator = Mock(return_value=3_585)
    gateway = AIGateway(
        model_configs={"general": _model_config()},
        default_model_alias="general",
        provider_factory=provider_factory,
        max_retry_attempts=0,
        retry_backoff_seconds=0.0,
        total_deadline_seconds=1.0,
        stream_idle_timeout_seconds=1.0,
        stream_total_deadline_seconds=1.0,
        input_token_estimator=estimator,
    )

    with pytest.raises(
        AIInvalidRequestError,
        match="exceeds the model context window",
    ):
        asyncio.run(gateway.generate(_chat_request()))

    # 模型默认输出预算是 512；3585 + 512 > 4096。
    provider_factory.assert_not_called()


def test_generate_retries_retryable_error_until_success() -> None:
    provider = Mock(spec=ChatProvider)
    provider.generate = AsyncMock(
        side_effect=[
            ProviderUnavailableError("temporary outage"),
            ChatResult(
                request_id="request-1",
                content="Recovered result.",
                finish_reason=FinishReason.STOP,
                usage=None,
            ),
        ]
    )
    provider_factory = Mock(return_value=provider)
    gateway = _gateway(
        provider_factory,
        max_retry_attempts=1,
    )

    result = asyncio.run(gateway.generate(_chat_request()))

    assert result.content == "Recovered result."
    assert provider.generate.await_count == 2
    provider_factory.assert_called_once_with("primary")


@pytest.mark.parametrize(
    ("provider_error", "expected_error_type"),
    [
        (ProviderRateLimitError("rate limited"), AIProviderRateLimitError),
        (ProviderTimeoutError("timed out"), AIProviderTimeoutError),
        (ProviderUnavailableError("unavailable"), AIProviderUnavailableError),
    ],
)
def test_generate_translates_retryable_error_after_attempt_limit(
    provider_error: ProviderError,
    expected_error_type: type[AIProviderError],
) -> None:
    provider = Mock(spec=ChatProvider)
    provider.generate = AsyncMock(side_effect=provider_error)
    gateway = _gateway(
        Mock(return_value=provider),
        max_retry_attempts=2,
    )

    with pytest.raises(expected_error_type):
        asyncio.run(gateway.generate(_chat_request()))

    assert provider.generate.await_count == 3


def test_generate_does_not_retry_non_retryable_provider_error() -> None:
    provider = Mock(spec=ChatProvider)
    provider.generate = AsyncMock(side_effect=ProviderError("malformed"))
    gateway = _gateway(
        Mock(return_value=provider),
        max_retry_attempts=3,
    )

    with pytest.raises(AIProviderUnavailableError):
        asyncio.run(gateway.generate(_chat_request()))

    assert provider.generate.await_count == 1


def test_generate_uses_exponential_backoff_without_waiting_after_final_failure() -> (
    None
):
    provider = Mock(spec=ChatProvider)
    provider.generate = AsyncMock(
        side_effect=[
            ProviderTimeoutError("first timeout"),
            ProviderTimeoutError("second timeout"),
            ProviderTimeoutError("final timeout"),
        ]
    )
    gateway = _gateway(
        Mock(return_value=provider),
        max_retry_attempts=2,
        retry_backoff_seconds=0.2,
    )

    with patch("app.ai.gateway.asyncio.sleep", new_callable=AsyncMock) as sleep:
        with pytest.raises(AIProviderTimeoutError):
            asyncio.run(gateway.generate(_chat_request()))

    sleep.assert_has_awaits([call(0.2), call(0.4)])
    assert sleep.await_count == 2


async def _slow_generate(_request: ProviderChatRequest) -> ChatResult:
    await asyncio.sleep(0.1)
    return ChatResult(
        request_id="request-1",
        content="too late",
        finish_reason=FinishReason.STOP,
        usage=None,
    )


def test_generate_translates_total_deadline_to_timeout_error() -> None:
    provider = Mock(spec=ChatProvider)
    provider.generate = AsyncMock(side_effect=_slow_generate)
    gateway = _gateway(
        Mock(return_value=provider),
        max_retry_attempts=2,
        total_deadline_seconds=0.01,
    )

    with pytest.raises(AIProviderTimeoutError):
        asyncio.run(gateway.generate(_chat_request()))

    assert provider.generate.await_count == 1


async def _collect_stream(stream: AsyncIterator[ChatEvent]) -> list[ChatEvent]:
    return [event async for event in stream]


async def _stream_attempt(
    events: tuple[ChatEvent, ...],
    *,
    error: ProviderError | None = None,
    closed_attempts: list[bool] | None = None,
) -> AsyncIterator[ChatEvent]:
    try:
        for event in events:
            yield event

        if error is not None:
            raise error
    finally:
        if closed_attempts is not None:
            closed_attempts.append(True)


async def _blocking_stream(
    closed_attempts: list[bool],
) -> AsyncIterator[ChatEvent]:
    try:
        await asyncio.Event().wait()
        yield ChatDone(
            request_id="request-1",
            finish_reason=FinishReason.STOP,
        )
    finally:
        closed_attempts.append(True)


async def _event_then_block(
    event: ChatEvent,
    closed_attempts: list[bool],
) -> AsyncIterator[ChatEvent]:
    try:
        yield event
        await asyncio.Event().wait()
        yield ChatDone(
            request_id="request-1",
            finish_reason=FinishReason.STOP,
        )
    finally:
        closed_attempts.append(True)


def test_stream_yields_delta_usage_and_done_and_closes_provider() -> None:
    usage = TokenUsage(
        input_tokens=6,
        output_tokens=9,
        total_tokens=15,
    )
    events: tuple[ChatEvent, ...] = (
        ChatDelta(request_id="request-1", content="First"),
        ChatDelta(request_id="request-1", content=" second"),
        ChatUsageEvent(request_id="request-1", usage=usage),
        ChatDone(
            request_id="request-1",
            finish_reason=FinishReason.STOP,
        ),
    )
    provider = FakeChatProvider(content="", stream_events=events)
    provider_factory = Mock(return_value=provider)
    gateway = _gateway(provider_factory)

    result = asyncio.run(_collect_stream(gateway.stream(_chat_request())))

    assert result == list(events)
    assert provider.stream_closed is True
    provider_factory.assert_called_once_with("primary")
    assert provider.last_request == ProviderChatRequest(
        request_id="request-1",
        messages=_chat_request().messages,
        provider_model="provider-model",
        temperature=0.3,
        max_output_tokens=512,
    )


def test_stream_retries_retryable_error_before_first_event() -> None:
    closed_attempts: list[bool] = []
    done = ChatDone(
        request_id="request-1",
        finish_reason=FinishReason.STOP,
    )
    provider = Mock(spec=ChatProvider)
    provider.stream.side_effect = [
        _stream_attempt(
            (),
            error=ProviderUnavailableError("temporary outage"),
            closed_attempts=closed_attempts,
        ),
        _stream_attempt((done,), closed_attempts=closed_attempts),
    ]
    gateway = _gateway(
        Mock(return_value=provider),
        max_retry_attempts=1,
    )

    result = asyncio.run(_collect_stream(gateway.stream(_chat_request())))

    assert result == [done]
    assert provider.stream.call_count == 2
    assert closed_attempts == [True, True]


@pytest.mark.parametrize(
    "first_event",
    [
        ChatDelta(request_id="request-1", content="visible"),
        ChatUsageEvent(
            request_id="request-1",
            usage=TokenUsage(
                input_tokens=1,
                output_tokens=1,
                total_tokens=2,
            ),
        ),
    ],
)
def test_stream_does_not_retry_after_any_event(
    first_event: ChatEvent,
) -> None:
    closed_attempts: list[bool] = []
    provider = Mock(spec=ChatProvider)
    provider.stream.return_value = _stream_attempt(
        (first_event,),
        error=ProviderTimeoutError("stream interrupted"),
        closed_attempts=closed_attempts,
    )
    gateway = _gateway(
        Mock(return_value=provider),
        max_retry_attempts=3,
    )

    async def consume() -> None:
        stream = gateway.stream(_chat_request())
        assert await anext(stream) == first_event

        with pytest.raises(AIProviderTimeoutError):
            await anext(stream)

    asyncio.run(consume())

    provider.stream.assert_called_once()
    assert closed_attempts == [True]


def test_stream_uses_exponential_backoff_before_first_event() -> None:
    provider = Mock(spec=ChatProvider)
    done = ChatDone(
        request_id="request-1",
        finish_reason=FinishReason.STOP,
    )
    provider.stream.side_effect = [
        _stream_attempt((), error=ProviderTimeoutError("first timeout")),
        _stream_attempt((), error=ProviderTimeoutError("second timeout")),
        _stream_attempt((done,)),
    ]
    gateway = _gateway(
        Mock(return_value=provider),
        max_retry_attempts=2,
        retry_backoff_seconds=0.2,
    )

    with patch("app.ai.gateway.asyncio.sleep", new_callable=AsyncMock) as sleep:
        result = asyncio.run(_collect_stream(gateway.stream(_chat_request())))

    assert result == [done]
    sleep.assert_has_awaits([call(0.2), call(0.4)])
    assert provider.stream.call_count == 3


def test_stream_retries_idle_timeout_before_first_event() -> None:
    closed_attempts: list[bool] = []
    done = ChatDone(
        request_id="request-1",
        finish_reason=FinishReason.STOP,
    )
    provider = Mock(spec=ChatProvider)
    provider.stream.side_effect = [
        _blocking_stream(closed_attempts),
        _stream_attempt((done,), closed_attempts=closed_attempts),
    ]
    gateway = _gateway(
        Mock(return_value=provider),
        max_retry_attempts=1,
        stream_idle_timeout_seconds=0.01,
        stream_total_deadline_seconds=1.0,
    )

    result = asyncio.run(_collect_stream(gateway.stream(_chat_request())))

    assert result == [done]
    assert provider.stream.call_count == 2
    assert closed_attempts == [True, True]


def test_stream_does_not_retry_idle_timeout_after_first_event() -> None:
    closed_attempts: list[bool] = []
    delta = ChatDelta(request_id="request-1", content="visible")
    provider = Mock(spec=ChatProvider)
    provider.stream.return_value = _event_then_block(delta, closed_attempts)
    gateway = _gateway(
        Mock(return_value=provider),
        max_retry_attempts=2,
        stream_idle_timeout_seconds=0.01,
        stream_total_deadline_seconds=1.0,
    )

    async def consume() -> None:
        stream = gateway.stream(_chat_request())
        assert await anext(stream) == delta

        with pytest.raises(AIProviderTimeoutError):
            await anext(stream)

    asyncio.run(consume())

    provider.stream.assert_called_once()
    assert closed_attempts == [True]


def test_stream_total_deadline_does_not_retry() -> None:
    closed_attempts: list[bool] = []
    provider = Mock(spec=ChatProvider)
    provider.stream.return_value = _blocking_stream(closed_attempts)
    gateway = _gateway(
        Mock(return_value=provider),
        max_retry_attempts=2,
        stream_idle_timeout_seconds=1.0,
        stream_total_deadline_seconds=0.01,
    )

    with pytest.raises(
        AIProviderTimeoutError,
        match="AI stream exceeded its total deadline",
    ):
        asyncio.run(_collect_stream(gateway.stream(_chat_request())))

    provider.stream.assert_called_once()
    assert closed_attempts == [True]


def test_stream_propagates_cancellation_and_closes_provider() -> None:
    closed_attempts: list[bool] = []
    provider = Mock(spec=ChatProvider)
    provider.stream.return_value = _blocking_stream(closed_attempts)
    gateway = _gateway(Mock(return_value=provider))

    async def consume_and_cancel() -> None:
        stream = gateway.stream(_chat_request())
        pending_event = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        pending_event.cancel()

        with pytest.raises(asyncio.CancelledError):
            await pending_event

    asyncio.run(consume_and_cancel())

    provider.stream.assert_called_once()
    assert closed_attempts == [True]


def test_stream_aclose_closes_provider_stream() -> None:
    delta = ChatDelta(request_id="request-1", content="visible")
    provider = FakeChatProvider(
        content="",
        stream_events=(
            delta,
            ChatDone(
                request_id="request-1",
                finish_reason=FinishReason.STOP,
            ),
        ),
    )
    gateway = _gateway(Mock(return_value=provider))

    async def consume_and_close() -> None:
        stream = gateway.stream(_chat_request())
        assert await anext(stream) == delta
        await stream.aclose()

    asyncio.run(consume_and_close())

    assert provider.stream_closed is True


def test_stream_rejects_missing_done_as_provider_failure() -> None:
    provider = FakeChatProvider(content="", stream_events=())
    gateway = _gateway(
        Mock(return_value=provider),
        max_retry_attempts=3,
    )

    with pytest.raises(AIProviderUnavailableError) as error_info:
        asyncio.run(_collect_stream(gateway.stream(_chat_request())))

    assert isinstance(error_info.value.__cause__, ProviderStreamError)
    assert provider.stream_closed is True


def test_stream_rejects_unconfigured_model_without_calling_factory() -> None:
    provider_factory = Mock()
    gateway = _gateway(provider_factory)
    request = ChatRequest(
        request_id="request-1",
        messages=_chat_request().messages,
        model_alias="missing",
    )

    with pytest.raises(AIInvalidModelError):
        asyncio.run(_collect_stream(gateway.stream(request)))

    provider_factory.assert_not_called()


@pytest.mark.parametrize(
    ("temperature", "max_output_tokens"),
    [
        (2.1, None),
        (None, 1025),
    ],
)
def test_stream_rejects_invalid_parameters_without_calling_factory(
    temperature: float | None,
    max_output_tokens: int | None,
) -> None:
    provider_factory = Mock()
    gateway = _gateway(provider_factory)
    request = ChatRequest(
        request_id="request-1",
        messages=_chat_request().messages,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    with pytest.raises(AIInvalidRequestError):
        asyncio.run(_collect_stream(gateway.stream(request)))

    provider_factory.assert_not_called()


def test_stream_rejects_context_overflow_without_calling_factory() -> None:
    provider_factory = Mock()
    gateway = AIGateway(
        model_configs={"general": _model_config()},
        default_model_alias="general",
        provider_factory=provider_factory,
        max_retry_attempts=0,
        retry_backoff_seconds=0.0,
        total_deadline_seconds=1.0,
        stream_idle_timeout_seconds=1.0,
        stream_total_deadline_seconds=1.0,
        input_token_estimator=Mock(return_value=3_841),
    )
    request = ChatRequest(
        request_id="request-1",
        messages=_chat_request().messages,
        max_output_tokens=256,
    )

    with pytest.raises(
        AIInvalidRequestError,
        match="exceeds the model context window",
    ):
        asyncio.run(_collect_stream(gateway.stream(request)))

    provider_factory.assert_not_called()
