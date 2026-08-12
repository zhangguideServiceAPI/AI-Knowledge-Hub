import pytest

from app.ai.exceptions import (
    AIError,
    AIInvalidModelError,
    AIInvalidRequestError,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    ProviderError,
    ProviderRateLimitError,
    ProviderStreamError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


def test_invalid_model_error_uses_ai_gateway_error_base() -> None:
    error = AIInvalidModelError()

    assert isinstance(error, AIError)
    assert not isinstance(error, ProviderError)


def test_invalid_request_error_uses_ai_gateway_error_base() -> None:
    error = AIInvalidRequestError()

    assert isinstance(error, AIError)
    assert not isinstance(error, ProviderError)


@pytest.mark.parametrize(
    "error_type",
    [
        AIProviderRateLimitError,
        AIProviderTimeoutError,
        AIProviderUnavailableError,
    ],
)
def test_ai_provider_errors_share_gateway_provider_error_base(
    error_type: type[AIProviderError],
) -> None:
    error = error_type()

    assert isinstance(error, AIProviderError)
    assert isinstance(error, AIError)
    assert not isinstance(error, ProviderError)


@pytest.mark.parametrize(
    "error_type",
    [
        ProviderRateLimitError,
        ProviderTimeoutError,
        ProviderUnavailableError,
        ProviderStreamError,
    ],
)
def test_provider_errors_share_provider_error_base(
    error_type: type[ProviderError],
) -> None:
    error = error_type()

    assert isinstance(error, ProviderError)
    assert isinstance(error, Exception)
