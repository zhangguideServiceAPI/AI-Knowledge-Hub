from functools import lru_cache

import httpx
from openai import AsyncOpenAI

from app.ai.provider import ChatProvider, EmbeddingProvider
from app.ai.providers.openai_compatible import (
    OpenAICompatibleChatProvider,
    OpenAICompatibleEmbeddingProvider,
)
from app.core.config import settings, AIProviderConfig


def _create_openai_compatible_client(config: AIProviderConfig) -> AsyncOpenAI:
    """用共享 Provider 配置创建已认证、具备超时策略的异步 OpenAI 客户端。"""

    api_key = config.api_key
    base_url = config.base_url

    client = AsyncOpenAI(
        api_key=api_key.get_secret_value(),
        base_url=str(base_url),
        timeout=httpx.Timeout(
            connect=config.connect_timeout_seconds,
            read=config.read_timeout_seconds,
            write=config.read_timeout_seconds,
            pool=config.connect_timeout_seconds,
        ),
        max_retries=0,
    )

    return client


def _create_openai_compatible_chat_provider(config: AIProviderConfig) -> ChatProvider:
    """创建只承担 Chat 协议的 OpenAI-compatible Provider。"""

    return OpenAICompatibleChatProvider(_create_openai_compatible_client(config))


def _create_openai_compatible_embedding_provider(
    config: AIProviderConfig,
) -> EmbeddingProvider:
    """创建只承担 Embedding 协议的 OpenAI-compatible Provider。"""

    return OpenAICompatibleEmbeddingProvider(_create_openai_compatible_client(config))


@lru_cache(maxsize=None)
def get_chat_provider(provider_key: str) -> ChatProvider:
    """按 Provider Key 取得缓存的 ChatProvider。"""

    provider_config = settings.AI_PROVIDERS.get(provider_key)

    if provider_config is None:
        raise ValueError("Requested AI provider is not configured.")

    match provider_config.provider_type:
        case "openai_compatible":
            return _create_openai_compatible_chat_provider(provider_config)
        case _:
            raise ValueError("Unsupported AI provider.")


@lru_cache(maxsize=None)
def get_embedding_provider(provider_key: str) -> EmbeddingProvider:
    """按 Provider Key 取得缓存的 EmbeddingProvider，与 Chat Provider 互不混用。"""

    provider_config = settings.AI_PROVIDERS.get(provider_key)
    if provider_config is None:
        raise ValueError("Requested AI provider is not configured.")

    match provider_config.provider_type:
        case "openai_compatible":
            return _create_openai_compatible_embedding_provider(provider_config)
        case _:
            raise ValueError("Unsupported AI provider.")
