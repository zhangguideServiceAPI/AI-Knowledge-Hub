from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.storage.factory import (
    get_minio_readiness_client,
    get_storage_bucket,
)


def is_storage_ready() -> bool:
    if settings.STORAGE_PROVIDER == "local":
        return True

    try:
        get_minio_readiness_client().head_bucket(
            Bucket=get_storage_bucket(),
        )
    except (BotoCoreError, ClientError):
        return False

    return True
