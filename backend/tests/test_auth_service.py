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
)
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    verify_password,
)
from app.db.repositories.user_repository import UserRepository
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest
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


def test_login_returns_access_token_for_valid_credentials(
    session: Session,
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
        )
    )

    payload = jwt.decode(
        response.access_token,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert response.token_type == "bearer"
    assert response.expires_in == (settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    assert payload["sub"] == str(user.id)
    assert payload["type"] == "access"


def test_login_rejects_unknown_email(session: Session) -> None:
    service = AuthService(session)

    with pytest.raises(InvalidCredentialsError):
        service.login(
            LoginRequest(
                email="unknown@example.com",
                password="a",
            )
        )


def test_login_checks_password_for_unknown_email(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
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
            )
        )

    assert verified_hashes == [DUMMY_PASSWORD_HASH]


def test_login_rejects_wrong_password(session: Session) -> None:
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
            )
        )


def test_login_rejects_inactive_user(session: Session) -> None:
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
            )
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
