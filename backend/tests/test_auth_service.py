import logging
from time import time
from unittest.mock import Mock

import pytest
from jose import jwt
from pydantic import SecretStr
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
    SessionDeletion,
    SessionDeletionResult,
    SessionRecord,
    SessionRotationResult,
)
from app.db.repositories.user_repository import UserRepository
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
)
from app.services.auth_service import AuthService


def test_register_creates_committed_user(
    session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AuthService(session)
    request = RegisterRequest(
        email="USER@example.com",
        password="password123",
        nickname="  Nickname  ",
    )

    with caplog.at_level(logging.INFO, logger="ai_knowledge_hub"):
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
    assert (
        "ai_knowledge_hub",
        logging.INFO,
        f"auth.register.success user_id={response.id}",
    ) in caplog.record_tuples
    assert str(request.email) not in caplog.text
    assert request.password not in caplog.text
    assert request.nickname not in caplog.text
    assert response.nickname not in caplog.text
    assert saved_user.password_hash not in caplog.text


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
        settings.JWT_SIGNING_KEYS[settings.JWT_ACTIVE_KEY_ID].get_secret_value(),
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


def test_login_logs_success_without_sensitive_data(
    session: Session,
    login_rate_limiter: Mock,
    session_repository: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AuthService(session)
    user = service.register(
        RegisterRequest(
            email="user@example.com",
            password="password123",
        )
    )
    request = LoginRequest(
        email="user@example.com",
        password="password123",
    )

    with caplog.at_level(logging.INFO, logger="ai_knowledge_hub"):
        response = service.login(
            request,
            login_rate_limiter,
            session_repository,
        )

    session_record = session_repository.create.call_args.args[0]

    assert f"auth.login.success user_id={user.id}" in caplog.messages
    assert str(request.email) not in caplog.text
    assert request.password not in caplog.text
    assert response.access_token not in caplog.text
    assert response.refresh_token not in caplog.text
    assert session_record.session_id not in caplog.text
    assert session_record.refresh_token_hash not in caplog.text


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

    login_rate_limiter.reserve_attempt.assert_called_once_with("unknown@example.com")
    login_rate_limiter.reset.assert_not_called()


def test_login_rejects_rate_limited_identifier(
    session: Session,
    login_rate_limiter: Mock,
    session_repository: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    login_rate_limiter.reserve_attempt.return_value = False
    service = AuthService(session)

    with caplog.at_level(logging.WARNING, logger="ai_knowledge_hub"):
        with pytest.raises(LoginRateLimitExceededError):
            service.login(
                LoginRequest(
                    email="USER@example.com",
                    password="password123",
                ),
                login_rate_limiter,
                session_repository,
            )

    login_rate_limiter.reserve_attempt.assert_called_once_with("user@example.com")
    login_rate_limiter.reset.assert_not_called()
    assert (
        "ai_knowledge_hub",
        logging.WARNING,
        "auth.login.rate_limited reason=attempt_limit_exceeded",
    ) in caplog.record_tuples
    assert "USER@example.com" not in caplog.text
    assert "user@example.com" not in caplog.text
    assert "password123" not in caplog.text


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

    login_rate_limiter.reserve_attempt.assert_called_once_with("user@example.com")
    login_rate_limiter.reset.assert_not_called()


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
    caplog: pytest.LogCaptureFixture,
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

    first_secret = "first-test-signing-key-at-least-32-characters"
    second_secret = "second-test-signing-key-at-least-32-characters"

    monkeypatch.setattr(
        settings,
        "JWT_SIGNING_KEYS",
        {
            "v1": SecretStr(first_secret),
            "v2": SecretStr(second_secret),
        },
    )
    monkeypatch.setattr(settings, "JWT_ACTIVE_KEY_ID", "v1")

    old_refresh_token = create_refresh_token(
        user_id=user.id,
        session_id=session_id,
        expires_at=session_expires_at,
    )

    old_refresh_header = jwt.get_unverified_header(old_refresh_token)

    monkeypatch.setattr(settings, "JWT_ACTIVE_KEY_ID", "v2")
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

    with caplog.at_level(logging.INFO, logger="ai_knowledge_hub"):
        response = service.refresh(
            RefreshRequest(refresh_token=old_refresh_token),
            session_repository,
        )

    new_refresh_header = jwt.get_unverified_header(response.refresh_token)
    new_access_header = jwt.get_unverified_header(response.access_token)
    new_refresh_claims = decode_refresh_token(response.refresh_token)
    access_payload = jwt.decode(
        response.access_token,
        second_secret,
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

    assert old_refresh_header["kid"] == "v1"
    assert new_refresh_header["kid"] == "v2"
    assert new_access_header["kid"] == "v2"
    assert (
        "ai_knowledge_hub",
        logging.INFO,
        f"auth.refresh.success user_id={user.id}",
    ) in caplog.record_tuples
    assert "user@example.com" not in caplog.text
    assert old_refresh_token not in caplog.text
    assert response.refresh_token not in caplog.text
    assert response.access_token not in caplog.text
    assert session_id not in caplog.text
    assert rotation.expected_refresh_token_hash not in caplog.text
    assert rotation.new_refresh_token_hash not in caplog.text


@pytest.mark.parametrize(
    ("rotation_result", "expected_event", "expected_reason"),
    [
        (
            SessionRotationResult.SESSION_NOT_FOUND,
            "auth.refresh.rejected",
            "session_not_found",
        ),
        (
            SessionRotationResult.TOKEN_MISMATCH,
            "auth.refresh.replay_detected",
            "token_mismatch",
        ),
    ],
)
def test_refresh_rejects_failed_rotation(
    rotation_result: SessionRotationResult,
    expected_event: str,
    expected_reason: str,
    session: Session,
    session_repository: Mock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
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

    with caplog.at_level(logging.WARNING, logger="ai_knowledge_hub"):
        with pytest.raises(InvalidRefreshTokenError):
            service.refresh(
                RefreshRequest(refresh_token=old_refresh_token),
                session_repository,
            )

    session_repository.get.assert_called_once_with(session_id)
    session_repository.create.assert_not_called()
    session_repository.rotate.assert_called_once()
    assert (
        "ai_knowledge_hub",
        logging.WARNING,
        f"{expected_event} user_id={user.id} reason={expected_reason}",
    ) in caplog.record_tuples
    assert "user@example.com" not in caplog.text
    assert old_refresh_token not in caplog.text
    assert session_id not in caplog.text
    assert hash_refresh_token(old_refresh_token) not in caplog.text


def test_refresh_rejects_missing_session_before_rotation(
    session: Session,
    session_repository: Mock,
    caplog: pytest.LogCaptureFixture,
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

    with caplog.at_level(logging.WARNING, logger="ai_knowledge_hub"):
        with pytest.raises(InvalidRefreshTokenError):
            service.refresh(
                RefreshRequest(refresh_token=refresh_token),
                session_repository,
            )

    session_repository.get.assert_called_once_with(session_id)
    session_repository.create.assert_not_called()
    session_repository.rotate.assert_not_called()
    assert (
        "ai_knowledge_hub",
        logging.WARNING,
        f"auth.refresh.rejected user_id={user.id} reason=session_not_found",
    ) in caplog.record_tuples
    assert "user@example.com" not in caplog.text
    assert refresh_token not in caplog.text
    assert session_id not in caplog.text
    assert hash_refresh_token(refresh_token) not in caplog.text


def test_refresh_rejects_session_user_mismatch_without_rotation(
    session: Session,
    session_repository: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AuthService(session)
    user = service.register(
        RegisterRequest(
            email="user@example.com",
            password="password123",
        )
    )
    session_id = "mismatched-user-session-id"
    expires_at = int(time()) + 3_600
    refresh_token = create_refresh_token(
        user_id=user.id,
        session_id=session_id,
        expires_at=expires_at,
    )
    session_repository.get.return_value = SessionRecord(
        session_id=session_id,
        user_id=user.id + 1,
        refresh_token_hash=hash_refresh_token(refresh_token),
        created_at=expires_at - 600,
        last_used_at=expires_at - 60,
        expires_at=expires_at,
        absolute_expires_at=expires_at,
    )

    with caplog.at_level(logging.WARNING, logger="ai_knowledge_hub"):
        with pytest.raises(InvalidRefreshTokenError):
            service.refresh(
                RefreshRequest(refresh_token=refresh_token),
                session_repository,
            )

    session_repository.rotate.assert_not_called()
    assert (
        "ai_knowledge_hub",
        logging.WARNING,
        f"auth.refresh.rejected user_id={user.id} reason=user_mismatch",
    ) in caplog.record_tuples
    assert refresh_token not in caplog.text
    assert session_id not in caplog.text
    assert hash_refresh_token(refresh_token) not in caplog.text


def test_refresh_rejects_missing_user_without_rotation(
    session: Session,
    session_repository: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AuthService(session)
    user_id = 999
    session_id = "missing-user-session-id"
    expires_at = int(time()) + 3_600
    refresh_token = create_refresh_token(
        user_id=user_id,
        session_id=session_id,
        expires_at=expires_at,
    )
    session_repository.get.return_value = SessionRecord(
        session_id=session_id,
        user_id=user_id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        created_at=expires_at - 600,
        last_used_at=expires_at - 60,
        expires_at=expires_at,
        absolute_expires_at=expires_at,
    )

    with caplog.at_level(logging.WARNING, logger="ai_knowledge_hub"):
        with pytest.raises(InvalidRefreshTokenError):
            service.refresh(
                RefreshRequest(refresh_token=refresh_token),
                session_repository,
            )

    session_repository.rotate.assert_not_called()
    assert (
        "ai_knowledge_hub",
        logging.WARNING,
        f"auth.refresh.rejected user_id={user_id} reason=user_not_found",
    ) in caplog.record_tuples
    assert refresh_token not in caplog.text
    assert session_id not in caplog.text
    assert hash_refresh_token(refresh_token) not in caplog.text


def test_refresh_rejects_expired_session_without_rotation(
    session: Session,
    session_repository: Mock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AuthService(session)
    user = service.register(
        RegisterRequest(
            email="user@example.com",
            password="password123",
        )
    )
    now = int(time())
    expires_at = now + 3_600
    session_id = "expired-session-id"
    refresh_token = create_refresh_token(
        user_id=user.id,
        session_id=session_id,
        expires_at=expires_at,
    )
    session_repository.get.return_value = SessionRecord(
        session_id=session_id,
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        created_at=now - 600,
        last_used_at=now - 60,
        expires_at=expires_at,
        absolute_expires_at=expires_at,
    )
    monkeypatch.setattr(settings, "SESSION_EXPIRATION_MODE", "absolute")
    monkeypatch.setattr("app.services.auth_service.time", lambda: expires_at)

    with caplog.at_level(logging.WARNING, logger="ai_knowledge_hub"):
        with pytest.raises(InvalidRefreshTokenError):
            service.refresh(
                RefreshRequest(refresh_token=refresh_token),
                session_repository,
            )

    session_repository.rotate.assert_not_called()
    assert (
        "ai_knowledge_hub",
        logging.WARNING,
        f"auth.refresh.rejected user_id={user.id} reason=session_expired",
    ) in caplog.record_tuples
    assert "user@example.com" not in caplog.text
    assert refresh_token not in caplog.text
    assert session_id not in caplog.text
    assert hash_refresh_token(refresh_token) not in caplog.text


def test_logout_deletes_current_session(
    session: Session,
    session_repository: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AuthService(session)
    user_id = 42
    session_id = "current-session-id"
    refresh_token = create_refresh_token(
        user_id=user_id,
        session_id=session_id,
        expires_at=int(time()) + 3_600,
    )
    session_repository.delete_if_matches.return_value = SessionDeletionResult.SUCCESS

    with caplog.at_level(logging.INFO, logger="ai_knowledge_hub"):
        result = service.logout(
            LogoutRequest(refresh_token=refresh_token),
            session_repository,
        )

    assert result is None
    session_repository.delete_if_matches.assert_called_once_with(
        SessionDeletion(
            session_id=session_id,
            user_id=user_id,
            expected_refresh_token_hash=hash_refresh_token(refresh_token),
        )
    )
    session_repository.get.assert_not_called()
    session_repository.delete.assert_not_called()
    session_repository.create.assert_not_called()
    session_repository.rotate.assert_not_called()
    assert (
        "ai_knowledge_hub",
        logging.INFO,
        f"auth.logout.success user_id={user_id} result=deleted",
    ) in caplog.record_tuples
    assert refresh_token not in caplog.text
    assert session_id not in caplog.text
    assert hash_refresh_token(refresh_token) not in caplog.text


def test_logout_succeeds_when_session_is_already_missing(
    session: Session,
    session_repository: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AuthService(session)
    session_id = "missing-session-id"
    refresh_token = create_refresh_token(
        user_id=42,
        session_id=session_id,
        expires_at=int(time()) + 3_600,
    )
    session_repository.delete_if_matches.return_value = (
        SessionDeletionResult.SESSION_NOT_FOUND
    )

    with caplog.at_level(logging.INFO, logger="ai_knowledge_hub"):
        result = service.logout(
            LogoutRequest(refresh_token=refresh_token),
            session_repository,
        )

    assert result is None
    session_repository.delete_if_matches.assert_called_once_with(
        SessionDeletion(
            session_id=session_id,
            user_id=42,
            expected_refresh_token_hash=hash_refresh_token(refresh_token),
        )
    )
    session_repository.get.assert_not_called()
    session_repository.delete.assert_not_called()
    assert (
        "ai_knowledge_hub",
        logging.INFO,
        "auth.logout.success user_id=42 result=already_missing",
    ) in caplog.record_tuples
    assert refresh_token not in caplog.text
    assert session_id not in caplog.text
    assert hash_refresh_token(refresh_token) not in caplog.text


def test_logout_rejects_session_mismatch(
    session: Session,
    session_repository: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = AuthService(session)
    user_id = 42
    session_id = "current-session-id"
    refresh_token = create_refresh_token(
        user_id=user_id,
        session_id=session_id,
        expires_at=int(time()) + 3_600,
    )
    session_repository.delete_if_matches.return_value = (
        SessionDeletionResult.SESSION_MISMATCH
    )

    with caplog.at_level(logging.INFO, logger="ai_knowledge_hub"):
        with pytest.raises(InvalidRefreshTokenError):
            service.logout(
                LogoutRequest(refresh_token=refresh_token),
                session_repository,
            )

    session_repository.delete_if_matches.assert_called_once_with(
        SessionDeletion(
            session_id=session_id,
            user_id=user_id,
            expected_refresh_token_hash=hash_refresh_token(refresh_token),
        )
    )
    session_repository.get.assert_not_called()
    session_repository.delete.assert_not_called()
    assert "auth.logout.success" not in caplog.text


def test_refresh_extends_expiration_in_sliding_mode(
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
    current_expires_at = rotated_at + 3_600
    absolute_expires_at = rotated_at + 30 * 86_400
    expected_expires_at = rotated_at + 7 * 86_400
    session_id = "sliding-session-id"

    old_refresh_token = create_refresh_token(
        user_id=user.id,
        session_id=session_id,
        expires_at=current_expires_at,
    )

    session_repository.get.return_value = SessionRecord(
        session_id=session_id,
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(old_refresh_token),
        created_at=rotated_at - 86_400,
        last_used_at=rotated_at - 86_400,
        expires_at=current_expires_at,
        absolute_expires_at=absolute_expires_at,
    )
    session_repository.rotate.return_value = SessionRotationResult.SUCCESS

    monkeypatch.setattr(settings, "SESSION_EXPIRATION_MODE", "sliding")
    monkeypatch.setattr(settings, "SESSION_TTL_DAYS", 7)
    monkeypatch.setattr("app.services.auth_service.time", lambda: rotated_at)

    response = service.refresh(
        RefreshRequest(refresh_token=old_refresh_token),
        session_repository,
    )

    new_refresh_claims = decode_refresh_token(response.refresh_token)
    rotation = session_repository.rotate.call_args.args[0]

    assert rotation.expires_at == expected_expires_at
    assert rotation.ttl_seconds == 7 * 86_400
    assert response.refresh_expires_in == 7 * 86_400
    assert new_refresh_claims.expires_at == expected_expires_at
