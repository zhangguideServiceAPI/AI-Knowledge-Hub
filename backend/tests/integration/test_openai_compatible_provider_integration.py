import asyncio
from os import getenv

import pytest

from app.ai.exceptions import ProviderError
from app.ai.factory import get_chat_provider
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

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        getenv("RUN_AI_INTEGRATION_TESTS") != "1",
        reason="Set RUN_AI_INTEGRATION_TESTS=1 to run real AI provider tests.",
    ),
]


@pytest.fixture(autouse=True)
def suppress_http_client_request_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING", logger="httpx")
    caplog.set_level("WARNING", logger="httpcore")


def _integration_target() -> tuple[str, str]:
    provider_key = getenv("AI_INTEGRATION_PROVIDER_KEY")
    provider_model = getenv("AI_INTEGRATION_MODEL")

    if provider_key is None or provider_model is None:
        pytest.skip(
            "Set AI_INTEGRATION_PROVIDER_KEY and AI_INTEGRATION_MODEL "
            "to run real AI provider tests."
        )

    return provider_key, provider_model


def _provider_request(provider_model: str, request_id: str) -> ProviderChatRequest:
    return ProviderChatRequest(
        request_id=request_id,
        messages=(
            ChatMessage(
                role=ChatRole.SYSTEM,
                content="Reply briefly and plainly.",
            ),
            ChatMessage(
                role=ChatRole.USER,
                content="Reply with the word pong.",
            ),
        ),
        provider_model=provider_model,
        temperature=0.0,
        max_output_tokens=16,
    )


def _assert_usage_is_valid(usage: TokenUsage) -> None:
    token_counts = (
        usage.input_tokens,
        usage.output_tokens,
        usage.total_tokens,
    )
    assert all(count is None or count >= 0 for count in token_counts)

    if all(count is not None for count in token_counts):
        assert usage.total_tokens == usage.input_tokens + usage.output_tokens


def _safe_provider_failure(error: ProviderError) -> AssertionError:
    sdk_error_type = (
        type(error.__cause__).__name__ if error.__cause__ is not None else "unknown"
    )
    return AssertionError(
        f"Real provider call failed safely: {type(error).__name__} "
        f"caused by {sdk_error_type}."
    )


async def _generate_and_close(
    provider: OpenAICompatibleChatProvider,
    request: ProviderChatRequest,
) -> ChatResult:
    try:
        try:
            return await provider.generate(request)
        except ProviderError as error:
            raise _safe_provider_failure(error) from None
    finally:
        await provider.client.close()
        get_chat_provider.cache_clear()


async def _stream_and_close(
    provider: OpenAICompatibleChatProvider,
    request: ProviderChatRequest,
) -> list[ChatDelta | ChatUsageEvent | ChatDone]:
    try:
        try:
            return [event async for event in provider.stream(request)]
        except ProviderError as error:
            raise _safe_provider_failure(error) from None
    finally:
        await provider.client.close()
        get_chat_provider.cache_clear()


def test_real_openai_compatible_provider_generate() -> None:
    provider_key, provider_model = _integration_target()
    provider = get_chat_provider(provider_key)
    assert isinstance(provider, OpenAICompatibleChatProvider)
    request = _provider_request(
        provider_model,
        request_id="integration-non-stream",
    )

    result = asyncio.run(_generate_and_close(provider, request))

    assert result.request_id == request.request_id
    assert result.content.strip()
    assert result.finish_reason in {
        FinishReason.STOP,
        FinishReason.LENGTH,
        FinishReason.CONTENT_FILTER,
    }
    if result.usage is not None:
        _assert_usage_is_valid(result.usage)


def test_real_openai_compatible_provider_stream() -> None:
    provider_key, provider_model = _integration_target()
    provider = get_chat_provider(provider_key)
    assert isinstance(provider, OpenAICompatibleChatProvider)
    request = _provider_request(
        provider_model,
        request_id="integration-stream",
    )

    events = asyncio.run(_stream_and_close(provider, request))

    assert events
    assert all(event.request_id == request.request_id for event in events)
    assert isinstance(events[-1], ChatDone)
    assert "".join(
        event.content for event in events if isinstance(event, ChatDelta)
    ).strip()

    usage_events = [event for event in events if isinstance(event, ChatUsageEvent)]
    assert len(usage_events) <= 1
    if usage_events:
        _assert_usage_is_valid(usage_events[0].usage)
