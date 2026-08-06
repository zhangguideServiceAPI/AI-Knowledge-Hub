from typing import Annotated, Literal, Self

from pydantic import Field, PositiveFloat, PositiveInt, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

JwtKeyId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    ),
]

JwtSigningSecret = Annotated[
    SecretStr,
    Field(min_length=32),
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "AI Knowledge Hub"
    APP_ENV: str = "dev"

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"
    DB_NAME: str = "ai_knowledge_hub"

    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = Field(default=6379, ge=1, le=65535)
    REDIS_DB: int = Field(default=0, ge=0)
    REDIS_PASSWORD: SecretStr = Field(min_length=16)
    REDIS_CONNECT_TIMEOUT_SECONDS: PositiveFloat = 1.0
    REDIS_SOCKET_TIMEOUT_SECONDS: PositiveFloat = 1.0

    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: PositiveInt = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: PositiveInt = 60

    JWT_ACTIVE_KEY_ID: JwtKeyId
    JWT_SIGNING_KEYS: dict[JwtKeyId, JwtSigningSecret] = Field(
        min_length=1,
    )
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: PositiveInt = 30

    SESSION_EXPIRATION_MODE: Literal["absolute", "sliding"] = "absolute"
    SESSION_TTL_DAYS: PositiveInt = 7
    SESSION_ABSOLUTE_MAX_DAYS: PositiveInt = 30

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @model_validator(mode="after")
    def validate_session_expiration(self) -> Self:
        if (
            self.SESSION_EXPIRATION_MODE == "sliding"
            and self.SESSION_ABSOLUTE_MAX_DAYS < self.SESSION_TTL_DAYS
        ):
            raise ValueError(
                "SESSION_ABSOLUTE_MAX_DAYS must be greater than or equal "
                "to SESSION_TTL_DAYS in sliding mode."
            )

        return self

    @model_validator(mode="after")
    def validate_jwt_key_ring(self) -> Self:
        if self.JWT_ACTIVE_KEY_ID not in self.JWT_SIGNING_KEYS:
            raise ValueError("JWT_ACTIVE_KEY_ID must exist in JWT_SIGNING_KEYS.")

        return self

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()
