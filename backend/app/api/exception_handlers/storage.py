"""文件与对象存储相关异常的 HTTP 映射。"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.logging import logger
from app.schemas.error import ErrorResponse
from app.storage.exceptions import (
    EmptyFileError,
    FileContentUnavailableError,
    FileDeleteFailedError,
    FileResourceNotFoundError,
    FileTooLargeError,
    FileUploadFailedError,
    InvalidFileNameError,
    StorageUnavailableError,
    UnsupportedFileTypeError,
)


async def invalid_upload_metadata_handler(
    _request: Request,
    _error: InvalidFileNameError | EmptyFileError,
) -> JSONResponse:
    """将空文件或非法文件名转换为统一的上传元数据 400 响应。"""

    response = ErrorResponse(detail="Invalid upload metadata.")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=response.model_dump(),
    )


async def file_too_large_handler(
    _request: Request,
    _error: FileTooLargeError,
) -> JSONResponse:
    """将文件超限转换为 413 响应。"""

    response = ErrorResponse(detail="Uploaded file is too large.")
    return JSONResponse(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        content=response.model_dump(),
    )


async def unsupported_file_type_handler(
    _request: Request,
    _error: UnsupportedFileTypeError,
) -> JSONResponse:
    """将未允许的 MIME 类型或文件签名转换为 415 响应。"""

    response = ErrorResponse(detail="Unsupported file type.")
    return JSONResponse(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        content=response.model_dump(),
    )


async def storage_unavailable_handler(
    request: Request,
    _error: StorageUnavailableError,
) -> JSONResponse:
    """记录对象存储暂不可用的请求上下文，并返回 503 响应。"""

    logger.error(
        "storage.provider.unavailable method=%s path=%s",
        request.method,
        request.url.path,
    )
    response = ErrorResponse(detail="File storage is temporarily unavailable.")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=response.model_dump(),
    )


async def file_upload_failed_handler(
    request: Request,
    _error: FileUploadFailedError,
) -> JSONResponse:
    """记录上传业务失败并返回不包含 Provider 细节的 500 响应。"""

    logger.error(
        "storage.upload.failed method=%s path=%s",
        request.method,
        request.url.path,
    )
    response = ErrorResponse(detail="File upload failed.")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(),
    )


async def file_resource_not_found_handler(
    _request: Request,
    _error: FileResourceNotFoundError,
) -> JSONResponse:
    """将当前用户不可访问的 FileResource 转换为 404 响应。"""

    response = ErrorResponse(detail="File not found.")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=response.model_dump(),
    )


async def file_delete_failed_handler(
    request: Request,
    _error: FileDeleteFailedError,
) -> JSONResponse:
    """记录文件删除失败并返回 500 响应。"""

    logger.error(
        "storage.delete.failed method=%s path=%s",
        request.method,
        request.url.path,
    )
    response = ErrorResponse(detail="File deletion failed.")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(),
    )


async def file_content_unavailable_handler(
    request: Request,
    _error: FileContentUnavailableError,
) -> JSONResponse:
    """记录对象内容不可读取的情况，并返回 500 响应。"""

    logger.error(
        "storage.download.failed method=%s path=%s",
        request.method,
        request.url.path,
    )
    response = ErrorResponse(detail="File content is unavailable.")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(),
    )


def register_storage_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 注册文件和对象存储领域的全部异常映射。"""

    app.add_exception_handler(InvalidFileNameError, invalid_upload_metadata_handler)
    app.add_exception_handler(EmptyFileError, invalid_upload_metadata_handler)
    app.add_exception_handler(FileTooLargeError, file_too_large_handler)
    app.add_exception_handler(UnsupportedFileTypeError, unsupported_file_type_handler)
    app.add_exception_handler(StorageUnavailableError, storage_unavailable_handler)
    app.add_exception_handler(FileUploadFailedError, file_upload_failed_handler)
    app.add_exception_handler(
        FileResourceNotFoundError, file_resource_not_found_handler
    )
    app.add_exception_handler(FileDeleteFailedError, file_delete_failed_handler)
    app.add_exception_handler(
        FileContentUnavailableError, file_content_unavailable_handler
    )
