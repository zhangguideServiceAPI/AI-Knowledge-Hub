from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.file_resource import FileResource, FileStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_document import KnowledgeDocument


class KnowledgeRepository:
    """Database queries owned by the Knowledge domain."""

    def __init__(self, session: Session) -> None:
        """保存调用方传入的 SQLAlchemy Session，供本仓储执行知识域查询。"""

        self._session = session

    def get_owned_base(
        self,
        *,
        knowledge_base_id: str,
        owner_id: int,
    ) -> KnowledgeBase | None:
        """按知识库 ID 和 owner 查询可访问的 KnowledgeBase；未找到时返回 None。"""

        # select(...) 只构造 SQL 查询；session.scalar(...) 才执行查询并取第一条结果。
        statement = select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.owner_id == owner_id,
        )
        return self._session.scalar(statement)

    def get_document_by_base_and_file(
        self,
        *,
        knowledge_base_id: str,
        file_id: str,
    ) -> KnowledgeDocument | None:
        """查询某知识库中对某 FileResource 的既有 Document，支持重复请求幂等。"""

        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.knowledge_base_id == knowledge_base_id,
            KnowledgeDocument.file_id == file_id,
        )
        return self._session.scalar(statement)

    def get_owned_document(
        self,
        *,
        document_id: str,
        owner_id: int,
    ) -> KnowledgeDocument | None:
        """
        查询当前用户可处理的 Document。

        同时验证知识库所有权、文件所有权、文件 READY 状态和未删除条件；
        任一条件不满足均返回 None，不向 Service 暴露越权或不可用资源。
        """

        # join 把 Document、KnowledgeBase 和 FileResource 放进同一条查询；
        # 权限和 READY 状态在数据库查询阶段完成，调用方不会先拿到越权文件。
        statement = (
            select(KnowledgeDocument)
            .join(
                KnowledgeBase,
                KnowledgeDocument.knowledge_base_id == KnowledgeBase.id,
            )
            .join(FileResource, KnowledgeDocument.file_id == FileResource.id)
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeBase.owner_id == owner_id,
                FileResource.owner_id == owner_id,
                FileResource.status == FileStatus.READY.value,
                FileResource.deleted_at.is_(None),
            )
        )
        return self._session.scalar(statement)

    def create_document(
        self,
        document: KnowledgeDocument,
    ) -> KnowledgeDocument:
        """将新 Document 加入当前事务并刷新数据库默认字段，调用方决定何时提交。"""

        self._session.add(document)
        # flush 把 INSERT 发给数据库但不提交事务；这样可立刻拿到 UUID 和数据库默认时间。
        self._session.flush()
        # refresh 从数据库重新读取 server_default 等由数据库生成的字段。
        self._session.refresh(document)
        return document

    def get_version_by_fingerprint(
        self,
        *,
        document_id: str,
        processing_fingerprint: str,
    ) -> DocumentVersion | None:
        """按处理指纹查找一个 Document 的既有 Version，用于幂等复用。"""

        # 指纹是一次处理配置的稳定标识；命中后复用旧 Version，避免重复建索引。
        statement = select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.processing_fingerprint == processing_fingerprint,
        )
        return self._session.scalar(statement)

    def get_next_version_number(self, *, document_id: str) -> int:
        """返回某个 Document 下一个可用的连续版本号。"""

        # 数据库只返回当前最大版本号；第一个版本从 1 开始。
        latest_number = self._session.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document_id
            )
        )
        return (latest_number or 0) + 1

    def create_version(self, version: DocumentVersion) -> DocumentVersion:
        """把 Version 写入当前事务，并取得数据库/默认生成的字段。"""

        self._session.add(version)
        # flush 先发送 INSERT，让后续 Chunk 可以引用这个 Version；commit 仍由 Service 控制。
        self._session.flush()
        self._session.refresh(version)
        return version

    def create_chunks(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        """把同一 Version 的全部 Chunk 加入当前事务，暂不提交。"""

        self._session.add_all(chunks)
        # 一次 flush 写入全部 Chunk；任何一条失败都会由 Service 的事务统一回滚。
        self._session.flush()
        return chunks

    def list_chunks(self, *, document_version_id: str) -> tuple[DocumentChunk, ...]:
        """按原文顺序读取一个 Version 的 Chunk，供幂等请求复用结果。"""

        statement = (
            select(DocumentChunk)
            .where(DocumentChunk.document_version_id == document_version_id)
            .order_by(DocumentChunk.chunk_index)
        )
        return tuple(self._session.scalars(statement))
