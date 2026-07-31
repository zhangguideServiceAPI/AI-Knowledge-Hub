import logging
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.repositories.session_repository import (
    SessionBulkRevocation,
    SessionBulkRevocationResult,
    SessionBulkRevocationStatus,
    SessionRecord,
    SessionRevocation,
    SessionRevocationResult,
)
from app.models.user import User


def _register_and_login(client: TestClient) -> tuple[int, str]:
    credentials = {
        "email": "user@example.com",
        "password": "password123",
    }

    register_response = client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)

    return (
        register_response.json()["id"],
        login_response.json()["access_token"],
    )


def _get_created_session_record(session_repository: Mock) -> SessionRecord:
    record = session_repository.create.call_args.args[0]
    assert isinstance(record, SessionRecord)
    return record


def _utc_json_datetime(timestamp: int) -> str:
    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def test_get_me_returns_current_user(client: TestClient) -> None:
    user_id, token = _register_and_login(client)

    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == user_id
    assert response.json()["email"] == "user@example.com"
    assert "password_hash" not in response.json()


def test_get_me_rejects_missing_token(client: TestClient) -> None:
    response = client.get(
        "/users/me",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "detail": "Invalid or missing access token.",
    }
    assert response.headers["www-authenticate"] == "Bearer"


def test_get_me_rejects_invalid_token_without_security_log_noise(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="ai_knowledge_hub"):
        response = client.get(
            "/users/me",
            headers={"Authorization": "Bearer invalid-token"},
        )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers["www-authenticate"] == "Bearer"
    assert not [
        record
        for record in caplog.records
        if record.name == "ai_knowledge_hub" and record.levelno >= logging.WARNING
    ]


def test_get_me_rejects_missing_user(client: TestClient) -> None:
    token = create_access_token(user_id=999, session_id="session-abc")

    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_me_rejects_inactive_user(
    client: TestClient,
    session: Session,
) -> None:
    user_id, token = _register_and_login(client)

    user = session.get(User, user_id)
    assert user is not None
    user.status = "disabled"
    session.commit()

    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": "User account is inactive.",
    }


def test_list_sessions_returns_current_and_other_sessions(
    client: TestClient,
    session_repository: Mock,
) -> None:
    user_id, token = _register_and_login(client)
    current_record = _get_created_session_record(session_repository)
    other_record = SessionRecord(
        session_id="other-session-id",
        user_id=user_id,
        refresh_token_hash="other-refresh-token-hash",
        created_at=current_record.created_at + 60,
        last_used_at=current_record.last_used_at + 120,
        expires_at=current_record.expires_at,
        absolute_expires_at=current_record.absolute_expires_at,
        ip_address="203.0.113.20",
        user_agent="AIKnowledgeHub/1.0 (macOS 15)",
    )
    session_repository.get.return_value = current_record
    session_repository.list_for_user.return_value = [current_record, other_record]

    response = client.get(
        "/users/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )

    payload = response.json()
    assert response.status_code == status.HTTP_200_OK
    assert payload["sessions"][0]["id"] == current_record.session_id
    assert payload["sessions"][0]["current"] is True
    assert payload["sessions"][1] == {
        "id": other_record.session_id,
        "current": False,
        "ip_address": "203.0.113.20",
        "user_agent": "AIKnowledgeHub/1.0 (macOS 15)",
        "created_at": _utc_json_datetime(other_record.created_at),
        "last_used_at": _utc_json_datetime(other_record.last_used_at),
        "expires_at": _utc_json_datetime(other_record.expires_at),
    }
    session_repository.get.assert_called_once_with(current_record.session_id)
    session_repository.list_for_user.assert_called_once_with(user_id)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/users/sessions"),
        ("DELETE", "/users/sessions/target-session-id"),
        ("DELETE", "/users/sessions"),
    ],
)
def test_session_management_requires_access_token(
    method: str,
    path: str,
    client: TestClient,
    session_repository: Mock,
) -> None:
    response = client.request(method, path)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "detail": "Invalid or missing access token.",
    }
    assert response.headers["www-authenticate"] == "Bearer"
    session_repository.get.assert_not_called()


def test_list_sessions_rejects_inactive_user(
    client: TestClient,
    session: Session,
    session_repository: Mock,
) -> None:
    user_id, token = _register_and_login(client)
    user = session.get(User, user_id)
    assert user is not None
    user.status = "disabled"
    session.commit()

    response = client.get(
        "/users/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": "User account is inactive.",
    }
    session_repository.get.assert_not_called()


def test_revoke_session_returns_no_content(
    client: TestClient,
    session_repository: Mock,
) -> None:
    user_id, token = _register_and_login(client)
    current_record = _get_created_session_record(session_repository)
    target_session_id = "other-session-id"
    session_repository.get.return_value = current_record
    session_repository.revoke.return_value = SessionRevocationResult.SUCCESS

    response = client.delete(
        f"/users/sessions/{target_session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
    session_repository.revoke.assert_called_once_with(
        SessionRevocation(
            session_id=target_session_id,
            user_id=user_id,
        )
    )


def test_revoke_session_returns_not_found_without_sensitive_log_data(
    client: TestClient,
    session_repository: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _user_id, token = _register_and_login(client)
    current_record = _get_created_session_record(session_repository)
    target_session_id = "missing-or-foreign-session-id"
    session_repository.get.return_value = current_record
    session_repository.revoke.return_value = SessionRevocationResult.NOT_FOUND

    with caplog.at_level(logging.WARNING, logger="ai_knowledge_hub"):
        response = client.delete(
            f"/users/sessions/{target_session_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Session not found."}
    assert token not in caplog.text
    assert current_record.session_id not in caplog.text
    assert target_session_id not in caplog.text


def test_revoke_all_sessions_returns_no_content(
    client: TestClient,
    session_repository: Mock,
) -> None:
    user_id, token = _register_and_login(client)
    current_record = _get_created_session_record(session_repository)
    session_repository.get.return_value = current_record
    session_repository.revoke_all.return_value = SessionBulkRevocationResult(
        status=SessionBulkRevocationStatus.SUCCESS,
        revoked_count=2,
    )

    response = client.delete(
        "/users/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
    session_repository.revoke_all.assert_called_once_with(
        SessionBulkRevocation(
            current_session_id=current_record.session_id,
            user_id=user_id,
        )
    )
    session_repository.revoke.assert_not_called()


def test_revoke_all_sessions_returns_unauthorized_when_current_session_disappears(
    client: TestClient,
    session_repository: Mock,
) -> None:
    _user_id, token = _register_and_login(client)
    current_record = _get_created_session_record(session_repository)
    session_repository.get.return_value = current_record
    session_repository.revoke_all.return_value = SessionBulkRevocationResult(
        status=SessionBulkRevocationStatus.CURRENT_SESSION_NOT_FOUND,
        revoked_count=0,
    )

    response = client.delete(
        "/users/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "detail": "Invalid or missing access token.",
    }
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/users/sessions"),
        ("DELETE", "/users/sessions/target-session-id"),
        ("DELETE", "/users/sessions"),
    ],
)
def test_session_management_returns_service_unavailable_for_redis_error(
    method: str,
    path: str,
    client: TestClient,
    session_repository: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _user_id, token = _register_and_login(client)
    current_record = _get_created_session_record(session_repository)
    session_repository.get.side_effect = RedisError("test Redis outage")

    with caplog.at_level(logging.ERROR, logger="ai_knowledge_hub"):
        response = client.request(
            method,
            path,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {
        "detail": "Authentication service is temporarily unavailable.",
    }
    assert (
        "ai_knowledge_hub",
        logging.ERROR,
        f"auth.redis.unavailable method={method} path={path} error_type=RedisError",
    ) in caplog.record_tuples
    assert "test Redis outage" not in caplog.text
    assert token not in caplog.text
    assert current_record.session_id not in caplog.text
