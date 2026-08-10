from functools import lru_cache

import httpx
from openai import AsyncOpenAI

from app.ai.provider import ChatProvider
from app.ai.providers.openai_compatible import OpenAICompatibleChatProvider
from app.core.config import settings, AIProviderConfig


def _create_openai_compatible_provider(config: AIProviderConfig) -> ChatProvider:
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

    return OpenAICompatibleChatProvider(client)


@lru_cache(maxsize=None)
def get_chat_provider(provider_key: str) -> ChatProvider:
    provider_config = settings.AI_PROVIDERS.get(provider_key)

    if provider_config is None:
        raise ValueError("Requested AI provider is not configured.")

    match provider_config.provider_type:
        case "openai_compatible":
            return _create_openai_compatible_provider(provider_config)
        case _:
            raise ValueError("Unsupported AI provider.")
