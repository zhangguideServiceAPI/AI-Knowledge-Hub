from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

from app.core.config import settings

REDIS_OPERATION_RETRIES = 0


def create_redis_client() -> Redis:
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD.get_secret_value(),
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
        retry=Retry(
            NoBackoff(),
            REDIS_OPERATION_RETRIES,
        ),
        decode_responses=True,
    )


redis_client = create_redis_client()


def is_redis_ready() -> bool:
    try:
        return bool(redis_client.ping())
    except RedisError:
        return False
