from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_user, get_knowledge_service
from app.schemas.error import ErrorResponse
from app.schemas.knowledge import KnowledgeBaseCreateRequest, KnowledgeBaseResponse
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
