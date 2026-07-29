from hashlib import sha256

from redis import Redis


class LoginRateLimiter:
    def __init__(self, client: Redis, window_seconds: int, max_attempts: int) -> None:
        self._client = client
        self._window_seconds = window_seconds
        self._max_attempts = max_attempts

    def record_failure(self, identifier: str) -> int:
        key = self._build_key(identifier)

        pipeline = self._client.pipeline(transaction=True)
        pipeline.incr(key)
        pipeline.expire(key, self._window_seconds, nx=True)

        result = pipeline.execute()
        attempts = result[0]

        return int(attempts)

    def is_limited(self, identifier: str) -> bool:
        attempts = self._client.get(self._build_key(identifier))

        if attempts is None:
            return False

        return int(attempts) >= self._max_attempts

    def reset(self, identifier: str) -> None:
        self._client.delete(self._build_key(identifier))

    @staticmethod
    def _build_key(identifier: str) -> str:
        normalized_identifier = identifier.strip().lower()
        identifier_hash = sha256(normalized_identifier.encode("utf-8")).hexdigest()

        return f"auth:login:failures:{identifier_hash}"
