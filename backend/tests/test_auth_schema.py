import pytest
from pydantic import ValidationError

from app.core.security import BCRYPT_PASSWORD_MAX_BYTES
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse


def test_register_request_accepts_valid_data() -> None:
    request = RegisterRequest(
        email="user@example.com",
        password="securepassword",
    )

    assert str(request.email) == "user@example.com"
    assert request.password == "securepassword"
    assert request.nickname is None


def test_register_request_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError) as error:
        RegisterRequest(
            email="invalid-email",
            password="securepassword",
        )

    assert error.value.errors()[0]["loc"] == ("email",)


def test_register_request_rejects_short_password() -> None:
    with pytest.raises(ValidationError) as error:
        RegisterRequest(
            email="user@example.com",
            password="short",
        )

    assert error.value.errors()[0]["loc"] == ("password",)


def test_register_request_rejects_password_over_bcrypt_byte_limit() -> None:
    multibyte_password = "\u5bc6" * 25

    with pytest.raises(ValidationError) as error:
        RegisterRequest(
            email="user@example.com",
            password=multibyte_password,
        )

    assert error.value.errors()[0]["loc"] == ("password",)


def test_login_request_accepts_existing_short_password() -> None:
    request = LoginRequest(
        email="user@example.com",
        password="a",
    )

    assert str(request.email) == "user@example.com"
    assert request.password == "a"


def test_login_request_rejects_empty_password() -> None:
    with pytest.raises(ValidationError) as error:
        LoginRequest(
            email="user@example.com",
            password="",
        )

    assert error.value.errors()[0]["loc"] == ("password",)


def test_login_request_rejects_password_over_bcrypt_byte_limit() -> None:
    with pytest.raises(ValidationError) as error:
        LoginRequest(
            email="user@example.com",
            password="a" * (BCRYPT_PASSWORD_MAX_BYTES + 1),
        )

    assert error.value.errors()[0]["loc"] == ("password",)


def test_token_response_uses_bearer_token_type() -> None:
    response = TokenResponse(
        access_token="signed-token",
        expires_in=1800,
    )

    assert response.access_token == "signed-token"
    assert response.token_type == "bearer"
    assert response.expires_in == 1800
