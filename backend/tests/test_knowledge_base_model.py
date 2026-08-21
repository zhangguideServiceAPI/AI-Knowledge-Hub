from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.knowledge_base import KnowledgeBase
from app.models.user import User


def _create_user(session: Session, email: str) -> User:
    user = User(email=email, password_hash="hashed-password")
    session.add(user)
    session.flush()
    return user


def test_create_knowledge_base_with_defaults(session: Session) -> None:
    user = _create_user(session, "knowledge-base-owner@example.com")
    knowledge_base = KnowledgeBase(owner_id=user.id, name="Product manuals")

    session.add(knowledge_base)
    session.flush()
    session.refresh(knowledge_base)

    assert UUID(knowledge_base.id).version == 4
    assert knowledge_base.owner_id == user.id
    assert knowledge_base.name == "Product manuals"
    assert knowledge_base.created_at is not None
    assert knowledge_base.updated_at is not None


def test_knowledge_base_owner_must_exist(session: Session) -> None:
    knowledge_base = KnowledgeBase(owner_id=999_999, name="Orphaned base")
    session.add(knowledge_base)

    with pytest.raises(IntegrityError):
        session.flush()


def test_knowledge_base_name_cannot_be_empty(session: Session) -> None:
    user = _create_user(session, "empty-name-owner@example.com")
    knowledge_base = KnowledgeBase(owner_id=user.id, name="")
    session.add(knowledge_base)

    with pytest.raises(IntegrityError):
        session.flush()
