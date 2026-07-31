from concurrent.futures import ThreadPoolExecutor
from os import getenv
from threading import Barrier
from time import time
from uuid import uuid4

import pytest

from app.db.redis_client import create_redis_client
from app.db.repositories.session_repository import (
    SessionBulkRevocation,
    SessionBulkRevocationStatus,
    SessionDeletion,
    SessionDeletionResult,
    SessionRecord,
    SessionRepository,
    SessionRotation,
    SessionRotationResult,
    SessionRevocation,
    SessionRevocationResult,
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


def test_delete_removes_session_and_user_index_in_real_redis() -> None:
    client = create_redis_client()
    repository = SessionRepository(client)

    session_id = f"logout-test-{uuid4().hex}"
    user_id = 9_999_999
    session_key = f"auth:session:{session_id}"
    index_key = f"auth:user:{user_id}:sessions"
    now = int(time())

    try:
        repository.create(
            SessionRecord(
                session_id=session_id,
                user_id=user_id,
                refresh_token_hash="a" * 64,
                created_at=now,
                last_used_at=now,
                expires_at=now + 60,
                absolute_expires_at=now + 60,
            ),
            ttl_seconds=60,
        )

        assert client.exists(session_key) == 1
        assert client.zscore(index_key, session_id) == float(now)

        repository.delete(user_id, session_id)

        assert client.exists(session_key) == 0
        assert client.zscore(index_key, session_id) is None
    finally:
        # 即使断言提前失败，也只清理本测试创建的唯一 Session。
        repository.delete(user_id, session_id)
        client.close()


def test_delete_if_matches_requires_current_hash_in_real_redis() -> None:
    client = create_redis_client()
    repository = SessionRepository(client)

    session_id = f"atomic-logout-test-{uuid4().hex}"
    user_id = 9_999_999
    session_key = f"auth:session:{session_id}"
    index_key = f"auth:user:{user_id}:sessions"
    now = int(time())

    try:
        repository.create(
            SessionRecord(
                session_id=session_id,
                user_id=user_id,
                refresh_token_hash="a" * 64,
                created_at=now,
                last_used_at=now,
                expires_at=now + 60,
                absolute_expires_at=now + 60,
            ),
            ttl_seconds=60,
        )

        rotation_result = repository.rotate(
            SessionRotation(
                session_id=session_id,
                user_id=user_id,
                expected_refresh_token_hash="a" * 64,
                new_refresh_token_hash="b" * 64,
                rotated_at=now,
                expires_at=now + 60,
                ttl_seconds=60,
            )
        )

        stale_logout_result = repository.delete_if_matches(
            SessionDeletion(
                session_id=session_id,
                user_id=user_id,
                expected_refresh_token_hash="a" * 64,
            )
        )

        stored_session = client.hgetall(session_key)

        assert rotation_result is SessionRotationResult.SUCCESS
        assert stale_logout_result is SessionDeletionResult.SESSION_MISMATCH
        assert stored_session["refresh_token_hash"] == "b" * 64
        assert client.zscore(index_key, session_id) == float(now)

        current_logout_result = repository.delete_if_matches(
            SessionDeletion(
                session_id=session_id,
                user_id=user_id,
                expected_refresh_token_hash="b" * 64,
            )
        )

        assert current_logout_result is SessionDeletionResult.SUCCESS
        assert client.exists(session_key) == 0
        assert client.zscore(index_key, session_id) is None
    finally:
        repository.delete(user_id, session_id)
        client.close()


def test_revoke_only_deletes_session_owned_by_user_in_real_redis() -> None:
    client = create_redis_client()
    repository = SessionRepository(client)

    session_id = f"revocation-test-{uuid4().hex}"
    owner_user_id = 9_999_999
    other_user_id = 8_888_888
    session_key = f"auth:session:{session_id}"
    owner_index_key = f"auth:user:{owner_user_id}:sessions"
    now = int(time())

    try:
        repository.create(
            SessionRecord(
                session_id=session_id,
                user_id=owner_user_id,
                refresh_token_hash="a" * 64,
                created_at=now,
                last_used_at=now,
                expires_at=now + 60,
                absolute_expires_at=now + 60,
            ),
            ttl_seconds=60,
        )

        wrong_owner_result = repository.revoke(
            SessionRevocation(
                session_id=session_id,
                user_id=other_user_id,
            )
        )

        assert wrong_owner_result is SessionRevocationResult.NOT_FOUND
        assert client.exists(session_key) == 1
        assert client.zscore(owner_index_key, session_id) == float(now)

        owner_result = repository.revoke(
            SessionRevocation(
                session_id=session_id,
                user_id=owner_user_id,
            )
        )

        assert owner_result is SessionRevocationResult.SUCCESS
        assert client.exists(session_key) == 0
        assert client.zscore(owner_index_key, session_id) is None

    finally:
        repository.delete(owner_user_id, session_id)
        client.close()


def test_revoke_all_deletes_only_owned_sessions_in_real_redis() -> None:
    client = create_redis_client()
    repository = SessionRepository(client)

    owner_user_id = 9_999_999
    foreign_user_id = 8_888_888

    current_session_id = f"bulk-current-{uuid4().hex}"
    other_session_id = f"bulk-other-{uuid4().hex}"
    foreign_session_id = f"bulk-foreign-{uuid4().hex}"

    current_key = f"auth:session:{current_session_id}"
    other_key = f"auth:session:{other_session_id}"
    foreign_key = f"auth:session:{foreign_session_id}"

    owner_index_key = f"auth:user:{owner_user_id}:sessions"
    foreign_index_key = f"auth:user:{foreign_user_id}:sessions"

    now = int(time())

    try:
        for session_id, user_id in [
            (current_session_id, owner_user_id),
            (other_session_id, owner_user_id),
            (foreign_session_id, foreign_user_id),
        ]:
            repository.create(
                SessionRecord(
                    session_id=session_id,
                    user_id=user_id,
                    refresh_token_hash="a" * 64,
                    created_at=now,
                    last_used_at=now,
                    expires_at=now + 60,
                    absolute_expires_at=now + 60,
                ),
                ttl_seconds=60,
            )

        client.zadd(
            owner_index_key,
            {foreign_session_id: now},
        )

        rejected_result = repository.revoke_all(
            SessionBulkRevocation(
                current_session_id=current_session_id,
                user_id=foreign_user_id,
            )
        )

        assert (
            rejected_result.status
            is SessionBulkRevocationStatus.CURRENT_SESSION_NOT_FOUND
        )
        assert client.exists(current_key) == 1
        assert client.exists(other_key) == 1
        assert client.exists(foreign_key) == 1

        result = repository.revoke_all(
            SessionBulkRevocation(
                current_session_id=current_session_id,
                user_id=owner_user_id,
            )
        )
        assert result.status is SessionBulkRevocationStatus.SUCCESS
        assert result.revoked_count == 2
        assert client.exists(current_key) == 0
        assert client.exists(other_key) == 0
        assert client.exists(foreign_key) == 1
        assert client.exists(owner_index_key) == 0
        assert client.zscore(foreign_index_key, foreign_session_id) == float(now)

    finally:
        repository.delete(owner_user_id, current_session_id)
        repository.delete(owner_user_id, other_session_id)
        repository.delete(foreign_user_id, foreign_session_id)

        # 清理故意加入错误索引的 foreign_session_id。
        client.zrem(owner_index_key, foreign_session_id)
        client.close()
