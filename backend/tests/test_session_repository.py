from unittest.mock import ANY, Mock

import pytest
from redis import Redis

from app.db.repositories.session_repository import (
    SessionRecord,
    SessionRepository,
    SessionRotation,
    SessionRotationResult,
)


@pytest.mark.parametrize(
    ("redis_result", "expected_result"),
    [
        (0, SessionRotationResult.SESSION_NOT_FOUND),
        (-1, SessionRotationResult.TOKEN_MISMATCH),
    ],
)
def test_rotate_maps_redis_failure_result(
    redis_result: int,
    expected_result: SessionRotationResult,
) -> None:
    client = Mock(spec=Redis)
    client.eval.return_value = redis_result
    repository = SessionRepository(client)

    rotation = SessionRotation(
        session_id="abc",
        user_id=42,
        expected_refresh_token_hash="a" * 64,
        new_refresh_token_hash="b" * 64,
        rotated_at=2_000,
        expires_at=605_800,
        ttl_seconds=603_800,
    )

    result = repository.rotate(rotation)

    assert result is expected_result


def test_rotate_raises_when_script_returns_unexpected_result() -> None:
    client = Mock(spec=Redis)
    client.eval.return_value = 99
    repository = SessionRepository(client)

    rotation = SessionRotation(
        session_id="abc",
        user_id=42,
        expected_refresh_token_hash="a" * 64,
        new_refresh_token_hash="b" * 64,
        rotated_at=2_000,
        expires_at=605_800,
        ttl_seconds=603_800,
    )

    with pytest.raises(
        ValueError,
        match="Unexpected session rotation result: 99",
    ):
        repository.rotate(rotation)


def test_rotate_returns_success_when_current_hash_matches() -> None:
    client = Mock(spec=Redis)
    client.eval.return_value = 1
    repository = SessionRepository(client)

    rotation = SessionRotation(
        session_id="abc",
        user_id=42,
        expected_refresh_token_hash="a" * 64,
        new_refresh_token_hash="b" * 64,
        rotated_at=2_000,
        expires_at=605_800,
        ttl_seconds=603_800,
    )

    result = repository.rotate(rotation)

    assert result is SessionRotationResult.SUCCESS
    client.eval.assert_called_once_with(
        ANY,
        2,
        "auth:session:abc",
        "auth:user:42:sessions",
        "a" * 64,
        "b" * 64,
        2_000,
        605_800,
        603_800,
        "abc",
    )


def test_create_stores_session_hash_with_ttl() -> None:
    client = Mock(spec=Redis)
    pipeline = Mock()
    client.pipeline.return_value = pipeline
    # pipeline = client.pipeline.return_value 这种也是可以的

    session = SessionRecord(
        session_id="abc",
        user_id=42,
        refresh_token_hash="a" * 64,
        created_at=1_000,
        last_used_at=1_100,
        expires_at=605_800,
        absolute_expires_at=2_593_000,
    )
    repository = SessionRepository(client)
    repository.create(session, ttl_seconds=604_800)

    client.pipeline.assert_called_once_with(transaction=True)
    pipeline.hset.assert_called_once_with(
        "auth:session:abc",
        mapping={
            "user_id": "42",
            "refresh_token_hash": "a" * 64,
            "created_at": "1000",
            "last_used_at": "1100",
            "expires_at": "605800",
            "absolute_expires_at": "2593000",
        },
    )
    pipeline.expire.assert_called_once_with(
        "auth:session:abc",
        604_800,
    )
    pipeline.zadd.assert_called_once_with(
        "auth:user:42:sessions",
        {"abc": 1_100},
    )
    pipeline.execute.assert_called_once_with()


def test_get_returns_session_record() -> None:
    client = Mock(spec=Redis)
    client.hgetall.return_value = {
        "user_id": "42",
        "refresh_token_hash": "a" * 64,
        "created_at": "1000",
        "last_used_at": "1100",
        "expires_at": "605800",
        "absolute_expires_at": "2593000",
    }
    repository = SessionRepository(client)

    result = repository.get("abc")

    assert result == SessionRecord(
        session_id="abc",
        user_id=42,
        refresh_token_hash="a" * 64,
        created_at=1_000,
        last_used_at=1_100,
        expires_at=605_800,
        absolute_expires_at=2_593_000,
    )
    client.hgetall.assert_called_once_with("auth:session:abc")


def test_get_returns_none_when_session_does_not_exist() -> None:
    client = Mock(spec=Redis)
    client.hgetall.return_value = {}

    repository = SessionRepository(client)

    result = repository.get("missing")

    assert result is None
    client.hgetall.assert_called_once_with("auth:session:missing")


def test_delete_removes_session_and_user_index() -> None:
    client = Mock(spec=Redis)
    pipeline = client.pipeline.return_value
    repository = SessionRepository(client)

    repository.delete(
        user_id=42,
        session_id="abc",
    )

    client.pipeline.assert_called_once_with(transaction=True)
    pipeline.delete.assert_called_once_with("auth:session:abc")
    pipeline.zrem.assert_called_once_with(
        "auth:user:42:sessions",
        "abc",
    )
    pipeline.execute.assert_called_once_with()


def test_list_for_user_returns_sessions_and_removes_stale_index() -> None:
    client = Mock(spec=Redis)
    client.zrevrange.return_value = ["active", "expired"]

    pipeline = client.pipeline.return_value
    pipeline.execute.return_value = [
        {
            "user_id": "42",
            "refresh_token_hash": "a" * 64,
            "created_at": "1000",
            "last_used_at": "1100",
            "expires_at": "605800",
            "absolute_expires_at": "2593000",
        },
        {},
    ]

    repository = SessionRepository(client)

    result = repository.list_for_user(42)

    assert result == [
        SessionRecord(
            session_id="active",
            user_id=42,
            refresh_token_hash="a" * 64,
            created_at=1_000,
            last_used_at=1_100,
            expires_at=605_800,
            absolute_expires_at=2_593_000,
        )
    ]
    client.zrevrange.assert_called_once_with(
        "auth:user:42:sessions",
        0,
        -1,
    )
    client.pipeline.assert_called_once_with(transaction=False)
    pipeline.hgetall.assert_any_call("auth:session:active")
    pipeline.hgetall.assert_any_call("auth:session:expired")
    assert pipeline.hgetall.call_count == 2
    pipeline.execute.assert_called_once_with()
    client.zrem.assert_called_once_with(
        "auth:user:42:sessions",
        "expired",
    )


def test_list_for_user_returns_empty_list_when_index_is_empty() -> None:
    client = Mock(spec=Redis)
    client.zrevrange.return_value = []
    repository = SessionRepository(client)

    result = repository.list_for_user(42)

    assert result == []
    client.zrevrange.assert_called_once_with(
        "auth:user:42:sessions",
        0,
        -1,
    )
    client.pipeline.assert_not_called()
    client.zrem.assert_not_called()
