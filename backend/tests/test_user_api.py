import logging

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
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
    token = create_access_token(user_id=999)

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
