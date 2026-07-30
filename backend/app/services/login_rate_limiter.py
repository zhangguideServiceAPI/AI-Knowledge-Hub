from hashlib import sha256

from redis import Redis


class LoginRateLimiter:
    def __init__(self, client: Redis, window_seconds: int, max_attempts: int) -> None:
        self._client = client
        self._window_seconds = window_seconds
        self._max_attempts = max_attempts

    def reserve_attempt(self, identifier: str) -> bool:
        key = self._build_key(identifier)

        # 每个并发请求先原子递增，再根据自己获得的计数决定是否准入。
        pipeline = self._client.pipeline(transaction=True)
        pipeline.incr(key)
        pipeline.expire(key, self._window_seconds, nx=True)

        result = pipeline.execute()
        attempts = int(result[0])

        return attempts <= self._max_attempts

    def reset(self, identifier: str) -> None:
        self._client.delete(self._build_key(identifier))

    @staticmethod
    def _build_key(identifier: str) -> str:
        normalized_identifier = identifier.strip().lower()
        identifier_hash = sha256(normalized_identifier.encode("utf-8")).hexdigest()

        return f"auth:login:failures:{identifier_hash}"
