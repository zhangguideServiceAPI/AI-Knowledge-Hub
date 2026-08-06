import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            JWT_SECRET_KEY="short-secret",
        )

    assert error.value.errors()[0]["loc"] == ("JWT_SECRET_KEY",)
