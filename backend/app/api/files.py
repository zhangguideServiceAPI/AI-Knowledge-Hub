from collections.abc import Iterator
from typing import Annotated, BinaryIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_current_user, get_file_service
from app.schemas.error import ErrorResponse
from app.schemas.file import FileResourceListResponse, FileResourceResponse
from app.schemas.user import UserResponse
from app.services.file_service import FileDownload, FileService


router = APIRouter(
    prefix="/files",
    tags=["Files"],
)


def _stream_file(
    stream: BinaryIO,
    chunk_size: int,
) -> Iterator[bytes]:
    try:
        while chunk := stream.read(chunk_size):
            yield chunk
    finally:
        stream.close()


# POST /files
# Content-Type: multipart/form-data; boundary=abc123

# --abc123
# Content-Disposition: form-data; name="upload"; filename="report.pdf"
# Content-Type: application/pdf


# %PDF-1.7
# file content
# --abc123--
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


@router.get(
    "/{file_id}",
    response_model=FileResourceResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "File not found.",
        },
    },
)
def get_file_resource(
    file_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> FileResourceResponse:
    return file_service.get_file(
        file_id=file_id,
        owner_id=current_user.id,
    )


@router.get(
    "/{file_id}/download",
    response_class=StreamingResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "File not found.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "File content is unavailable.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "File storage is temporarily unavailable.",
        },
    },
)
def download_file_resource(
    file_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> StreamingResponse:
    download: FileDownload = file_service.download_file(
        owner_id=current_user.id,
        file_id=file_id,
    )
    encoded_filename = quote(download.original_filename, safe="")

    return StreamingResponse(
        _stream_file(download.stream, download.chunk_size),
        media_type=download.content_type,
        headers={
            "Content-Disposition": (f"attachment; filename*=UTF-8''{encoded_filename}"),
            "Content-Length": str(download.size_bytes),
        },
    )


@router.get(
    "",
    response_model=FileResourceListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
    },
)
def list_file_resources(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FileResourceListResponse:
    return file_service.list_files(
        owner_id=current_user.id,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "File not found.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "File deletion failed.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "File storage is temporarily unavailable.",
        },
    },
)
def delete_file_resource(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    file_id: str,
) -> None:
    file_service.delete_file(
        file_id=file_id,
        owner_id=current_user.id,
    )
