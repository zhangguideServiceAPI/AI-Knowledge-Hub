from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class DocumentVersionPrepareResponse(BaseModel):
    """系统完成解析和分块后返回的待索引 Version 摘要。"""

    id: UUID
    document_id: UUID
    version_number: int
    status: str
    chunk_count: int
    created_at: datetime
