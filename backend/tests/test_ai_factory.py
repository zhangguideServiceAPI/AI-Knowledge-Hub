from collections.abc import Iterator
from unittest.mock import Mock

import httpx
import pytest

from app.ai import factory as ai_factory
from app.ai.providers.openai_compatible import OpenAICompatibleChatProvider
from app.core.config import AIProviderConfig


@pytest.fixture(autouse=True)
def clear_chat_provider_cache() -> Iterator[None]:
    ai_factory.get_chat_provider.cache_clear()
    try:
        yield
    finally:
        ai_factory.get_chat_provider.cache_clear()


def _provider_config(
    *,
    api_key: str,
    base_url: str,
    connect_timeout_seconds: float = 5.0,
    read_timeout_seconds: float = 60.0,
) -> AIProviderConfig:
    return AIProviderConfig(
        provider_type="openai_compatible",
        api_key=api_key,
        base_url=base_url,
        connect_timeout_seconds=connect_timeout_seconds,
        read_timeout_seconds=read_timeout_seconds,
    )


def test_get_chat_provider_creates_and_caches_openai_compatible_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_client = Mock()
    sdk_client_factory = Mock(return_value=sdk_client)
    monkeypatch.setattr(
        ai_factory.settings,
        "AI_PROVIDERS",
        {
            "primary": _provider_config(
                api_key="test-primary-api-key",
                base_url="https://primary.example.com/v1",
                connect_timeout_seconds=0.5,
                read_timeout_seconds=1.25,
            )
        },
    )
    monkeypatch.setattr(ai_factory, "AsyncOpenAI", sdk_client_factory)

    first_provider = ai_factory.get_chat_provider("primary")
    second_provider = ai_factory.get_chat_provider("primary")

    assert isinstance(first_provider, OpenAICompatibleChatProvider)
    assert second_provider is first_provider
    assert first_provider.client is sdk_client
    sdk_client_factory.assert_called_once()

    arguments, keyword_arguments = sdk_client_factory.call_args
    assert arguments == ()
    assert keyword_arguments["api_key"] == "test-primary-api-key"
    assert keyword_arguments["base_url"] == "https://primary.example.com/v1"
    assert keyword_arguments["max_retries"] == 0

    timeout = keyword_arguments["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 0.5
    assert timeout.read == 1.25
    assert timeout.write == 1.25
    assert timeout.pool == 0.5


def test_get_chat_provider_caches_each_provider_key_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_client = Mock()
    backup_client = Mock()
    sdk_client_factory = Mock(
        side_effect=[
            primary_client,
            backup_client,
        ]
    )
    monkeypatch.setattr(
        ai_factory.settings,
        "AI_PROVIDERS",
        {
            "primary": _provider_config(
                api_key="test-primary-api-key",
                base_url="https://primary.example.com/v1",
            ),
            "backup": _provider_config(
                api_key="test-backup-api-key",
                base_url="https://backup.example.com/v1",
            ),
        },
    )
    monkeypatch.setattr(ai_factory, "AsyncOpenAI", sdk_client_factory)

    primary_provider = ai_factory.get_chat_provider("primary")
    backup_provider = ai_factory.get_chat_provider("backup")
    cached_primary_provider = ai_factory.get_chat_provider("primary")

    assert primary_provider is cached_primary_provider
    assert primary_provider is not backup_provider
    assert primary_provider.client is primary_client
    assert backup_provider.client is backup_client
    assert sdk_client_factory.call_count == 2
    assert [call.kwargs["base_url"] for call in sdk_client_factory.call_args_list] == [
        "https://primary.example.com/v1",
        "https://backup.example.com/v1",
    ]


def test_get_chat_provider_rejects_unknown_key_before_creating_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_client_factory = Mock()
    monkeypatch.setattr(
        ai_factory.settings,
        "AI_PROVIDERS",
        {
            "primary": _provider_config(
                api_key="test-primary-api-key",
                base_url="https://primary.example.com/v1",
            )
        },
    )
    monkeypatch.setattr(ai_factory, "AsyncOpenAI", sdk_client_factory)

    with pytest.raises(
        ValueError,
        match="Requested AI provider is not configured",
    ):
        ai_factory.get_chat_provider("missing")

    sdk_client_factory.assert_not_called()
    assert ai_factory.get_chat_provider.cache_info().currsize == 0
