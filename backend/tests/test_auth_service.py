from time import time
from unittest.mock import Mock

import pytest
from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    LoginRateLimitExceededError,
)
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_refresh_token,
    verify_password,
)
from app.db.repositories.session_repository import (
    SessionRecord,
    SessionRotationResult,
)
from app.db.repositories.user_repository import UserRepository
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest
from app.services.auth_service import AuthService


def test_register_creates_committed_user(session: Session) -> None:
    service = AuthService(session)
    request = RegisterRequest(
        email="USER@example.com",
        password="password123",
        nickname="  Nickname  ",
    )

    response = service.register(request)

    assert str(response.email) == "user@example.com"
    assert response.nickname == "Nickname"
    assert response.status == "active"

    with Session(bind=session.get_bind()) as verification_session:
        saved_user = verification_session.scalar(
            select(User).where(User.email == "user@example.com")
        )

    assert saved_user is not None
    assert saved_user.password_hash != request.password
    assert verify_password(request.password, saved_user.password_hash) is True


def test_register_rejects_existing_email(session: Session) -> None:
    service = AuthService(session)
    first_request = RegisterRequest(
        email="user@example.com",
        password="password123",
    )
    duplicate_request = RegisterRequest(
        email="USER@example.com",
        password="different-password",
    )

    service.register(first_request)

    with pytest.raises(EmailAlreadyRegisteredError) as error:
        service.register(duplicate_request)

    user_count = session.scalar(select(func.count()).select_from(User))

    assert error.value.__cause__ is None
    assert user_count == 1


def test_register_translates_unique_constraint_error(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AuthService(session)

    first_request = RegisterRequest(
        email="user@example.com",
        password="password123",
    )
    duplicate_request = RegisterRequest(
        email="user@example.com",
        password="different-password",
    )

    service.register(first_request)

    monkeypatch.setattr(
        UserRepository,
        "get_by_email",
        lambda _repository, _email: None,
    )

    with pytest.raises(EmailAlreadyRegisteredError) as error:
        service.register(duplicate_request)

    user_count = session.scalar(select(func.count()).select_from(User))

    assert isinstance(error.value.__cause__, IntegrityError)
    assert user_count == 1


def test_login_returns_token_pair_and_creates_session(
    session: Session,
    login_rate_limiter: Mock,
    session_repository: Mock,
) -> None:
    service = AuthService(session)
    user = service.register(
        RegisterRequest(
            email="USER@example.com",
            password="password123",
        )
    )

    response = service.login(
        LoginRequest(
            email="user@example.com",
            password="password123",
        ),
        login_rate_limiter,
        session_repository,
    )

    payload = jwt.decode(
        response.access_token,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )

    refresh_claims = decode_refresh_token(response.refresh_token)

    session_repository.create.assert_called_once()
    create_call = session_repository.create.call_args
    session_record = create_call.args[0]
    ttl_seconds = create_call.kwargs["ttl_seconds"]

    assert response.token_type == "bearer"
    assert response.expires_in == (settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    assert payload["sub"] == str(user.id)
    assert payload["type"] == "access"
    login_rate_limiter.reset.assert_called_once_with("user@example.com")
    assert response.refresh_expires_in == ttl_seconds

    assert refresh_claims.user_id == user.id
    assert refresh_claims.session_id == session_record.session_id
    assert refresh_claims.expires_at == session_record.expires_at

    assert session_record.user_id == user.id
    assert session_record.refresh_token_hash == hash_refresh_token(
        response.refresh_token
    )
    assert session_record.created_at == session_record.last_used_at
    assert session_record.absolute_expires_at >= session_record.expires_at

    assert ttl_seconds == (settings.SESSION_TTL_DAYS * 86_400)
    assert payload["exp"] <= refresh_claims.expires_at


def test_login_rejects_unknown_email(
    session: Session,
    login_rate_limiter: Mock,
    session_repository: Mock,
) -> None:
    service = AuthService(session)

    with pytest.raises(InvalidCredentialsError):
        service.login(
            LoginRequest(
                email="unknown@example.com",
                password="a",
            ),
            login_rate_limiter,
            session_repository,
        )

    login_rate_limiter.record_failure.assert_called_once_with("unknown@example.com")


def test_login_rejects_rate_limited_identifier(
    session: Session,
    login_rate_limiter: Mock,
    session_repository: Mock,
) -> None:
    login_rate_limiter.is_limited.return_value = True
    service = AuthService(session)

    with pytest.raises(LoginRateLimitExceededError):
        service.login(
            LoginRequest(
                email="USER@example.com",
                password="password123",
            ),
            login_rate_limiter,
            session_repository,
        )

    login_rate_limiter.is_limited.assert_called_once_with("user@example.com")
    login_rate_limiter.record_failure.assert_not_called()
    login_rate_limiter.reset.assert_not_called()


def test_login_checks_password_for_unknown_email(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    login_rate_limiter: Mock,
    session_repository: Mock,
) -> None:
    service = AuthService(session)
    verified_hashes: list[str] = []

    def track_password_check(_password: str, password_hash: str) -> bool:
        verified_hashes.append(password_hash)
        return False

    monkeypatch.setattr(
        "app.services.auth_service.verify_password",
        track_password_check,
    )

    with pytest.raises(InvalidCredentialsError):
        service.login(
            LoginRequest(
                email="unknown@example.com",
                password="password123",
            ),
            login_rate_limiter,
            session_repository,
        )

    assert verified_hashes == [DUMMY_PASSWORD_HASH]


def test_login_rejects_wrong_password(
    session: Session,
    login_rate_limiter: Mock,
    session_repository: Mock,
) -> None:
    service = AuthService(session)

    service.register(
        RegisterRequest(
            email="USER@example.com",
            password="password123",
        )
    )

    with pytest.raises(InvalidCredentialsError):
        service.login(
            LoginRequest(
                email="USER@example.com",
                password="wrong-password",
            ),
            login_rate_limiter,
            session_repository,
        )

    login_rate_limiter.record_failure.assert_called_once_with("user@example.com")


def test_login_rejects_inactive_user(
    session: Session,
    login_rate_limiter: Mock,
    session_repository: Mock,
) -> None:
    service = AuthService(session)

    user = service.register(
        RegisterRequest(
            email="USER@example.com",
            password="password123",
        )
    )

    user_model = session.get(User, user.id)
    assert user_model is not None
    user_model.status = "disabled"
    session.commit()

    with pytest.raises(InactiveUserError):
        service.login(
            LoginRequest(
                email="USER@example.com",
                password="password123",
            ),
            login_rate_limiter,
            session_repository,
        )


def test_get_current_user_returns_token_user(session: Session) -> None:
    service = AuthService(session)

    registered_user = service.register(
        RegisterRequest(
            email="user@example.com",
            password="password123",
        )
    )

    token = create_access_token(registered_user.id)

    current_user = service.get_current_user(token)

    assert current_user.id == registered_user.id
    assert str(current_user.email) == "user@example.com"
    assert current_user.status == "active"


def test_get_current_user_rejects_missing_user(session: Session) -> None:
    service = AuthService(session)
    token = create_access_token(user_id=999)

    with pytest.raises(InvalidAccessTokenError):
        service.get_current_user(token)


def test_get_current_user_rejects_inactive_user(
    session: Session,
) -> None:
    service = AuthService(session)
    registered_user = service.register(
        RegisterRequest(
            email="user@example.com",
            password="password123",
        )
    )

    user_model = session.get(User, registered_user.id)
    assert user_model is not None
    user_model.status = "disabled"
    session.commit()

    token = create_access_token(registered_user.id)

    with pytest.raises(InactiveUserError):
        service.get_current_user(token)


def test_refresh_returns_rotated_token_pair(
    session: Session,
    session_repository: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AuthService(session)
    user = service.register(
        RegisterRequest(
            email="user@example.com",
            password="password123",
        )
    )
    rotated_at = int(time())
    session_expires_at = rotated_at + 3_600
    session_id = "test-session-id"
    old_refresh_token = create_refresh_token(
        user_id=user.id,
        session_id=session_id,
        expires_at=session_expires_at,
    )
    old_refresh_claims = decode_refresh_token(old_refresh_token)

    # Redis Mock 表示当前 Session 存在，并且 Lua 原子 Rotation 成功。
    session_repository.get.return_value = SessionRecord(
        session_id=session_id,
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(old_refresh_token),
        created_at=rotated_at - 600,
        last_used_at=rotated_at - 60,
        expires_at=session_expires_at,
        absolute_expires_at=session_expires_at,
    )
    session_repository.rotate.return_value = SessionRotationResult.SUCCESS
    monkeypatch.setattr(settings, "SESSION_EXPIRATION_MODE", "absolute")
    monkeypatch.setattr("app.services.auth_service.time", lambda: rotated_at)

    response = service.refresh(
        RefreshRequest(refresh_token=old_refresh_token),
        session_repository,
    )

    new_refresh_claims = decode_refresh_token(response.refresh_token)
    access_payload = jwt.decode(
        response.access_token,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )
    rotation = session_repository.rotate.call_args.args[0]

    assert response.refresh_token != old_refresh_token
    assert response.token_type == "bearer"
    assert response.expires_in == settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert response.refresh_expires_in == 3_600

    assert new_refresh_claims.user_id == user.id
    assert new_refresh_claims.session_id == session_id
    assert new_refresh_claims.token_id != old_refresh_claims.token_id
    assert new_refresh_claims.expires_at == session_expires_at
    assert access_payload["sub"] == str(user.id)
    assert access_payload["type"] == "access"
    assert access_payload["exp"] <= session_expires_at

    session_repository.get.assert_called_once_with(session_id)
    session_repository.create.assert_not_called()
    session_repository.rotate.assert_called_once()
    assert rotation.session_id == session_id
    assert rotation.user_id == user.id
    assert rotation.expected_refresh_token_hash == hash_refresh_token(old_refresh_token)
    assert rotation.new_refresh_token_hash == hash_refresh_token(response.refresh_token)
    assert rotation.rotated_at == rotated_at
    assert rotation.expires_at == session_expires_at
    assert rotation.ttl_seconds == 3_600


@pytest.mark.parametrize(
    "rotation_result",
    [
        SessionRotationResult.SESSION_NOT_FOUND,
        SessionRotationResult.TOKEN_MISMATCH,
    ],
)
def test_refresh_rejects_failed_rotation(
    rotation_result: SessionRotationResult,
    session: Session,
    session_repository: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AuthService(session)
    user = service.register(
        RegisterRequest(
            email="user@example.com",
            password="password123",
        )
    )
    rotated_at = int(time())
    session_expires_at = rotated_at + 3_600
    session_id = "test-session-id"
    old_refresh_token = create_refresh_token(
        user_id=user.id,
        session_id=session_id,
        expires_at=session_expires_at,
    )
    session_repository.get.return_value = SessionRecord(
        session_id=session_id,
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(old_refresh_token),
        created_at=rotated_at - 600,
        last_used_at=rotated_at - 60,
        expires_at=session_expires_at,
        absolute_expires_at=session_expires_at,
    )
    session_repository.rotate.return_value = rotation_result
    monkeypatch.setattr(settings, "SESSION_EXPIRATION_MODE", "absolute")
    monkeypatch.setattr("app.services.auth_service.time", lambda: rotated_at)

    with pytest.raises(InvalidRefreshTokenError):
        service.refresh(
            RefreshRequest(refresh_token=old_refresh_token),
            session_repository,
        )

    session_repository.get.assert_called_once_with(session_id)
    session_repository.create.assert_not_called()
    session_repository.rotate.assert_called_once()


def test_refresh_rejects_missing_session_before_rotation(
    session: Session,
    session_repository: Mock,
) -> None:
    service = AuthService(session)
    user = service.register(
        RegisterRequest(
            email="user@example.com",
            password="password123",
        )
    )
    session_id = "missing-session-id"
    refresh_token = create_refresh_token(
        user_id=user.id,
        session_id=session_id,
        expires_at=int(time()) + 3_600,
    )
    session_repository.get.return_value = None

    with pytest.raises(InvalidRefreshTokenError):
        service.refresh(
            RefreshRequest(refresh_token=refresh_token),
            session_repository,
        )

    session_repository.get.assert_called_once_with(session_id)
    session_repository.create.assert_not_called()
    session_repository.rotate.assert_not_called()
