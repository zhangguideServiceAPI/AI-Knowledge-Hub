from datetime import datetime

from app.models.user import User
from app.schemas.user import UserResponse


def test_user_response_from_orm_excludes_password_hash() -> None:
    timestamp = datetime.now()
    user = User(
        id=1,
        email="user@example.com",
        password_hash="stored-password-hash",
        nickname="nickname",
        avatar_url="http://example.com/avatar.png",
        status="active",
        created_at=timestamp,
        updated_at=timestamp,
    )

    response = UserResponse.model_validate(user)
    response_data = response.model_dump()

    assert response.id == 1
    assert str(response.email) == "user@example.com"
    assert response.status == "active"
    assert response.created_at == timestamp
    assert response.updated_at == timestamp
    assert "password" not in response_data
    assert "password_hash" not in response_data
