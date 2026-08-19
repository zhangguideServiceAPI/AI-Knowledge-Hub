"""create document versions and chunks tables

Revision ID: d4eb9a63f125
Revises: c6d08f2a91be
Create Date: 2026-08-17 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4eb9a63f125"
down_revision: Union[str, None] = "c6d08f2a91be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """向前迁移：创建 Version、Chunk，并补上 Document 的 active_version 外键。"""

    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("processing_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("parser_name", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("chunker_name", sa.String(length=64), nullable=False),
        sa.Column("chunker_config", sa.JSON(), nullable=False),
        sa.Column("embedding_profile", sa.String(length=128), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="pending", nullable=False
        ),
        sa.Column("failure_reason", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "chunker_name <> ''",
            name="ck_document_versions_chunker_name_non_empty",
        ),
        sa.CheckConstraint(
            "embedding_dimension > 0",
            name="ck_document_versions_embedding_dimension_positive",
        ),
        sa.CheckConstraint(
            "embedding_profile <> ''",
            name="ck_document_versions_embedding_profile_non_empty",
        ),
        sa.CheckConstraint(
            "(status IN ('failed', 'cleanup_required') AND failure_reason IS NOT NULL) OR (status NOT IN ('failed', 'cleanup_required') AND failure_reason IS NULL)",
            name="ck_document_versions_failure_reason",
        ),
        sa.CheckConstraint(
            "parser_name <> ''",
            name="ck_document_versions_parser_name_non_empty",
        ),
        sa.CheckConstraint(
            "parser_version <> ''",
            name="ck_document_versions_parser_version_non_empty",
        ),
        sa.CheckConstraint(
            "processing_fingerprint <> ''",
            name="ck_document_versions_processing_fingerprint_non_empty",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'indexed', 'failed', 'cleanup_required')",
            name="ck_document_versions_status",
        ),
        sa.CheckConstraint(
            "version_number > 0",
            name="ck_document_versions_version_number_positive",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name="fk_document_versions_document_id_knowledge_documents",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "id",
            name="uq_document_versions_id_document",
        ),
        sa.UniqueConstraint(
            "document_id",
            "processing_fingerprint",
            name="uq_document_versions_document_processing_fingerprint",
        ),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_document_version_number",
        ),
    )
    op.create_index(
        "ix_document_versions_document_status_created_at",
        "document_versions",
        ["document_id", "status", "created_at"],
        unique=False,
    )
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_version_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("source_locator", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name="ck_document_chunks_chunk_index_non_negative",
        ),
        sa.CheckConstraint(
            "content <> ''",
            name="ck_document_chunks_content_non_empty",
        ),
        sa.CheckConstraint(
            "token_count >= 0",
            name="ck_document_chunks_token_count_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_document_chunks_document_version_id_document_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_version_id",
            "chunk_index",
            name="uq_document_chunks_version_chunk_index",
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("active_version_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_knowledge_documents_active_version_document_versions",
        "knowledge_documents",
        "document_versions",
        ["id", "active_version_id"],
        ["document_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """向后迁移：按外键依赖反序删除 active_version、Chunk 和 Version。"""

    op.drop_constraint(
        "fk_knowledge_documents_active_version_document_versions",
        "knowledge_documents",
        type_="foreignkey",
    )
    op.drop_column("knowledge_documents", "active_version_id")
    op.drop_table("document_chunks")
    op.drop_table("document_versions")
