import logging
from unittest.mock import Mock

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from jose import jwt
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_refresh_token, hash_refresh_token
from app.db.repositories.session_repository import (
    SessionDeletion,
    SessionDeletionResult,
    SessionRotationResult,
)
from app.models.user import User


def test_register_returns_created_user(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={
            "email": "USER@example.com",
            "password": "password123",
        },
    )

    response_data = response.json()

    assert response.status_code == status.HTTP_201_CREATED
    assert response_data["email"] == "user@example.com"
    assert "password" not in response_data
    assert "password_hash" not in response_data


def test_register_returns_conflict_for_existing_email(client: TestClient) -> None:
    payload = {
        "email": "user@example.com",
        "password": "password123",
    }

    first_response = client.post("/auth/register", json=payload)
    response = client.post("/auth/register", json=payload)

    assert first_response.status_code == status.HTTP_201_CREATED
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "detail": "Email is already registered.",
    }


def test_register_returns_validation_error(client: TestClient) -> None:
    payload = {
        "email": "invalid-email",
        "password": "short",
    }

    response = client.post("/auth/register", json=payload)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_login_returns_token_pair(client: TestClient) -> None:
    credentials = {
        "email": "user@example.com",
        "password": "password123",
    }

    client.post("/auth/register", json=credentials)

    response = client.post("/auth/login", json=credentials)
    response_data = response.json()
    access_payload = jwt.decode(
        response_data["access_token"],
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )
    refresh_payload = jwt.decode(
        response_data["refresh_token"],
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert response.status_code == status.HTTP_200_OK
    assert response_data["token_type"] == "bearer"
    assert response_data["expires_in"] == (
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    assert response_data["refresh_expires_in"] == settings.SESSION_TTL_DAYS * 86_400
    assert access_payload["type"] == "access"
    assert refresh_payload["type"] == "refresh"
    assert refresh_payload["sub"] == access_payload["sub"]
    assert refresh_payload["sid"]
    assert refresh_payload["jti"]
    assert (
        refresh_payload["exp"] - refresh_payload["iat"]
        == response_data["refresh_expires_in"]
    )


def test_login_returns_unauthorized_for_unknown_email(
    client: TestClient,
) -> None:
    response = client.post(
        "/auth/login",
        json={
            "email": "unknow@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "detail": "Invalid email or password.",
    }
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_returns_too_many_requests_when_rate_limited(
    client: TestClient,
    login_rate_limiter: Mock,
) -> None:
    login_rate_limiter.reserve_attempt.return_value = False

    response = client.post(
        "/auth/login",
        json={
            "email": "USER@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json() == {
        "detail": "Too many login attempts. Try again later.",
    }
    login_rate_limiter.reserve_attempt.assert_called_once_with("user@example.com")


def test_login_returns_service_unavailable_when_rate_limit_check_fails(
    client: TestClient,
    login_rate_limiter: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    login_rate_limiter.reserve_attempt.side_effect = RedisError("test Redis outage")

    with caplog.at_level(logging.ERROR, logger="ai_knowledge_hub"):
        response = client.post(
            "/auth/login",
            json={
                "email": "user@example.com",
                "password": "password123",
            },
        )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {
        "detail": "Authentication service is temporarily unavailable.",
    }
    assert (
        "ai_knowledge_hub",
        logging.ERROR,
        "auth.redis.unavailable method=POST path=/auth/login error_type=RedisError",
    ) in caplog.record_tuples
    assert "user@example.com" not in caplog.text
    assert "password123" not in caplog.text
    assert "test Redis outage" not in caplog.text


def test_login_returns_service_unavailable_when_session_creation_fails(
    client: TestClient,
    session_repository: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    credentials = {
        "email": "user@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    session_repository.create.side_effect = RedisError("test Redis outage")

    with caplog.at_level(logging.ERROR, logger="ai_knowledge_hub"):
        response = client.post("/auth/login", json=credentials)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {
        "detail": "Authentication service is temporarily unavailable.",
    }
    assert (
        "ai_knowledge_hub",
        logging.ERROR,
        "auth.redis.unavailable method=POST path=/auth/login error_type=RedisError",
    ) in caplog.record_tuples
    assert credentials["email"] not in caplog.text
    assert credentials["password"] not in caplog.text
    assert "test Redis outage" not in caplog.text


def test_login_returns_unauthorized_for_wrong_password(
    client: TestClient,
) -> None:
    client.post(
        "/auth/register",
        json={
            "email": "user@example.com",
            "password": "password123",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "user@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "detail": "Invalid email or password.",
    }


def test_login_returns_forbidden_for_inactive_user(
    client: TestClient,
    session: Session,
) -> None:
    client.post(
        "/auth/register",
        json={
            "email": "user@example.com",
            "password": "password123",
        },
    )

    user = session.scalar(select(User).where(User.email == "user@example.com"))
    assert user is not None
    user.status = "disabled"
    session.commit()

    response = client.post(
        "/auth/login",
        json={
            "email": "user@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": "User account is inactive.",
    }


def test_login_returns_validation_error(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={
            "email": "invalid-email",
            "password": "",
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_refresh_returns_rotated_token_pair(
    client: TestClient,
    session_repository: Mock,
) -> None:
    credentials = {
        "email": "user@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)
    login_data = login_response.json()
    old_refresh_claims = decode_refresh_token(login_data["refresh_token"])
    session_record = session_repository.create.call_args.args[0]

    session_repository.reset_mock()
    session_repository.get.return_value = session_record
    session_repository.rotate.return_value = SessionRotationResult.SUCCESS

    response = client.post(
        "/auth/refresh",
        json={"refresh_token": login_data["refresh_token"]},
    )

    response_data = response.json()
    new_refresh_claims = decode_refresh_token(response_data["refresh_token"])

    assert response.status_code == status.HTTP_200_OK
    assert response_data["access_token"]
    assert response_data["refresh_token"] != login_data["refresh_token"]
    assert response_data["token_type"] == "bearer"
    assert response_data["expires_in"] <= settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert 0 < response_data["refresh_expires_in"] <= login_data["refresh_expires_in"]
    assert new_refresh_claims.session_id == old_refresh_claims.session_id
    assert new_refresh_claims.token_id != old_refresh_claims.token_id

    session_repository.get.assert_called_once_with(old_refresh_claims.session_id)
    session_repository.create.assert_not_called()
    session_repository.rotate.assert_called_once()


def test_refresh_returns_unauthorized_for_invalid_token(
    client: TestClient,
    session_repository: Mock,
) -> None:
    response = client.post(
        "/auth/refresh",
        json={"refresh_token": "not-a-valid-jwt"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "detail": "Invalid or expired refresh token.",
    }
    session_repository.get.assert_not_called()
    session_repository.rotate.assert_not_called()


def test_refresh_returns_forbidden_for_inactive_user(
    client: TestClient,
    session: Session,
    session_repository: Mock,
) -> None:
    credentials = {
        "email": "user@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)
    refresh_token = login_response.json()["refresh_token"]
    session_record = session_repository.create.call_args.args[0]

    user = session.scalar(select(User).where(User.email == "user@example.com"))
    assert user is not None
    user.status = "disabled"
    session.commit()

    session_repository.reset_mock()
    session_repository.get.return_value = session_record

    response = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": "User account is inactive.",
    }
    session_repository.rotate.assert_not_called()


def test_refresh_returns_service_unavailable_when_redis_is_down(
    client: TestClient,
    session_repository: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    credentials = {
        "email": "user@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)
    refresh_token = login_response.json()["refresh_token"]

    session_repository.reset_mock()
    session_repository.get.side_effect = RedisError("test Redis outage")

    with caplog.at_level(logging.ERROR, logger="ai_knowledge_hub"):
        response = client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {
        "detail": "Authentication service is temporarily unavailable.",
    }
    session_repository.rotate.assert_not_called()
    assert (
        "ai_knowledge_hub",
        logging.ERROR,
        "auth.redis.unavailable method=POST path=/auth/refresh error_type=RedisError",
    ) in caplog.record_tuples
    assert refresh_token not in caplog.text
    assert "test Redis outage" not in caplog.text


def test_logout_returns_no_content_and_deletes_current_session(
    client: TestClient,
    session_repository: Mock,
) -> None:
    credentials = {
        "email": "user@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)
    refresh_token = login_response.json()["refresh_token"]
    refresh_claims = decode_refresh_token(refresh_token)

    session_repository.reset_mock()
    session_repository.delete_if_matches.return_value = SessionDeletionResult.SUCCESS

    response = client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
    session_repository.delete_if_matches.assert_called_once_with(
        SessionDeletion(
            session_id=refresh_claims.session_id,
            user_id=refresh_claims.user_id,
            expected_refresh_token_hash=hash_refresh_token(refresh_token),
        )
    )
    session_repository.get.assert_not_called()
    session_repository.delete.assert_not_called()


def test_logout_returns_no_content_when_session_is_already_missing(
    client: TestClient,
    session_repository: Mock,
) -> None:
    credentials = {
        "email": "user@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)
    refresh_token = login_response.json()["refresh_token"]
    refresh_claims = decode_refresh_token(refresh_token)

    session_repository.reset_mock()
    session_repository.delete_if_matches.return_value = (
        SessionDeletionResult.SESSION_NOT_FOUND
    )

    response = client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
    session_repository.delete_if_matches.assert_called_once_with(
        SessionDeletion(
            session_id=refresh_claims.session_id,
            user_id=refresh_claims.user_id,
            expected_refresh_token_hash=hash_refresh_token(refresh_token),
        )
    )
    session_repository.get.assert_not_called()
    session_repository.delete.assert_not_called()


def test_logout_returns_unauthorized_for_invalid_token(
    client: TestClient,
    session_repository: Mock,
) -> None:
    response = client.post(
        "/auth/logout",
        json={"refresh_token": "not-a-valid-jwt"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "detail": "Invalid or expired refresh token.",
    }
    session_repository.delete_if_matches.assert_not_called()
    session_repository.get.assert_not_called()
    session_repository.delete.assert_not_called()


def test_logout_returns_unauthorized_for_session_mismatch(
    client: TestClient,
    session_repository: Mock,
) -> None:
    credentials = {
        "email": "user@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)
    refresh_token = login_response.json()["refresh_token"]

    session_repository.reset_mock()
    session_repository.delete_if_matches.return_value = (
        SessionDeletionResult.SESSION_MISMATCH
    )

    response = client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "detail": "Invalid or expired refresh token.",
    }


def test_logout_returns_service_unavailable_when_redis_is_down(
    client: TestClient,
    session_repository: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    credentials = {
        "email": "user@example.com",
        "password": "password123",
    }
    client.post("/auth/register", json=credentials)
    login_response = client.post("/auth/login", json=credentials)
    refresh_token = login_response.json()["refresh_token"]

    session_repository.reset_mock()
    session_repository.delete_if_matches.side_effect = RedisError("test Redis outage")

    with caplog.at_level(logging.ERROR, logger="ai_knowledge_hub"):
        response = client.post(
            "/auth/logout",
            json={"refresh_token": refresh_token},
        )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {
        "detail": "Authentication service is temporarily unavailable.",
    }
    session_repository.get.assert_not_called()
    session_repository.delete.assert_not_called()
    assert (
        "ai_knowledge_hub",
        logging.ERROR,
        "auth.redis.unavailable method=POST path=/auth/logout error_type=RedisError",
    ) in caplog.record_tuples
    assert refresh_token not in caplog.text
    assert "test Redis outage" not in caplog.text
