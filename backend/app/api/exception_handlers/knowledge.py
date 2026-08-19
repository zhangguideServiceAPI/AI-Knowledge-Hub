"""KnowledgeBase、Document 与索引元数据异常的 HTTP 映射。"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.logging import logger
from app.knowledge.exceptions import KnowledgeBaseWriteError
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


def register_knowledge_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 注册目前 Knowledge 元数据写入相关的异常映射。"""

    app.add_exception_handler(
        KnowledgeBaseWriteError,
        knowledge_base_write_error_handler,
    )
