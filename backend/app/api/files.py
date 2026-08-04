from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.dependencies import get_current_user, get_file_service
from app.schemas.error import ErrorResponse
from app.schemas.file import FileResourceResponse
from app.schemas.user import UserResponse
from app.services.file_service import FileService


router = APIRouter(
    prefix="/files",
    tags=["Files"],
)


@router.post(
    "",
    response_model=FileResourceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Invalid upload metadata.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {
            "model": ErrorResponse,
            "description": "Uploaded file is too large.",
        },
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
            "model": ErrorResponse,
            "description": "Unsupported file type.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "File storage is temporarily unavailable.",
        },
    },
)
def upload_file(
    upload: Annotated[UploadFile, File(...)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> FileResourceResponse:
    return file_service.upload(
        owner_id=current_user.id,
        original_filename=upload.filename,
        content_type=upload.content_type,
        source=upload.file,
    )
