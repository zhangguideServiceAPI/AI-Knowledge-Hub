from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_chat_service, get_current_user
from app.schemas.ai import (
    AIErrorResponse,
    ChatRequestSchema,
    ChatResponseSchema,
)
from app.schemas.error import ErrorResponse
from app.schemas.user import UserResponse
from app.services.chat_service import ChatService


router = APIRouter(
    prefix="/ai",
    tags=["AI"],
)


@router.post(
    "/chat",
    response_model=ChatResponseSchema,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": AIErrorResponse,
            "description": "Invalid AI model or generation parameters.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "User account is inactive.",
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "model": AIErrorResponse,
            "description": "AI provider is temporarily rate limited.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": AIErrorResponse,
            "description": "Unexpected AI service failure.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": AIErrorResponse,
            "description": "AI service is temporarily unavailable.",
        },
        status.HTTP_504_GATEWAY_TIMEOUT: {
            "model": AIErrorResponse,
            "description": "AI service timed out.",
        },
    },
)
async def chat(
    request: ChatRequestSchema,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponseSchema:
    return await chat_service.chat(
        request,
        user_id=current_user.id,
    )
