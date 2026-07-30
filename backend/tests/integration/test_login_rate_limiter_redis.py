from concurrent.futures import ThreadPoolExecutor
from os import getenv
from threading import Barrier
from uuid import uuid4

import pytest

from app.db.redis_client import create_redis_client
from app.services.login_rate_limiter import LoginRateLimiter

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        getenv("RUN_REDIS_INTEGRATION_TESTS") != "1",
        reason="Set RUN_REDIS_INTEGRATION_TESTS=1 to run real Redis tests.",
    ),
]


def test_concurrent_reservations_enforce_attempt_limit() -> None:
    client = create_redis_client()
    limiter = LoginRateLimiter(
        client,
        window_seconds=60,
        max_attempts=5,
    )
    identifier = f"concurrent-{uuid4().hex}@example.com"
    request_count = 20
    barrier = Barrier(request_count)

    try:

        def reserve_attempt() -> bool:
            barrier.wait()
            return limiter.reserve_attempt(identifier)

        with ThreadPoolExecutor(max_workers=request_count) as executor:
            futures = [executor.submit(reserve_attempt) for _ in range(request_count)]
            results = [future.result() for future in futures]

        assert results.count(True) == 5
        assert results.count(False) == 15

    finally:
        limiter.reset(identifier)
        client.close()
