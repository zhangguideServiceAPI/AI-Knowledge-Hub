from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.file import FileResourceResponse


class KnowledgeBaseCreateRequest(BaseModel):
    """用户主动创建知识库时提交的名称。"""

    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, name: str) -> str:
        """删除名称首尾空格，并拒绝清理后为空的值。"""

        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Knowledge base name must not be blank.")
        return normalized_name


class KnowledgeBaseResponse(BaseModel):
    """创建或读取知识库时返回给 API 调用方的公共字段。"""

    # from_attributes=True 允许 Pydantic 从 SQLAlchemy 模型属性读取响应字段。
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentResponse(BaseModel):
    """文件成功加入知识库后返回的 Document 管理记录。"""

    # from_attributes=True 允许 Pydantic 从 SQLAlchemy KnowledgeDocument 读取字段。
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    knowledge_base_id: UUID
    file_id: UUID
    active_version_id: UUID | None
    created_at: datetime
    updated_at: datetime


class DocumentVersionResponse(BaseModel):
    """系统自动准备完成的待索引 DocumentVersion 摘要。"""

    id: UUID
    document_id: UUID
    version_number: int
    status: str
    chunk_count: int
    created_at: datetime


class KnowledgeFileIngestionResponse(BaseModel):
    """用户上传一个知识文件后，系统自动生成的全部业务记录摘要。"""

    file: FileResourceResponse
    document: KnowledgeDocumentResponse
    version: DocumentVersionResponse


class KnowledgeSearchRequest(BaseModel):
    """当前用户向一个 KnowledgeBase 提交的自然语言检索问题。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2_000)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, query: str) -> str:
        """清理问题首尾空白，并拒绝清理后没有语义内容的请求。"""

        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("Knowledge retrieval query must not be blank.")
        return normalized_query


class RetrievalHitResponse(BaseModel):
    """已通过 MySQL 所有权和 active Version 校验的一个可用检索结果。"""

    chunk_id: UUID
    document_id: UUID
    file_id: UUID
    content: str
    source_locator: dict[str, object]
    score: float


class KnowledgeSearchResponse(BaseModel):
    """一个 KnowledgeBase 的 Dense Retrieval 结果，不包含最终 Chat 回答。"""

    knowledge_base_id: UUID
    hits: list[RetrievalHitResponse]
