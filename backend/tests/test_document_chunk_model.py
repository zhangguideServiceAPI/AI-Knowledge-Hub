from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.file_resource import FileResource
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_document import KnowledgeDocument
from app.models.user import User


def _create_version(session: Session) -> DocumentVersion:
    user = User(email="chunk-owner@example.com", password_hash="hashed-password")
    session.add(user)
    session.flush()

    knowledge_base = KnowledgeBase(owner_id=user.id, name="Product manuals")
    file_resource = FileResource(
        owner_id=user.id,
        storage_provider="local",
        bucket="local",
        object_key="users/1/chunk-report.pdf",
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

    version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        processing_fingerprint="a" * 64,
        parser_name="pypdf",
        parser_version="1",
        chunker_name="structure-aware",
        chunker_config={"max_tokens": 512, "overlap_tokens": 64},
        embedding_profile="openai/text-embedding-3-small@v1",
        embedding_dimension=1536,
    )
    session.add(version)
    session.flush()
    return version


def _build_chunk(
    version_id: str,
    *,
    chunk_index: int = 0,
    content: str = "The product supports SSO.",
    token_count: int = 6,
) -> DocumentChunk:
    return DocumentChunk(
        document_version_id=version_id,
        chunk_index=chunk_index,
        content=content,
        token_count=token_count,
        source_locator={"page": 3, "section": "Authentication"},
    )


def test_create_document_chunk_with_citation_metadata(session: Session) -> None:
    version = _create_version(session)
    chunk = _build_chunk(version.id)

    session.add(chunk)
    session.flush()
    session.refresh(chunk)

    assert UUID(chunk.id).version == 4
    assert chunk.document_version_id == version.id
    assert chunk.source_locator == {"page": 3, "section": "Authentication"}
    assert chunk.created_at is not None


def test_document_version_cannot_reuse_chunk_index(session: Session) -> None:
    version = _create_version(session)
    session.add(_build_chunk(version.id))
    session.flush()
    session.add(_build_chunk(version.id))

    with pytest.raises(IntegrityError):
        session.flush()


def test_document_chunk_requires_existing_version(session: Session) -> None:
    chunk = _build_chunk(str(uuid4()))
    session.add(chunk)

    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize(
    ("chunk_index", "content", "token_count"),
    [(-1, "valid content", 1), (0, "", 1), (0, "valid content", -1)],
)
def test_document_chunk_rejects_invalid_content_or_counts(
    session: Session,
    chunk_index: int,
    content: str,
    token_count: int,
) -> None:
    version = _create_version(session)
    chunk = _build_chunk(
        version.id,
        chunk_index=chunk_index,
        content=content,
        token_count=token_count,
    )
    session.add(chunk)

    with pytest.raises(IntegrityError):
        session.flush()
