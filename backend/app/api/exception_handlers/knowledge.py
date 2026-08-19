"""KnowledgeBase、Document 与索引元数据异常的 HTTP 映射。"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.logging import logger
from app.knowledge.exceptions import (
    KnowledgeBaseNotFoundError,
    KnowledgeBaseWriteError,
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentWriteError,
    KnowledgeVersionWriteError,
)
from app.knowledge.parsing import ParsingError
from app.schemas.error import ErrorResponse


async def knowledge_base_write_error_handler(
    request: Request,
    _error: KnowledgeBaseWriteError,
) -> JSONResponse:
    """记录知识库写入失败，并向客户端返回不含数据库细节的 500 响应。"""

    logger.error(
        "knowledge.base.write.failed method=%s path=%s",
        request.method,
        request.url.path,
    )
    response = ErrorResponse(detail="Knowledge base could not be created.")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(),
    )


async def knowledge_base_not_found_handler(
    _request: Request,
    _error: KnowledgeBaseNotFoundError,
) -> JSONResponse:
    """将不存在或不属于当前用户的知识库统一隐藏为 404 响应。"""

    response = ErrorResponse(detail="Knowledge base not found.")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=response.model_dump(),
    )


async def knowledge_document_write_error_handler(
    request: Request,
    _error: KnowledgeDocumentWriteError,
) -> JSONResponse:
    """记录 Document 元数据写入失败，并返回不含数据库细节的 500 响应。"""

    logger.error(
        "knowledge.document.write.failed method=%s path=%s",
        request.method,
        request.url.path,
    )
    response = ErrorResponse(detail="Knowledge document could not be created.")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(),
    )


async def knowledge_document_not_found_handler(
    _request: Request,
    _error: KnowledgeDocumentNotFoundError,
) -> JSONResponse:
    """将不存在或不属于当前用户的 Document 统一隐藏为 404 响应。"""

    response = ErrorResponse(detail="Knowledge document not found.")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=response.model_dump(),
    )


async def knowledge_version_write_error_handler(
    request: Request,
    _error: KnowledgeVersionWriteError,
) -> JSONResponse:
    """记录 Version/Chunk 事务写入失败，并返回不含数据库细节的 500 响应。"""

    logger.error(
        "knowledge.version.write.failed method=%s path=%s",
        request.method,
        request.url.path,
    )
    response = ErrorResponse(detail="Document version could not be prepared.")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(),
    )


async def parsing_error_handler(
    request: Request,
    error: ParsingError,
) -> JSONResponse:
    """记录文件解析失败类型，并返回不泄露 Parser 实现细节的 422 响应。"""

    logger.info(
        "knowledge.document.parse.rejected method=%s path=%s error_type=%s",
        request.method,
        request.url.path,
        type(error).__name__,
    )
    response = ErrorResponse(
        detail="File content could not be parsed into knowledge chunks."
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=response.model_dump(),
    )


def register_knowledge_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 注册目前 Knowledge 元数据写入相关的异常映射。"""

    app.add_exception_handler(
        KnowledgeBaseWriteError,
        knowledge_base_write_error_handler,
    )
    app.add_exception_handler(
        KnowledgeBaseNotFoundError,
        knowledge_base_not_found_handler,
    )
    app.add_exception_handler(
        KnowledgeDocumentWriteError,
        knowledge_document_write_error_handler,
    )
    app.add_exception_handler(
        KnowledgeDocumentNotFoundError,
        knowledge_document_not_found_handler,
    )
    app.add_exception_handler(
        KnowledgeVersionWriteError,
        knowledge_version_write_error_handler,
    )
    app.add_exception_handler(ParsingError, parsing_error_handler)
