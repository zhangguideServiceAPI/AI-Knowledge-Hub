import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal
import logging
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest

from app.ai.exceptions import AIProviderTimeoutError
from app.ai.gateway import AIGateway, ChatRequest, GatewayChatResult
from app.ai.provider import (
    ChatDelta,
    ChatDone,
    ChatEvent,
    ChatMessage,
    ChatRole,
    ChatUsageEvent,
    FinishReason,
    TokenUsage,
)
from app.ai.prompt_center import PromptCenter, RenderedPrompt
from app.core.config import AIModelConfig
from app.models.usage import ChatUsageErrorCode, ChatUsageStatus
from app.schemas.ai import ChatRequestSchema
from app.services.chat_service import ChatService

REQUEST_UUID = UUID("00000000-0000-0000-0000-000000000001")
REQUEST_ID = str(REQUEST_UUID)
SYSTEM_PROMPT = "controlled system prompt"


def _gateway(result: GatewayChatResult) -> Mock:
    gateway = Mock(spec=AIGateway)
    gateway.generate = AsyncMock(return_value=result)
    return gateway


def _prompt_center() -> Mock:
    prompt_center = Mock(spec=PromptCenter)
    prompt_center.render.return_value = RenderedPrompt(
        prompt_key="assistant",
        version="v1",
        content=SYSTEM_PROMPT,
    )
    return prompt_center


def test_chat_maps_public_request_and_gateway_result_without_logging_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    user_content = "private user content"
    assistant_content = "private assistant content"
    usage = TokenUsage(
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
    )
    gateway = _gateway(
        GatewayChatResult(
            request_id=REQUEST_ID,
            model_alias="general",
            content=assistant_content,
            finish_reason=FinishReason.STOP,
            usage=usage,
        )
    )
    prompt_center = _prompt_center()
    service = ChatService(gateway, prompt_center)
    request = ChatRequestSchema(
        messages=[
            {"content": user_content},
            {"content": "second user message"},
        ],
        model="general",
        temperature=0.7,
        max_output_tokens=256,
    )

    with patch("app.services.chat_service.uuid4", return_value=REQUEST_UUID):
        with patch(
            "app.services.chat_service.perf_counter",
            side_effect=[10.0, 10.125],
        ):
            with caplog.at_level(logging.INFO, logger="ai_knowledge_hub"):
                response = asyncio.run(service.chat(request, user_id=42))

    gateway.generate.assert_awaited_once_with(
        ChatRequest(
            request_id=REQUEST_ID,
            messages=(
                ChatMessage(role=ChatRole.SYSTEM, content=SYSTEM_PROMPT),
                ChatMessage(role=ChatRole.USER, content=user_content),
                ChatMessage(role=ChatRole.USER, content="second user message"),
            ),
            model_alias="general",
            temperature=0.7,
            max_output_tokens=256,
        )
    )
    prompt_center.render.assert_called_once_with(
        prompt_key="assistant",
        version="v1",
        variables={},
    )
    assert response.model_dump(mode="json") == {
        "request_id": REQUEST_ID,
        "model": "general",
        "content": assistant_content,
        "finish_reason": "stop",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
        },
    }
    assert (
        "ai_knowledge_hub",
        logging.INFO,
        "ai.chat.success "
        f"request_id={REQUEST_ID} model_alias=general "
        "total_tokens=30 latency_ms=125",
    ) in caplog.record_tuples
    assert user_content not in caplog.text
    assert assistant_content not in caplog.text


def test_chat_preserves_missing_usage_as_null() -> None:
    gateway = _gateway(
        GatewayChatResult(
            request_id=REQUEST_ID,
            model_alias="general",
            content="Result",
            finish_reason=FinishReason.LENGTH,
            usage=None,
        )
    )
    prompt_center = _prompt_center()
    service = ChatService(gateway, prompt_center)

    with patch("app.services.chat_service.uuid4", return_value=REQUEST_UUID):
        response = asyncio.run(
            service.chat(
                ChatRequestSchema(messages=[{"content": "Hello"}]),
                user_id=42,
            )
        )

    assert response.request_id == REQUEST_ID
    assert response.model == "general"
    assert response.finish_reason is FinishReason.LENGTH
    assert response.usage is None


def test_chat_propagates_gateway_error_without_logging_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gateway = Mock(spec=AIGateway)
    gateway.generate = AsyncMock(
        side_effect=AIProviderTimeoutError("safe gateway timeout")
    )
    prompt_center = _prompt_center()
    service = ChatService(gateway, prompt_center)
    request = ChatRequestSchema(messages=[{"content": "private user content"}])

    with caplog.at_level(logging.INFO, logger="ai_knowledge_hub"):
        with pytest.raises(AIProviderTimeoutError):
            asyncio.run(service.chat(request, user_id=42))

    assert "ai.chat.success" not in caplog.text
    assert "private user content" not in caplog.text


async def _collect_stream(stream: AsyncIterator[ChatEvent]) -> list[ChatEvent]:
    return [event async for event in stream]


async def _gateway_stream(
    events: tuple[ChatEvent, ...],
    *,
    error: Exception | None = None,
    closed: list[bool] | None = None,
) -> AsyncIterator[ChatEvent]:
    try:
        for event in events:
            yield event

        if error is not None:
            raise error
    finally:
        if closed is not None:
            closed.append(True)


async def _blocking_gateway_stream(
    closed: list[bool],
) -> AsyncIterator[ChatEvent]:
    try:
        await asyncio.Event().wait()
        yield ChatDone(
            request_id=REQUEST_ID,
            finish_reason=FinishReason.STOP,
        )
    finally:
        closed.append(True)


def test_stream_maps_public_request_and_yields_gateway_events() -> None:
    user_content = "private stream content"
    usage = TokenUsage(
        input_tokens=4,
        output_tokens=6,
        total_tokens=10,
    )
    events: tuple[ChatEvent, ...] = (
        ChatDelta(request_id=REQUEST_ID, content="First"),
        ChatUsageEvent(request_id=REQUEST_ID, usage=usage),
        ChatDone(
            request_id=REQUEST_ID,
            finish_reason=FinishReason.STOP,
        ),
    )
    closed: list[bool] = []
    gateway = Mock(spec=AIGateway)
    gateway.stream.return_value = _gateway_stream(events, closed=closed)
    prompt_center = _prompt_center()
    service = ChatService(gateway, prompt_center)
    request = ChatRequestSchema(
        messages=[
            {"content": user_content},
            {"content": "second message"},
        ],
        model="general",
        temperature=0.7,
        max_output_tokens=256,
    )

    with patch("app.services.chat_service.uuid4", return_value=REQUEST_UUID):
        result = asyncio.run(_collect_stream(service.stream(request, user_id=42)))

    assert result == list(events)
    gateway.stream.assert_called_once_with(
        ChatRequest(
            request_id=REQUEST_ID,
            messages=(
                ChatMessage(role=ChatRole.SYSTEM, content=SYSTEM_PROMPT),
                ChatMessage(role=ChatRole.USER, content=user_content),
                ChatMessage(role=ChatRole.USER, content="second message"),
            ),
            model_alias="general",
            temperature=0.7,
            max_output_tokens=256,
        )
    )
    prompt_center.render.assert_called_once_with(
        prompt_key="assistant",
        version="v1",
        variables={},
    )
    assert closed == [True]


def test_stream_propagates_gateway_error_and_closes_gateway_stream() -> None:
    error = AIProviderTimeoutError("safe gateway timeout")
    closed: list[bool] = []
    gateway = Mock(spec=AIGateway)
    gateway.stream.return_value = _gateway_stream(
        (),
        error=error,
        closed=closed,
    )
    service = ChatService(gateway, _prompt_center())
    request = ChatRequestSchema(messages=[{"content": "private content"}])

    with pytest.raises(AIProviderTimeoutError) as error_info:
        asyncio.run(_collect_stream(service.stream(request, user_id=42)))

    assert error_info.value is error
    assert closed == [True]


def test_stream_propagates_cancellation_and_closes_gateway_stream() -> None:
    closed: list[bool] = []
    gateway = Mock(spec=AIGateway)
    gateway.stream.return_value = _blocking_gateway_stream(closed)
    service = ChatService(gateway, _prompt_center())
    request = ChatRequestSchema(messages=[{"content": "private content"}])

    async def consume_and_cancel() -> None:
        service_stream = service.stream(request, user_id=42)
        pending_event = asyncio.create_task(anext(service_stream))
        await asyncio.sleep(0)
        pending_event.cancel()

        with pytest.raises(asyncio.CancelledError):
            await pending_event

    asyncio.run(consume_and_cancel())

    gateway.stream.assert_called_once()
    assert closed == [True]


def test_stream_aclose_closes_gateway_stream() -> None:
    delta = ChatDelta(request_id=REQUEST_ID, content="visible")
    closed: list[bool] = []
    gateway = Mock(spec=AIGateway)
    gateway.stream.return_value = _gateway_stream(
        (
            delta,
            ChatDone(
                request_id=REQUEST_ID,
                finish_reason=FinishReason.STOP,
            ),
        ),
        closed=closed,
    )
    service = ChatService(gateway, _prompt_center())
    request = ChatRequestSchema(messages=[{"content": "private content"}])

    async def consume_and_close() -> None:
        service_stream = service.stream(request, user_id=42)
        assert await anext(service_stream) == delta
        await service_stream.aclose()

    asyncio.run(consume_and_close())

    assert closed == [True]


def _model_config_with_pricing() -> AIModelConfig:
    return AIModelConfig(
        provider_key="primary",
        provider_model="provider-model",
        default_temperature=0.3,
        default_max_output_tokens=256,
        max_output_tokens=512,
        context_window_tokens=4096,
        pricing={
            "input_price_per_million_tokens": "2.5",
            "output_price_per_million_tokens": "10",
            "currency": "USD",
            "version": "2026-08-13",
        },
    )


def test_chat_records_success_usage_and_cost_without_sensitive_content() -> None:
    gateway = _gateway(
        GatewayChatResult(
            request_id=REQUEST_ID,
            model_alias="general",
            content="private assistant answer",
            finish_reason=FinishReason.STOP,
            usage=TokenUsage(input_tokens=1000, output_tokens=250, total_tokens=1250),
        )
    )
    service = ChatService(
        gateway,
        _prompt_center(),
        model_configs={"general": _model_config_with_pricing()},
    )
    records = []

    with patch.object(
        service,
        "_save_usage_safely",
        side_effect=lambda usage: records.append(usage),
        new_callable=AsyncMock,
    ):
        with patch("app.services.chat_service.uuid4", return_value=REQUEST_UUID):
            asyncio.run(
                service.chat(
                    ChatRequestSchema(
                        messages=[{"content": "private user message"}],
                        model="general",
                    ),
                    user_id=42,
                )
            )

    assert len(records) == 1
    usage = records[0]
    assert usage.status == ChatUsageStatus.SUCCESS.value
    assert usage.user_id == 42
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 250
    assert usage.total_tokens == 1250
    assert usage.estimated_cost == Decimal("0.0050000000")
    assert usage.currency == "USD"
    assert usage.pricing_version == "2026-08-13"
    assert "private user message" not in repr(usage.__dict__)
    assert "private assistant answer" not in repr(usage.__dict__)
    assert SYSTEM_PROMPT not in repr(usage.__dict__)


def test_chat_records_sanitized_failure_and_re_raises_original_error() -> None:
    provider_detail = "provider failed at secret endpoint with private body"
    error = AIProviderTimeoutError(provider_detail)
    gateway = Mock(spec=AIGateway)
    gateway.generate = AsyncMock(side_effect=error)
    service = ChatService(
        gateway,
        _prompt_center(),
        model_configs={"general": _model_config_with_pricing()},
        default_model_alias="general",
    )
    records = []

    with patch.object(
        service,
        "_save_usage_safely",
        side_effect=lambda usage: records.append(usage),
        new_callable=AsyncMock,
    ):
        with pytest.raises(AIProviderTimeoutError) as error_info:
            asyncio.run(
                service.chat(
                    ChatRequestSchema(messages=[{"content": "private request"}]),
                    user_id=42,
                )
            )

    assert error_info.value is error
    assert len(records) == 1
    usage = records[0]
    assert usage.status == ChatUsageStatus.FAILED.value
    assert usage.error_code == ChatUsageErrorCode.PROVIDER_TIMEOUT.value
    assert usage.input_tokens is None
    assert usage.estimated_cost is None
    assert provider_detail not in repr(usage.__dict__)


def test_chat_records_cancellation_without_converting_it_to_provider_error() -> None:
    gateway = Mock(spec=AIGateway)
    started = asyncio.Event()

    async def blocking_generate(_request: ChatRequest) -> GatewayChatResult:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    gateway.generate.side_effect = blocking_generate
    service = ChatService(gateway, _prompt_center(), default_model_alias="general")
    records = []

    async def call_and_cancel() -> None:
        with patch.object(
            service,
            "_save_usage_safely",
            side_effect=lambda usage: records.append(usage),
            new_callable=AsyncMock,
        ):
            task = asyncio.create_task(
                service.chat(
                    ChatRequestSchema(messages=[{"content": "private request"}]),
                    user_id=42,
                )
            )
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(call_and_cancel())

    assert len(records) == 1
    usage = records[0]
    assert usage.status == ChatUsageStatus.CANCELLED.value
    assert usage.error_code == ChatUsageErrorCode.CANCELLED.value


def test_stream_records_usage_ttft_cost_and_success_terminal() -> None:
    events: tuple[ChatEvent, ...] = (
        ChatDelta(request_id=REQUEST_ID, content="private delta"),
        ChatUsageEvent(
            request_id=REQUEST_ID,
            usage=TokenUsage(input_tokens=1000, output_tokens=250, total_tokens=1250),
        ),
        ChatDone(request_id=REQUEST_ID, finish_reason=FinishReason.STOP),
    )
    gateway = Mock(spec=AIGateway)
    gateway.stream.return_value = _gateway_stream(events)
    service = ChatService(
        gateway,
        _prompt_center(),
        model_configs={"general": _model_config_with_pricing()},
        default_model_alias="general",
    )
    records = []

    with patch.object(
        service,
        "_save_usage_safely",
        side_effect=lambda usage: records.append(usage),
        new_callable=AsyncMock,
    ):
        with patch("app.services.chat_service.uuid4", return_value=REQUEST_UUID):
            with patch(
                "app.services.chat_service.perf_counter",
                side_effect=[10.0, 10.025, 10.100],
            ):
                result = asyncio.run(
                    _collect_stream(
                        service.stream(
                            ChatRequestSchema(messages=[{"content": "private"}]),
                            user_id=42,
                        )
                    )
                )

    assert result == list(events)
    assert len(records) == 1
    usage = records[0]
    assert usage.status == ChatUsageStatus.SUCCESS.value
    assert usage.time_to_first_token_ms == 25
    assert usage.latency_ms == 99
    assert usage.estimated_cost == Decimal("0.0050000000")
    assert "private delta" not in repr(usage.__dict__)


def test_stream_records_partial_usage_when_failure_happens_after_usage_event() -> None:
    error = AIProviderTimeoutError("private upstream detail")
    gateway = Mock(spec=AIGateway)
    gateway.stream.return_value = _gateway_stream(
        (
            ChatDelta(request_id=REQUEST_ID, content="private delta"),
            ChatUsageEvent(
                request_id=REQUEST_ID,
                usage=TokenUsage(
                    input_tokens=1000,
                    output_tokens=None,
                    total_tokens=None,
                ),
            ),
        ),
        error=error,
    )
    service = ChatService(
        gateway,
        _prompt_center(),
        model_configs={"general": _model_config_with_pricing()},
        default_model_alias="general",
    )
    records = []

    with patch.object(
        service,
        "_save_usage_safely",
        side_effect=lambda usage: records.append(usage),
        new_callable=AsyncMock,
    ):
        with pytest.raises(AIProviderTimeoutError):
            asyncio.run(
                _collect_stream(
                    service.stream(
                        ChatRequestSchema(messages=[{"content": "private"}]),
                        user_id=42,
                    )
                )
            )

    assert len(records) == 1
    usage = records[0]
    assert usage.status == ChatUsageStatus.FAILED.value
    assert usage.input_tokens == 1000
    assert usage.output_tokens is None
    assert usage.estimated_cost is None
    assert usage.error_code == ChatUsageErrorCode.PROVIDER_TIMEOUT.value


def test_stream_aclose_records_cancelled_terminal_once() -> None:
    delta = ChatDelta(request_id=REQUEST_ID, content="visible")
    gateway = Mock(spec=AIGateway)
    gateway.stream.return_value = _gateway_stream(
        (delta, ChatDone(request_id=REQUEST_ID, finish_reason=FinishReason.STOP))
    )
    service = ChatService(gateway, _prompt_center(), default_model_alias="general")
    records = []

    async def consume_and_close() -> None:
        with patch.object(
            service,
            "_save_usage_safely",
            side_effect=lambda usage: records.append(usage),
            new_callable=AsyncMock,
        ):
            service_stream = service.stream(
                ChatRequestSchema(messages=[{"content": "private"}]),
                user_id=42,
            )
            assert await anext(service_stream) == delta
            await service_stream.aclose()

    asyncio.run(consume_and_close())

    assert len(records) == 1
    assert records[0].status == ChatUsageStatus.CANCELLED.value
    assert records[0].error_code == ChatUsageErrorCode.CANCELLED.value


def test_usage_database_failure_does_not_replace_completed_chat_result(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    gateway = _gateway(
        GatewayChatResult(
            request_id=REQUEST_ID,
            model_alias="general",
            content="answer remains available",
            finish_reason=FinishReason.STOP,
            usage=None,
        )
    )
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    service = ChatService(
        gateway,
        _prompt_center(),
        usage_session_factory=Mock(return_value=session),
    )

    with patch(
        "app.services.chat_service.ChatUsageRepository.create",
        side_effect=SQLAlchemyError("private database detail"),
    ):
        with caplog.at_level(logging.ERROR, logger="ai_knowledge_hub"):
            response = asyncio.run(
                service.chat(
                    ChatRequestSchema(messages=[{"content": "private request"}]),
                    user_id=42,
                )
            )

    assert response.content == "answer remains available"
    session.rollback.assert_called_once_with()
    assert "ai.usage.persist_failed" in caplog.text
    assert "private database detail" not in caplog.text
    assert "private request" not in caplog.text
