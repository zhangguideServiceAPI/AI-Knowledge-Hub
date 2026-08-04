from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    NonNegativeInt,
    PositiveInt,
)

from app.models.file_resource import FileStatus


class FileResourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    content_type: str
    size_bytes: NonNegativeInt
    status: FileStatus
    created_at: datetime
    updated_at: datetime


class FileResourceListResponse(BaseModel):
    items: list[FileResourceResponse]
    limit: PositiveInt
    offset: NonNegativeInt
