import asyncio
from datetime import datetime
from os import getenv

from fastapi import status
from httpx import ASGITransport, AsyncClient
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
from app.api.dependencies import get_current_user
from app.core.config import settings
from app.main import app
from app.schemas.ai import ChatResponseSchema
from app.schemas.user import UserResponse

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


def _integration_model_alias() -> str:
    model_alias = getenv("AI_INTEGRATION_MODEL_ALIAS")
    if model_alias is None:
        model_alias = settings.AI_DEFAULT_MODEL_ALIAS

    if model_alias is None or model_alias not in settings.AI_MODELS:
        pytest.skip("Set AI_INTEGRATION_MODEL_ALIAS to a configured AI model alias.")

    return model_alias


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


async def _call_real_non_stream_chat_api(
    *,
    model_alias: str,
    provider: OpenAICompatibleChatProvider,
) -> ChatResponseSchema:
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/ai/chat",
                headers={"Authorization": "Bearer integration-test-token"},
                json={
                    "messages": [{"content": "Reply with the word pong."}],
                    "model": model_alias,
                    "temperature": 0.0,
                    "max_output_tokens": 16,
                },
            )
    finally:
        await provider.client.close()
        get_chat_provider.cache_clear()

    assert response.status_code == status.HTTP_200_OK, response.text
    return ChatResponseSchema.model_validate(response.json())


def test_real_non_stream_chat_api_vertical_path() -> None:
    model_alias = _integration_model_alias()
    model_config = settings.AI_MODELS[model_alias]
    provider = get_chat_provider(model_config.provider_key)
    assert isinstance(provider, OpenAICompatibleChatProvider)

    timestamp = datetime(2026, 8, 12, 12, 0)
    current_user = UserResponse(
        id=42,
        email="ai-integration@example.com",
        nickname=None,
        avatar_url=None,
        status="active",
        created_at=timestamp,
        updated_at=timestamp,
    )
    app.dependency_overrides[get_current_user] = lambda: current_user

    try:
        result = asyncio.run(
            _call_real_non_stream_chat_api(
                model_alias=model_alias,
                provider=provider,
            )
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert result.request_id
    assert result.model == model_alias
    assert result.content.strip()
    assert result.finish_reason in {
        FinishReason.STOP,
        FinishReason.LENGTH,
        FinishReason.CONTENT_FILTER,
    }
    if result.usage is not None:
        _assert_usage_is_valid(
            TokenUsage(
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                total_tokens=result.usage.total_tokens,
            )
        )
