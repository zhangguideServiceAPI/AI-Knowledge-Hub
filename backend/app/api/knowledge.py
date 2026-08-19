from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_user, get_knowledge_service
from app.schemas.error import ErrorResponse
from app.schemas.knowledge import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseResponse,
    KnowledgeDocumentResponse,
)
from app.schemas.user import UserResponse
from app.services.knowledge_service import KnowledgeService


router = APIRouter(
    prefix="/knowledge-bases",
    tags=["Knowledge"],
)


@router.post(
    "",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Knowledge base could not be created.",
        },
    },
)
def create_knowledge_base(
    request: KnowledgeBaseCreateRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    knowledge_service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> KnowledgeBaseResponse:
    """创建当前认证用户主动拥有的知识库，并返回创建后的元数据。"""

    return knowledge_service.create_base(
        owner_id=current_user.id,
        name=request.name,
    )


@router.put(
    "/{knowledge_base_id}/documents/{file_id}",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Knowledge base or file was not found.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Knowledge document could not be created.",
        },
    },
)
def add_file_to_knowledge_base(
    knowledge_base_id: str,
    file_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    knowledge_service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> KnowledgeDocumentResponse:
    """
    将一个 READY FileResource 主动加入当前用户的知识库。

    使用 PUT 是因为相同的 Base 与 File 重复请求应复用同一 Document；
    本接口只建立管理关系，不会读取文件或启动 Parse、Chunk、Embedding。
    """

    return knowledge_service.add_file_to_base(
        owner_id=current_user.id,
        knowledge_base_id=knowledge_base_id,
        file_id=file_id,
    )
