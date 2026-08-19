from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.repositories.file_repository import FileRepository
from app.db.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge import (
    ChunkDraft,
    Chunker,
    ChunkingConfig,
    EmbeddingProfile,
    ParserRegistry,
    ParsedDocument,
    build_processing_fingerprint,
)
from app.knowledge.exceptions import (
    KnowledgeBaseNotFoundError,
    KnowledgeBaseWriteError,
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentWriteError,
    KnowledgeVersionWriteError,
)
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion, DocumentVersionStatus
from app.models.file_resource import FileResource
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_document import KnowledgeDocument
from app.storage.exceptions import FileResourceNotFoundError
from app.storage.provider import StorageProvider


@dataclass(frozen=True)
class KnowledgeIndexingComponents:
    """
    准备一个 DocumentVersion 时由 Service 编排的运行时依赖。

    这些值由服务器 Dependency 从 Settings 和 Provider 组装，不来自 API 请求；
    因此客户端不能自行选择 Tokenizer、Chunk 大小或 Embedding 模型。
    """

    storage_provider: StorageProvider
    parser_registry: ParserRegistry
    chunker: Chunker
    chunking_config: ChunkingConfig
    embedding_profile: EmbeddingProfile


class KnowledgeService:
    """Owns business operations that connect FileResource and Knowledge models."""

    def __init__(self, session: Session) -> None:
        """用同一个数据库 Session 组装 File 与 Knowledge 仓储，保持一次业务操作的事务边界。"""

        self._session = session
        self._file_repository = FileRepository(session)
        self._knowledge_repository = KnowledgeRepository(session)

    def create_base(self, *, owner_id: int, name: str) -> KnowledgeBase:
        """
        为当前用户创建一个主动管理的 KnowledgeBase。

        输入是已认证用户 ID 与已经由 API Schema 清理过的名称；
        返回已提交的 KnowledgeBase。此方法不创建 Document、不上传文件，
        也不启动解析或索引流程。
        """

        knowledge_base = KnowledgeBase(owner_id=owner_id, name=name)
        try:
            self._knowledge_repository.create_base(knowledge_base)
            self._session.commit()
        except SQLAlchemyError as error:
            # commit 失败后必须 rollback，才能让同一个请求的 Session 恢复可用。
            self._session.rollback()
            raise KnowledgeBaseWriteError() from error

        return knowledge_base

    def add_file_to_base(
        self,
        *,
        owner_id: int,
        knowledge_base_id: str,
        file_id: str,
    ) -> KnowledgeDocument:
        """
        将一个当前用户的 READY FileResource 加入其 KnowledgeBase。

        输入是所有者、知识库和文件 ID；返回新建或已存在的 Document。
        本方法仅建立 File 与知识库的管理关系，不解析文件、不生成 Chunk 或向量。
        """

        # 先按 owner_id 查询，避免只凭任意 UUID 把其他用户的知识库或文件关联进来。
        knowledge_base = self._knowledge_repository.get_owned_base(
            knowledge_base_id=knowledge_base_id,
            owner_id=owner_id,
        )
        if knowledge_base is None:
            raise KnowledgeBaseNotFoundError()

        # FileRepository.get_owned 同时检查 owner、READY 状态和 deleted_at；
        # 非 READY 文件不能进入后续解析流程。
        file_resource = self._file_repository.get_owned(
            file_id=file_id,
            owner_id=owner_id,
        )
        if file_resource is None:
            raise FileResourceNotFoundError()

        existing_document = self._knowledge_repository.get_document_by_base_and_file(
            knowledge_base_id=knowledge_base.id,
            file_id=file_resource.id,
        )
        if existing_document is not None:
            # 重复请求保持幂等：不创建第二个 Document，也不会再次触发索引。
            return existing_document

        document = KnowledgeDocument(
            knowledge_base_id=knowledge_base.id,
            file_id=file_resource.id,
        )
        try:
            self._knowledge_repository.create_document(document)
            # commit 才真正提交事务；在它成功前，其他连接看不到这条 Document。
            self._session.commit()
        except IntegrityError as error:
            # 并发请求都在前面的查询中没找到 Document 时，数据库唯一约束会裁决。
            self._session.rollback()
            existing_document = (
                self._knowledge_repository.get_document_by_base_and_file(
                    knowledge_base_id=knowledge_base.id,
                    file_id=file_resource.id,
                )
            )
            if existing_document is not None:
                return existing_document
            raise KnowledgeDocumentWriteError() from error
        except SQLAlchemyError as error:
            self._session.rollback()
            raise KnowledgeDocumentWriteError() from error

        return document

    def parse_and_chunk(
        self,
        *,
        owner_id: int,
        document_id: str,
        storage_provider: StorageProvider,
        parser_registry: ParserRegistry,
        chunker: Chunker,
    ) -> tuple[ChunkDraft, ...]:
        """
        读取当前用户的 READY 文件，解析并生成尚未持久化的 ChunkDraft。

        输入是 Document、存储实现、Parser 注册表和 Chunker；返回有序的内存分块。
        本方法不写 MySQL、不生成 embedding，也不调用 Qdrant。
        """

        file_resource = self._get_owned_ready_file(
            document_id=document_id,
            owner_id=owner_id,
        )
        parsed_document = self._parse_file_resource(
            file_resource=file_resource,
            storage_provider=storage_provider,
            parser_registry=parser_registry,
        )

        # Chunker 只处理统一 ParsedDocument，不知道 FileResource、权限或 Storage。
        return chunker.chunk(parsed_document)

    def prepare_document_version(
        self,
        *,
        owner_id: int,
        document_id: str,
        components: KnowledgeIndexingComponents,
    ) -> tuple[DocumentVersion, tuple[DocumentChunk, ...]]:
        """
        准备一个可进入 Embedding 阶段的 DocumentVersion 与全部 DocumentChunk。

        输入是当前用户、Document 和服务器组装的索引组件；本方法依次读取文件、
        解析、按 Token 分块、自动计算处理指纹，并原子写入 MySQL。
        返回新建或幂等复用的 pending Version 与有序 Chunk；不调用 Embedding 或 Qdrant，
        因此也不会把 Document.active_version_id 指向这条尚未完成索引的 Version。
        """

        file_resource = self._get_owned_ready_file(
            document_id=document_id,
            owner_id=owner_id,
        )
        parsed_document = self._parse_file_resource(
            file_resource=file_resource,
            storage_provider=components.storage_provider,
            parser_registry=components.parser_registry,
        )
        drafts = components.chunker.chunk(parsed_document)
        chunker_config = components.chunking_config.fingerprint_payload()
        processing_fingerprint = build_processing_fingerprint(
            file_sha256=file_resource.sha256,
            parser_name=parsed_document.parser_name,
            parser_version=parsed_document.parser_version,
            chunker_name=components.chunker.chunker_name,
            chunker_config=chunker_config,
            embedding_profile=components.embedding_profile,
        )

        return self.persist_chunks(
            owner_id=owner_id,
            document_id=document_id,
            drafts=drafts,
            processing_fingerprint=processing_fingerprint,
            parser_name=parsed_document.parser_name,
            parser_version=parsed_document.parser_version,
            chunker_name=components.chunker.chunker_name,
            chunker_config=chunker_config,
            embedding_profile=components.embedding_profile.alias,
            embedding_dimension=components.embedding_profile.dimension,
        )

    def persist_chunks(
        self,
        *,
        owner_id: int,
        document_id: str,
        drafts: tuple[ChunkDraft, ...],
        processing_fingerprint: str,
        parser_name: str,
        parser_version: str,
        chunker_name: str,
        chunker_config: dict[str, object],
        embedding_profile: str,
        embedding_dimension: int,
    ) -> tuple[DocumentVersion, tuple[DocumentChunk, ...]]:
        """
        将已分块的内存结果原子写入 MySQL。

        输入是当前用户、所属 Document、多个 ChunkDraft 和完整处理配置；
        返回新建或已复用的一条 DocumentVersion 及其有序 Chunk。
        本方法只做 MySQL 元数据持久化，不生成 embedding、不写 Qdrant，
        所以成功的 Version 仍停留在 pending 状态。
        """

        document = self._knowledge_repository.get_owned_document(
            document_id=document_id,
            owner_id=owner_id,
        )
        if document is None:
            raise KnowledgeDocumentNotFoundError()
        if not drafts:
            raise KnowledgeVersionWriteError("Cannot persist an empty chunk set.")

        existing_version = self._knowledge_repository.get_version_by_fingerprint(
            document_id=document_id,
            processing_fingerprint=processing_fingerprint,
        )
        if existing_version is not None:
            # 同一套 Parser/Chunker/Embedding 配置已经处理过，直接复用 Version。
            existing_chunks = self._knowledge_repository.list_chunks(
                document_version_id=existing_version.id
            )
            return existing_version, existing_chunks

        version = DocumentVersion(
            document_id=document_id,
            version_number=self._knowledge_repository.get_next_version_number(
                document_id=document_id
            ),
            processing_fingerprint=processing_fingerprint,
            parser_name=parser_name,
            parser_version=parser_version,
            chunker_name=chunker_name,
            chunker_config=chunker_config,
            embedding_profile=embedding_profile,
            embedding_dimension=embedding_dimension,
            status=DocumentVersionStatus.PENDING.value,
        )
        try:
            self._knowledge_repository.create_version(version)
            # UUID 的 default 在 flush 时执行；必须先 flush Version，Chunk 才能取得 version.id。
            chunks = tuple(
                DocumentChunk(
                    document_version_id=version.id,
                    chunk_index=chunk_index,
                    content=draft.content,
                    token_count=draft.token_count,
                    source_locator=draft.source_locator,
                )
                for chunk_index, draft in enumerate(drafts)
            )
            self._knowledge_repository.create_chunks(list(chunks))
            # Version 和所有 Chunk 必须一起提交，避免出现只有 Version 没有 Chunk 的半成品。
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            # 并发请求可能同时创建相同指纹；数据库唯一约束裁决后重新读取已成功的 Version。
            existing_version = self._knowledge_repository.get_version_by_fingerprint(
                document_id=document_id,
                processing_fingerprint=processing_fingerprint,
            )
            if existing_version is not None:
                existing_chunks = self._knowledge_repository.list_chunks(
                    document_version_id=existing_version.id
                )
                return existing_version, existing_chunks
            raise KnowledgeVersionWriteError() from error
        except SQLAlchemyError as error:
            self._session.rollback()
            raise KnowledgeVersionWriteError() from error

        return version, chunks

    def _get_owned_ready_file(
        self,
        *,
        document_id: str,
        owner_id: int,
    ) -> FileResource:
        """
        从当前用户的 Document 取回仍可读取的 READY FileResource。

        先通过 KnowledgeRepository 校验 Document、知识库和文件所有权，再通过
        FileRepository 取得文件元数据；任一检查失败时抛出原有的领域异常。
        """

        document = self._knowledge_repository.get_owned_document(
            document_id=document_id,
            owner_id=owner_id,
        )
        if document is None:
            raise KnowledgeDocumentNotFoundError()

        file_resource = self._file_repository.get_owned(
            file_id=document.file_id,
            owner_id=owner_id,
        )
        if file_resource is None:
            raise FileResourceNotFoundError()

        return file_resource

    def _parse_file_resource(
        self,
        *,
        file_resource: FileResource,
        storage_provider: StorageProvider,
        parser_registry: ParserRegistry,
    ) -> ParsedDocument:
        """
        打开一个已授权的 FileResource，选择对应 Parser 并返回统一解析结果。

        输入是已完成权限校验的文件和两个服务器组件；无论 Parser 成功、失败或
        MIME 类型不支持，finally 都会关闭 Storage 返回的二进制流。
        """

        # open() 返回的是存储层的二进制流；Service 不关心它来自本地磁盘还是 MinIO。
        source = storage_provider.open(file_resource.object_key)
        try:
            parser = parser_registry.get(file_resource.content_type)
            return parser.parse(
                source,
                content_type=file_resource.content_type,
                original_filename=file_resource.original_filename,
            )
        finally:
            # finally 无论 Parser 成功还是抛错都会执行，避免本地文件或 MinIO 流泄漏。
            source.close()
