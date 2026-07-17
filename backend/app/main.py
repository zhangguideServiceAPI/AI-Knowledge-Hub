from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import settings
from app.core.logging import logger, setup_logging


setup_logging()

app = FastAPI(title=settings.APP_NAME)

logger.info("Application started")

app.include_router(health_router)


@app.get("/hello")
def hello():

    logger.debug("This is a debug message for hello.") #不会显示 因为 level 是 info 级别，默认日志级别是 warning
    logger.info("This is an info message for hello.")
    logger.warning("This is a warning message for hello.")
    logger.error("This is an error message for hello.")
    logger.critical("This is a critical message for hello.")

    return {
        "app_name": settings.APP_NAME,
        "env": settings.APP_ENV
    }
