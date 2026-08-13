from unittest.mock import Mock, patch

from app.ai.gateway import AIGateway
from app.ai.prompt_center import PromptCenter
from app.api.dependencies import get_ai_gateway, get_chat_service
from app.core.config import settings


def test_get_ai_gateway_wires_settings_without_creating_provider() -> None:
    with patch("app.api.dependencies.AIGateway") as gateway_type:
        with patch("app.api.dependencies.get_chat_provider") as provider_factory:
            gateway = get_ai_gateway()

    gateway_type.assert_called_once_with(
        model_configs=settings.AI_MODELS,
        default_model_alias=settings.AI_DEFAULT_MODEL_ALIAS,
        provider_factory=provider_factory,
        max_retry_attempts=settings.AI_MAX_RETRY_ATTEMPTS,
        retry_backoff_seconds=settings.AI_RETRY_BACKOFF_SECONDS,
        total_deadline_seconds=settings.AI_TOTAL_DEADLINE_SECONDS,
        stream_idle_timeout_seconds=settings.AI_STREAM_IDLE_TIMEOUT_SECONDS,
        stream_total_deadline_seconds=(settings.AI_STREAM_TOTAL_DEADLINE_SECONDS),
    )
    provider_factory.assert_not_called()
    assert gateway is gateway_type.return_value


def test_get_chat_service_uses_injected_gateway_and_prompt_center() -> None:
    gateway = Mock(spec=AIGateway)
    prompt_center = Mock(spec=PromptCenter)

    with patch("app.api.dependencies.ChatService") as service_type:
        service = get_chat_service(gateway, prompt_center)

    service_type.assert_called_once_with(gateway, prompt_center)
    assert service is service_type.return_value
