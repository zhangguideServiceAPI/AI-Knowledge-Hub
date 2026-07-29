from unittest.mock import Mock

import pytest
from redis import Redis

from app.services.login_rate_limiter import LoginRateLimiter

LOGIN_RATE_LIMIT_KEY = (
    "auth:login:failures:"
    "b4c9a289323b21a01c3e940f150eb9b8"
    "c542587f1abfd8f0e1cc1ffc5e475514"
)


def test_record_failure_sets_expiration_on_first_failure() -> None:
    identifier = "user@example.com"
    key = LOGIN_RATE_LIMIT_KEY

    client = Mock(spec=Redis)
    pipeline = Mock()
    client.pipeline.return_value = pipeline
    pipeline.execute.return_value = [1, True]
    limiter = LoginRateLimiter(client, window_seconds=60, max_attempts=5)

    attempts = limiter.record_failure(identifier)

    assert attempts == 1
    client.pipeline.assert_called_once_with(transaction=True)
    pipeline.incr.assert_called_once_with(key)
    pipeline.expire.assert_called_once_with(key, 60, nx=True)
    pipeline.execute.assert_called_once_with()


def test_record_failure_does_not_reset_expiration_after_first_failure() -> None:
    identifier = "user@example.com"
    key = LOGIN_RATE_LIMIT_KEY

    client = Mock(spec=Redis)
    pipeline = Mock()
    client.pipeline.return_value = pipeline
    pipeline.execute.return_value = [2, False]

    limiter = LoginRateLimiter(client, window_seconds=60, max_attempts=5)

    attempts = limiter.record_failure(identifier)

    assert attempts == 2
    pipeline.incr.assert_called_once_with(key)
    pipeline.expire.assert_called_once_with(key, 60, nx=True)
    pipeline.execute.assert_called_once_with()


@pytest.mark.parametrize(
    ("stored_attempts", "expected"),
    [
        (None, False),
        ("4", False),
        ("5", True),
    ],
)
def test_is_limited_checks_current_attempt_count(
    stored_attempts: str | None,
    expected: bool,
) -> None:
    identifier = "user@example.com"
    key = LOGIN_RATE_LIMIT_KEY

    client = Mock(spec=Redis)
    client.get.return_value = stored_attempts

    limiter = LoginRateLimiter(client, window_seconds=60, max_attempts=5)

    result = limiter.is_limited(identifier)

    assert result is expected
    client.get.assert_called_once_with(key)


def test_reset_deletes_failure_counter() -> None:
    identifier = "user@example.com"
    key = LOGIN_RATE_LIMIT_KEY

    client = Mock(spec=Redis)
    limiter = LoginRateLimiter(
        client,
        window_seconds=60,
        max_attempts=5,
    )

    limiter.reset(identifier)

    client.delete.assert_called_once_with(key)


def test_identifier_is_normalized_before_hashing() -> None:
    client = Mock(spec=Redis)
    client.get.return_value = None

    limiter = LoginRateLimiter(
        client,
        window_seconds=60,
        max_attempts=5,
    )

    limiter.is_limited("  USER@example.com  ")

    client.get.assert_called_once_with(LOGIN_RATE_LIMIT_KEY)
