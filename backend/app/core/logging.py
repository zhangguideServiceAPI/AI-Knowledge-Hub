import logging

from app.core.config import settings


logger = logging.getLogger("ai_knowledge_hub")


def setup_logging() -> None:
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
