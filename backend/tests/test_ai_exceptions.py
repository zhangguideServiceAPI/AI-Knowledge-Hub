import pytest

from app.ai.exceptions import (
    ProviderError,
    ProviderRateLimitError,
    ProviderStreamError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


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
