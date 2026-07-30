from unittest.mock import Mock

import pytest
from redis import Redis

from app.services.login_rate_limiter import LoginRateLimiter

LOGIN_RATE_LIMIT_KEY = (
    "auth:login:failures:"
    "b4c9a289323b21a01c3e940f150eb9b8"
    "c542587f1abfd8f0e1cc1ffc5e475514"
)


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
    pipeline = client.pipeline.return_value
    pipeline.execute.return_value = [1, True]

    limiter = LoginRateLimiter(
        client,
        window_seconds=60,
        max_attempts=5,
    )

    limiter.reserve_attempt("  USER@example.com  ")

    pipeline.incr.assert_called_once_with(LOGIN_RATE_LIMIT_KEY)


@pytest.mark.parametrize(
    ("attempts", "expected"),
    [
        (1, True),
        (5, True),
        (6, False),
    ],
)
def test_reserve_attempt_enforces_atomic_limit(
    attempts: int,
    expected: bool,
) -> None:
    client = Mock(spec=Redis)
    pipeline = Mock()
    client.pipeline.return_value = pipeline
    pipeline.execute.return_value = [attempts, False]

    limiter = LoginRateLimiter(
        client,
        window_seconds=60,
        max_attempts=5,
    )

    result = limiter.reserve_attempt("user@example.com")

    assert result is expected
    client.pipeline.assert_called_once_with(transaction=True)
    pipeline.incr.assert_called_once_with(LOGIN_RATE_LIMIT_KEY)
    pipeline.expire.assert_called_once_with(
        LOGIN_RATE_LIMIT_KEY,
        60,
        nx=True,
    )
    pipeline.execute.assert_called_once_with()
