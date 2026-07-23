from sqlalchemy.orm import Session

from app.db.repositories.user_repository import UserRepository
from app.models.user import User


def test_create_and_get_user(session: Session) -> None:
    repository = UserRepository(session)
    user = User(
        email="user@example.com",
        password_hash="hashed-password",
    )

    created_user = repository.create(user)

    assert created_user.id is not None
    assert created_user.status == "active"
    assert created_user.created_at is not None
    assert created_user.updated_at is not None

    user_by_id = repository.get_by_id(created_user.id)
    user_by_email = repository.get_by_email(created_user.email)

    assert user_by_id is not None
    assert user_by_id.id == created_user.id
    assert user_by_email is not None
    assert user_by_email.email == created_user.email


def test_create_can_be_rolled_back(session: Session) -> None:
    repository = UserRepository(session)
    email = "rollback@example.com"
    user = User(
        email=email,
        password_hash="hashed-password",
    )

    repository.create(user)
    session.rollback()

    assert repository.get_by_email(email) is None
