from app.db.redis_client import is_redis_ready
from app.db.session import is_database_ready
from app.schemas.health import ReadinessResponse
from app.storage.readiness import is_storage_ready


def get_application_readiness() -> ReadinessResponse:
    database_ready = is_database_ready()
    redis_ready = is_redis_ready()
    storage_ready = is_storage_ready()
    application_ready = database_ready and redis_ready and storage_ready

    return ReadinessResponse(
        status="ready" if application_ready else "not_ready",
        database="ok" if database_ready else "unavailable",
        redis="ok" if redis_ready else "unavailable",
        storage="ok" if storage_ready else "unavailable",
    )
