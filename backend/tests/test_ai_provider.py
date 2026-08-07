from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError
from inspect import iscoroutinefunction
from typing import get_type_hints

import pytest

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


def test_provider_contract_supports_non_stream_result() -> None:
    message = ChatMessage(
        role=ChatRole.USER,
        content="Explain AI Gateway.",
    )
    request = ProviderChatRequest(
        request_id="request-1",
        messages=(message,),
        provider_model="test-model",
        temperature=0.7,
        max_output_tokens=128,
    )
    usage = TokenUsage(
        input_tokens=4,
        output_tokens=8,
        total_tokens=12,
    )
    result = ChatResult(
        request_id=request.request_id,
        content="An AI Gateway provides a stable model boundary.",
        finish_reason=FinishReason.STOP,
        usage=usage,
    )

    assert request.messages == (message,)
    assert result.request_id == request.request_id
    assert result.finish_reason is FinishReason.STOP
    assert result.usage == usage


def test_provider_contract_allows_missing_usage() -> None:
    result = ChatResult(
        request_id="request-2",
        content="Partial provider result.",
        finish_reason=FinishReason.LENGTH,
        usage=None,
    )

    assert result.usage is None


def test_provider_contract_dtos_are_immutable() -> None:
    message = ChatMessage(
        role=ChatRole.SYSTEM,
        content="Follow the application policy.",
    )

    with pytest.raises(FrozenInstanceError):
        message.content = "Changed policy."


def test_provider_generate_is_async() -> None:
    assert iscoroutinefunction(ChatProvider.generate)


def test_streaming_event_contracts_preserve_event_specific_data() -> None:
    usage = TokenUsage(
        input_tokens=4,
        output_tokens=8,
        total_tokens=12,
    )
    events: tuple[ChatEvent, ...] = (
        ChatDelta(
            request_id="request-3",
            content="An AI",
        ),
        ChatUsageEvent(
            request_id="request-3",
            usage=usage,
        ),
        ChatDone(
            request_id="request-3",
            finish_reason=FinishReason.STOP,
        ),
    )

    assert [type(event) for event in events] == [
        ChatDelta,
        ChatUsageEvent,
        ChatDone,
    ]
    assert events[0].content == "An AI"
    assert events[1].usage == usage
    assert events[2].finish_reason is FinishReason.STOP


def test_provider_stream_returns_async_iterator_contract() -> None:
    return_type = get_type_hints(ChatProvider.stream)["return"]

    assert return_type == AsyncIterator[ChatEvent]
    assert iscoroutinefunction(ChatProvider.stream) is False
