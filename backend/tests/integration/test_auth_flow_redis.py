from collections.abc import Generator
from os import getenv
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_login_rate_limiter,
    get_session_repository,
)
from app.core.config import settings
from app.core.security import decode_refresh_token
from app.db.redis_client import create_redis_client
from app.db.repositories.session_repository import SessionRepository
from app.db.session import get_db
from app.main import app
from app.services.login_rate_limiter import LoginRateLimiter

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        getenv("RUN_REDIS_INTEGRATION_TESTS") != "1",
        reason="Set RUN_REDIS_INTEGRATION_TESTS=1 to run real Redis tests.",
    ),
]

RealRedisAuthContext = tuple[
    TestClient,
    SessionRepository,
    LoginRateLimiter,
]


@pytest.fixture
def real_redis_auth_context(
    session: Session,
) -> Generator[RealRedisAuthContext, None, None]:
    redis_client = create_redis_client()
    session_repository = SessionRepository(redis_client)
    rate_limiter = LoginRateLimiter(
        redis_client,
        window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        max_attempts=settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    )

    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_repository] = lambda: session_repository
    app.dependency_overrides[get_login_rate_limiter] = lambda: rate_limiter

    try:
        with TestClient(app) as test_client:
            yield test_client, session_repository, rate_limiter
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_session_repository, None)
        app.dependency_overrides.pop(get_login_rate_limiter, None)
        redis_client.close()


def test_auth_lifecycle_uses_real_redis(
    real_redis_auth_context: RealRedisAuthContext,
) -> None:
    test_client, session_repository, rate_limiter = real_redis_auth_context
    email = f"auth-flow-{uuid4().hex}@example.com"
    user_id: int | None = None
    session_id: str | None = None

    try:
        register_response = test_client.post(
            "/auth/register",
            json={
                "email": email,
                "password": "password123",
            },
        )

        assert register_response.status_code == status.HTTP_201_CREATED
        user_id = register_response.json()["id"]

        login_response = test_client.post(
            "/auth/login",
            json={
                "email": email,
                "password": "password123",
            },
        )

        assert login_response.status_code == status.HTTP_200_OK

        token_pair = login_response.json()
        access_token = token_pair["access_token"]
        refresh_token = token_pair["refresh_token"]

        refresh_claims = decode_refresh_token(refresh_token)
        session_id = refresh_claims.session_id
        stored_session = session_repository.get(session_id)

        assert stored_session is not None
        assert stored_session.user_id == user_id

        current_user_response = test_client.get(
            "/users/me",
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )

        assert current_user_response.status_code == status.HTTP_200_OK
        assert current_user_response.json()["email"] == email

        refresh_response = test_client.post(
            "/auth/refresh",
            json={
                "refresh_token": refresh_token,
            },
        )

        assert refresh_response.status_code == status.HTTP_200_OK

        rotated_token_pair = refresh_response.json()
        new_access_token = rotated_token_pair["access_token"]
        new_refresh_token = rotated_token_pair["refresh_token"]
        rotated_claims = decode_refresh_token(new_refresh_token)

        assert new_refresh_token != refresh_token
        assert rotated_claims.session_id == session_id
        assert session_repository.get(session_id) is not None

        logout_response = test_client.post(
            "/auth/logout",
            json={
                "refresh_token": new_refresh_token,
            },
        )

        assert logout_response.status_code == status.HTTP_204_NO_CONTENT
        assert session_repository.get(session_id) is None

        access_after_logout_response = test_client.get(
            "/users/me",
            headers={
                "Authorization": f"Bearer {new_access_token}",
            },
        )

        assert access_after_logout_response.status_code == status.HTTP_200_OK

        refresh_after_logout_response = test_client.post(
            "/auth/refresh",
            json={
                "refresh_token": new_refresh_token,
            },
        )

        assert refresh_after_logout_response.status_code == status.HTTP_401_UNAUTHORIZED

    finally:
        if user_id is not None and session_id is not None:
            session_repository.delete(user_id, session_id)

        rate_limiter.reset(email)


def test_refresh_replay_revokes_real_redis_session(
    real_redis_auth_context: RealRedisAuthContext,
) -> None:
    test_client, session_repository, rate_limiter = real_redis_auth_context
    email = f"replay-flow-{uuid4().hex}@example.com"
    user_id: int | None = None
    session_id: str | None = None

    try:
        register_response = test_client.post(
            "/auth/register",
            json={
                "email": email,
                "password": "password123",
            },
        )

        assert register_response.status_code == status.HTTP_201_CREATED
        user_id = register_response.json()["id"]

        login_response = test_client.post(
            "/auth/login",
            json={
                "email": email,
                "password": "password123",
            },
        )

        assert login_response.status_code == status.HTTP_200_OK

        first_refresh_token = login_response.json()["refresh_token"]
        first_claims = decode_refresh_token(first_refresh_token)
        session_id = first_claims.session_id

        rotation_response = test_client.post(
            "/auth/refresh",
            json={
                "refresh_token": first_refresh_token,
            },
        )

        assert rotation_response.status_code == status.HTTP_200_OK

        second_refresh_token = rotation_response.json()["refresh_token"]

        replay_response = test_client.post(
            "/auth/refresh",
            json={
                "refresh_token": first_refresh_token,
            },
        )

        assert replay_response.status_code == status.HTTP_401_UNAUTHORIZED
        assert session_repository.get(session_id) is None

        current_token_response = test_client.post(
            "/auth/refresh",
            json={
                "refresh_token": second_refresh_token,
            },
        )

        assert current_token_response.status_code == status.HTTP_401_UNAUTHORIZED
    finally:
        if user_id is not None and session_id is not None:
            session_repository.delete(user_id, session_id)

        rate_limiter.reset(email)
