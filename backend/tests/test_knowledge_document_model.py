from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.file_resource import FileResource
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_document import KnowledgeDocument
from app.models.user import User


def _create_user(session: Session, email: str) -> User:
    user = User(email=email, password_hash="hashed-password")
    session.add(user)
    session.flush()
    return user


def _create_file_resource(
    session: Session, owner_id: int, object_key: str
) -> FileResource:
    file_resource = FileResource(
        owner_id=owner_id,
        storage_provider="local",
        bucket="local",
        object_key=object_key,
        original_filename="report.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        sha256="a" * 64,
    )
    session.add(file_resource)
    session.flush()
    return file_resource


def _create_knowledge_base(
    session: Session,
    owner_id: int,
    name: str,
) -> KnowledgeBase:
    knowledge_base = KnowledgeBase(owner_id=owner_id, name=name)
    session.add(knowledge_base)
    session.flush()
    return knowledge_base


def test_create_knowledge_document_with_defaults(session: Session) -> None:
    user = _create_user(session, "document-owner@example.com")
    knowledge_base = _create_knowledge_base(session, user.id, "Product manuals")
    file_resource = _create_file_resource(session, user.id, "users/1/report.pdf")
    document = KnowledgeDocument(
        knowledge_base_id=knowledge_base.id,
        file_id=file_resource.id,
    )

    session.add(document)
    session.flush()
    session.refresh(document)

    assert UUID(document.id).version == 4
    assert document.knowledge_base_id == knowledge_base.id
    assert document.file_id == file_resource.id
    assert document.created_at is not None
    assert document.updated_at is not None


def test_file_can_be_added_to_different_knowledge_bases(session: Session) -> None:
    user = _create_user(session, "multiple-bases-owner@example.com")
    file_resource = _create_file_resource(session, user.id, "users/1/shared.pdf")
    first_base = _create_knowledge_base(session, user.id, "Engineering")
    second_base = _create_knowledge_base(session, user.id, "Support")
    first_document = KnowledgeDocument(
        knowledge_base_id=first_base.id,
        file_id=file_resource.id,
    )
    second_document = KnowledgeDocument(
        knowledge_base_id=second_base.id,
        file_id=file_resource.id,
    )

    session.add_all([first_document, second_document])
    session.flush()

    assert first_document.id != second_document.id


def test_file_cannot_be_added_twice_to_same_knowledge_base(session: Session) -> None:
    user = _create_user(session, "duplicate-document-owner@example.com")
    knowledge_base = _create_knowledge_base(session, user.id, "Product manuals")
    file_resource = _create_file_resource(session, user.id, "users/1/duplicate.pdf")
    session.add(
        KnowledgeDocument(
            knowledge_base_id=knowledge_base.id,
            file_id=file_resource.id,
        )
    )
    session.flush()

    session.add(
        KnowledgeDocument(
            knowledge_base_id=knowledge_base.id,
            file_id=file_resource.id,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_knowledge_base_must_exist(session: Session) -> None:
    user = _create_user(session, "missing-base-owner@example.com")
    file_resource = _create_file_resource(session, user.id, "users/1/missing-base.pdf")
    document = KnowledgeDocument(
        knowledge_base_id=str(uuid4()),
        file_id=file_resource.id,
    )
    session.add(document)

    with pytest.raises(IntegrityError):
        session.flush()


def test_file_resource_must_exist(session: Session) -> None:
    user = _create_user(session, "missing-file-owner@example.com")
    knowledge_base = _create_knowledge_base(session, user.id, "Product manuals")
    document = KnowledgeDocument(
        knowledge_base_id=knowledge_base.id,
        file_id=str(uuid4()),
    )
    session.add(document)

    with pytest.raises(IntegrityError):
        session.flush()
