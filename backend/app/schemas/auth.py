from typing import Literal

from pydantic import BaseModel, EmailStr, Field, PositiveInt, field_validator

from app.core.security import BCRYPT_PASSWORD_MAX_BYTES


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    nickname: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="Optional nickname for the user, up to 50 characters.",
    )

    @field_validator("password")
    @classmethod
    def validate_password_byte_length(cls, password: str) -> str:
        if len(password.encode("utf-8")) > BCRYPT_PASSWORD_MAX_BYTES:
            raise ValueError(
                f"Password cannot exceed {BCRYPT_PASSWORD_MAX_BYTES} UTF-8 bytes."
            )

        return password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

    @field_validator("password")
    @classmethod
    def validate_password_byte_length(cls, password: str) -> str:
        if len(password.encode("utf-8")) > BCRYPT_PASSWORD_MAX_BYTES:
            raise ValueError(
                f"Password cannot exceed {BCRYPT_PASSWORD_MAX_BYTES} UTF-8 bytes."
            )

        return password


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: PositiveInt
