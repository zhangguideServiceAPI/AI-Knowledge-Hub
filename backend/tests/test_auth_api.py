from fastapi import status
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
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


def test_login_return_access_token(client: TestClient) -> None:
    credentials = {
        "email": "user@example.com",
        "password": "password123",
    }

    client.post("/auth/register", json=credentials)

    response = client.post("/auth/login", json=credentials)
    response_data = response.json()
    payload = jwt.decode(
        response_data["access_token"],
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert response.status_code == status.HTTP_200_OK
    assert response_data["token_type"] == "bearer"
    assert response_data["expires_in"] == (
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    assert payload["type"] == "access"


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
