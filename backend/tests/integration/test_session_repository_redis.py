from concurrent.futures import ThreadPoolExecutor
from os import getenv
from threading import Barrier
from time import time
from uuid import uuid4

import pytest

from app.db.redis_client import create_redis_client
from app.db.repositories.session_repository import (
    SessionRecord,
    SessionRepository,
    SessionRotation,
    SessionRotationResult,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        getenv("RUN_REDIS_INTEGRATION_TESTS") != "1",
        reason="Set RUN_REDIS_INTEGRATION_TESTS=1 to run real Redis tests.",
    ),
]


def test_rotate_updates_session_in_real_redis() -> None:
    client = create_redis_client()
    repository = SessionRepository(client)

    session_id = f"rotation-test-{uuid4().hex}"
    user_id = 9_999_999
    session_key = f"auth:session:{session_id}"
    index_key = f"auth:user:{user_id}:sessions"

    now = int(time())
    expires_at = now + 60

    try:
        repository.create(
            SessionRecord(
                session_id=session_id,
                user_id=user_id,
                refresh_token_hash="a" * 64,
                created_at=now,
                last_used_at=now - 1,
                expires_at=expires_at,
                absolute_expires_at=expires_at,
            ),
            ttl_seconds=60,
        )

        result = repository.rotate(
            SessionRotation(
                session_id=session_id,
                user_id=user_id,
                expected_refresh_token_hash="a" * 64,
                new_refresh_token_hash="b" * 64,
                rotated_at=now,
                expires_at=expires_at,
                ttl_seconds=60,
            )
        )

        stored_session = client.hgetall(session_key)
        ttl = client.ttl(session_key)
        score = client.zscore(index_key, session_id)

        assert result is SessionRotationResult.SUCCESS
        assert stored_session["refresh_token_hash"] == "b" * 64
        assert stored_session["last_used_at"] == str(now)
        assert stored_session["expires_at"] == str(expires_at)
        assert 55 <= ttl <= 60
        assert score == float(now)
    finally:
        # 只清理本测试创建的唯一 Session，不能清空共享的开发 Redis。
        repository.delete(user_id, session_id)
        client.close()


def test_rotate_revokes_session_when_old_token_is_reused() -> None:
    client = create_redis_client()
    repository = SessionRepository(client)

    session_id = f"replay-test-{uuid4().hex}"
    user_id = 9_999_999
    session_key = f"auth:session:{session_id}"
    index_key = f"auth:user:{user_id}:sessions"

    now = int(time())
    expires_at = now + 60

    try:
        repository.create(
            SessionRecord(
                session_id=session_id,
                user_id=user_id,
                refresh_token_hash="a" * 64,
                created_at=now,
                last_used_at=now - 1,
                expires_at=expires_at,
                absolute_expires_at=expires_at,
            ),
            ttl_seconds=60,
        )

        rotation = SessionRotation(
            session_id=session_id,
            user_id=user_id,
            expected_refresh_token_hash="a" * 64,
            new_refresh_token_hash="b" * 64,
            rotated_at=now,
            expires_at=expires_at,
            ttl_seconds=60,
        )

        first_result = repository.rotate(rotation)
        replay_result = repository.rotate(rotation)

        assert first_result is SessionRotationResult.SUCCESS
        assert replay_result is SessionRotationResult.TOKEN_MISMATCH
        assert client.exists(session_key) == 0
        assert client.zscore(index_key, session_id) is None
    finally:
        repository.delete(user_id, session_id)
        client.close()


def test_concurrent_rotate_allows_only_one_success() -> None:
    client = create_redis_client()
    repository = SessionRepository(client)

    session_id = f"concurrent-test-{uuid4().hex}"
    user_id = 9_999_999
    session_key = f"auth:session:{session_id}"
    index_key = f"auth:user:{user_id}:sessions"

    now = int(time())
    expires_at = now + 60
    barrier = Barrier(2)

    try:
        repository.create(
            SessionRecord(
                session_id=session_id,
                user_id=user_id,
                refresh_token_hash="a" * 64,
                created_at=now,
                last_used_at=now - 1,
                expires_at=expires_at,
                absolute_expires_at=expires_at,
            ),
            ttl_seconds=60,
        )

        def run_rotation(new_hash: str) -> SessionRotationResult:
            # 两个线程都到达这里后，再一起继续调用 Redis。
            barrier.wait()
            return repository.rotate(
                SessionRotation(
                    session_id=session_id,
                    user_id=user_id,
                    expected_refresh_token_hash="a" * 64,
                    new_refresh_token_hash=new_hash,
                    rotated_at=now,
                    expires_at=expires_at,
                    ttl_seconds=60,
                )
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(run_rotation, "b" * 64)
            second_future = executor.submit(run_rotation, "c" * 64)

            results = [
                first_future.result(),
                second_future.result(),
            ]

        assert results.count(SessionRotationResult.SUCCESS) == 1
        assert results.count(SessionRotationResult.TOKEN_MISMATCH) == 1

        # 失败的并发请求被视为 Replay，因此最终撤销整个当前 Session。
        assert client.exists(session_key) == 0
        assert client.zscore(index_key, session_id) is None

    finally:
        repository.delete(user_id, session_id)
        client.close()
