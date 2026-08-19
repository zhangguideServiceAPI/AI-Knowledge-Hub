"""集中组装各业务领域的 FastAPI 异常映射。"""

from fastapi import FastAPI

from .ai import PublicAIError as PublicAIError
from .ai import map_ai_error as map_ai_error
from .ai import register_ai_exception_handlers
from .auth import register_auth_exception_handlers
from .knowledge import register_knowledge_exception_handlers
from .storage import register_storage_exception_handlers

__all__ = [
    "PublicAIError",
    "map_ai_error",
    "register_exception_handlers",
]


def register_exception_handlers(app: FastAPI) -> None:
    """注册所有领域的异常处理器，保持应用启动处只有一个统一入口。"""

    register_auth_exception_handlers(app)
    register_storage_exception_handlers(app)
    register_knowledge_exception_handlers(app)
    register_ai_exception_handlers(app)
