from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document_version import DocumentVersion, DocumentVersionStatus
from app.models.file_resource import FileResource
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_document import KnowledgeDocument
from app.models.user import User


def _create_document(
    session: Session,
    *,
    email: str = "version-owner@example.com",
    object_key: str = "users/1/version-report.pdf",
) -> KnowledgeDocument:
    user = User(email=email, password_hash="hashed-password")
    session.add(user)
    session.flush()

    knowledge_base = KnowledgeBase(owner_id=user.id, name="Product manuals")
    file_resource = FileResource(
        owner_id=user.id,
        storage_provider="local",
        bucket="local",
        object_key=object_key,
        original_filename="report.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        sha256="a" * 64,
    )
    session.add_all([knowledge_base, file_resource])
    session.flush()

    document = KnowledgeDocument(
        knowledge_base_id=knowledge_base.id,
        file_id=file_resource.id,
    )
    session.add(document)
    session.flush()
    return document


def _build_version(
    document_id: str,
    *,
    version_number: int = 1,
    processing_fingerprint: str = "a" * 64,
) -> DocumentVersion:
    return DocumentVersion(
        document_id=document_id,
        version_number=version_number,
        processing_fingerprint=processing_fingerprint,
        parser_name="pypdf",
        parser_version="1",
        chunker_name="structure-aware",
        chunker_config={"max_tokens": 512, "overlap_tokens": 64},
        embedding_profile="openai/text-embedding-3-small@v1",
        embedding_dimension=1536,
    )


def test_create_document_version_with_defaults(session: Session) -> None:
    document = _create_document(session)
    version = _build_version(document.id)

    session.add(version)
    session.flush()
    session.refresh(version)

    assert UUID(version.id).version == 4
    assert version.document_id == document.id
    assert version.status == DocumentVersionStatus.PENDING.value
    assert version.failure_reason is None
    assert version.created_at is not None
    assert version.updated_at is not None


def test_document_cannot_reuse_version_number(session: Session) -> None:
    document = _create_document(session)
    session.add(_build_version(document.id))
    session.flush()

    session.add(
        _build_version(
            document.id,
            processing_fingerprint="b" * 64,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_document_cannot_reuse_processing_fingerprint(session: Session) -> None:
    document = _create_document(session)
    session.add(_build_version(document.id))
    session.flush()

    session.add(
        _build_version(
            document.id,
            version_number=2,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_document_version_requires_existing_document(session: Session) -> None:
    version = _build_version(str(uuid4()))
    session.add(version)

    with pytest.raises(IntegrityError):
        session.flush()


def test_document_version_failed_status_requires_failure_reason(
    session: Session,
) -> None:
    document = _create_document(session)
    version = _build_version(document.id)
    version.status = DocumentVersionStatus.FAILED.value
    session.add(version)

    with pytest.raises(IntegrityError):
        session.flush()


def test_document_active_version_must_exist(session: Session) -> None:
    document = _create_document(session)
    document.active_version_id = str(uuid4())
    session.add(document)

    with pytest.raises(IntegrityError):
        session.flush()


def test_document_active_version_must_belong_to_document(session: Session) -> None:
    first_document = _create_document(
        session,
        email="first-version-owner@example.com",
        object_key="users/1/first-version-report.pdf",
    )
    second_document = _create_document(
        session,
        email="second-version-owner@example.com",
        object_key="users/2/second-version-report.pdf",
    )
    version = _build_version(second_document.id)
    session.add(version)
    session.flush()

    first_document.active_version_id = version.id
    session.add(first_document)

    with pytest.raises(IntegrityError):
        session.flush()
