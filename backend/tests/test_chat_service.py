import asyncio
import logging
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest

from app.ai.exceptions import AIProviderTimeoutError
from app.ai.gateway import AIGateway, ChatRequest, GatewayChatResult
from app.ai.provider import ChatMessage, ChatRole, FinishReason, TokenUsage
from app.schemas.ai import ChatRequestSchema
from app.services.chat_service import ChatService

REQUEST_UUID = UUID("00000000-0000-0000-0000-000000000001")
REQUEST_ID = str(REQUEST_UUID)


def _gateway(result: GatewayChatResult) -> Mock:
    gateway = Mock(spec=AIGateway)
    gateway.generate = AsyncMock(return_value=result)
    return gateway


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
    service = ChatService(gateway)
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
                ChatMessage(role=ChatRole.USER, content=user_content),
                ChatMessage(role=ChatRole.USER, content="second user message"),
            ),
            model_alias="general",
            temperature=0.7,
            max_output_tokens=256,
        )
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
        f"request_id={REQUEST_ID} user_id=42 model_alias=general "
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
    service = ChatService(gateway)

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
    service = ChatService(gateway)
    request = ChatRequestSchema(messages=[{"content": "private user content"}])

    with caplog.at_level(logging.INFO, logger="ai_knowledge_hub"):
        with pytest.raises(AIProviderTimeoutError):
            asyncio.run(service.chat(request, user_id=42))

    assert "ai.chat.success" not in caplog.text
    assert "private user content" not in caplog.text
