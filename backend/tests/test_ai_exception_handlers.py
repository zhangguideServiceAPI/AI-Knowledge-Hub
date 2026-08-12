from unittest.mock import patch

from fastapi import FastAPI, status
from fastapi.testclient import TestClient
import pytest

from app.ai.exceptions import (
    AIError,
    AIInvalidModelError,
    AIInvalidRequestError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.api.exception_handlers import register_exception_handlers


def _client_raising(error: AIError) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/ai/chat")
    async def raise_ai_error() -> None:
        raise error

    return TestClient(app)


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code", "expected_detail"),
    [
        (
            AIInvalidModelError("raw model detail"),
            status.HTTP_400_BAD_REQUEST,
            "ai_invalid_model",
            "Requested AI model is not available.",
        ),
        (
            AIInvalidRequestError("raw request detail"),
            status.HTTP_400_BAD_REQUEST,
            "ai_invalid_request",
            "AI request parameters are invalid.",
        ),
        (
            AIProviderRateLimitError("raw rate-limit detail"),
            status.HTTP_429_TOO_MANY_REQUESTS,
            "ai_provider_rate_limit",
            "AI service is temporarily rate limited.",
        ),
        (
            AIProviderTimeoutError("raw timeout detail"),
            status.HTTP_504_GATEWAY_TIMEOUT,
            "ai_provider_timeout",
            "AI service timed out.",
        ),
        (
            AIProviderUnavailableError("raw unavailable detail"),
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ai_provider_unavailable",
            "AI service is temporarily unavailable.",
        ),
    ],
)
def test_ai_error_handler_maps_known_domain_errors_to_safe_http_responses(
    error: AIError,
    expected_status: int,
    expected_code: str,
    expected_detail: str,
) -> None:
    client = _client_raising(error)

    with patch("app.api.exception_handlers.logger") as logger:
        response = client.post("/ai/chat")

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": expected_detail,
        "code": expected_code,
    }
    assert str(error) not in response.text
    logger.error.assert_called_once_with(
        "ai.request.failed method=%s path=%s code=%s error_type=%s",
        "POST",
        "/ai/chat",
        expected_code,
        type(error).__name__,
    )


def test_ai_error_handler_uses_safe_fallback_for_unknown_domain_error() -> None:
    class FutureAIError(AIError):
        pass

    error = FutureAIError("raw future error detail")
    client = _client_raising(error)

    with patch("app.api.exception_handlers.logger") as logger:
        response = client.post("/ai/chat")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {
        "detail": "AI service failed to process the request.",
        "code": "ai_internal_error",
    }
    assert str(error) not in response.text
    logger.error.assert_called_once_with(
        "ai.request.failed method=%s path=%s code=%s error_type=%s",
        "POST",
        "/ai/chat",
        "ai_internal_error",
        "FutureAIError",
    )
