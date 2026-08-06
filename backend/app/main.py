from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.exception_handlers import register_exception_handlers
from app.api.health import router as health_router
from app.api.user import router as user_router
from app.core.config import settings
from app.core.logging import logger, setup_logging


setup_logging()

app = FastAPI(title=settings.APP_NAME)

register_exception_handlers(app)

logger.info("Application started")

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(user_router)
