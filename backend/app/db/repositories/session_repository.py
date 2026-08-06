from dataclasses import dataclass
from enum import Enum

from redis import Redis


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    user_id: int
    refresh_token_hash: str
    created_at: int
    last_used_at: int
    expires_at: int
    absolute_expires_at: int


# expected_refresh_token_hash：客户端提交的旧 Token Hash，必须和 Redis 当前值相同。
# new_refresh_token_hash：Rotation 成功后写入的新值。
# rotated_at：这次轮换发生的 Unix 秒。
# expires_at：轮换后的 Session 到期时间。
# ttl_seconds：Redis 从现在起还应保留多少秒。
# jti 不单独存入 Redis；新 jti 会改变整个 Refresh JWT，因此最终 Hash 也会变化。
@dataclass(frozen=True)
class SessionRotation:
    session_id: str
    user_id: int
    expected_refresh_token_hash: str
    new_refresh_token_hash: str
    rotated_at: int
    expires_at: int
    ttl_seconds: int


class SessionRotationResult(Enum):
    SUCCESS = "success"
    SESSION_NOT_FOUND = "session_not_found"
    TOKEN_MISMATCH = "token_mismatch"


# Lua 脚本在 Redis 内一次完成旧 Hash 比较和新状态写入。
_ROTATE_SESSION_SCRIPT = """
local current_hash = redis.call("HGET", KEYS[1], "refresh_token_hash")

if not current_hash then
    return 0
end

if current_hash ~= ARGV[1] then
    redis.call("DEL", KEYS[1])
    redis.call("ZREM", KEYS[2], ARGV[6])
    return -1
end

redis.call(
    "HSET",
    KEYS[1],
    "refresh_token_hash", ARGV[2],
    "last_used_at", ARGV[3],
    "expires_at", ARGV[4]
)
redis.call("EXPIRE", KEYS[1], ARGV[5])
redis.call("ZADD", KEYS[2], ARGV[3], ARGV[6])

return 1
"""
# 1. 读取 Session 当前保存的 Refresh Hash
# 2. Hash 不存在：Session 不存在，返回 0
# 3. 旧 Hash 不匹配：删除当前 Session 和索引，返回 -1
# 4. 写入新 Refresh Hash
# 5. 更新 last_used_at
# 6. 更新当前 expires_at
# 7. 用剩余秒数重新对齐 Redis TTL
# 8. 更新这个 Session 在用户 Sorted Set 中的最近使用时间
# 9. 返回 1


def _session_record_from_hash(
    session_id: str,
    data: dict[str, str],
) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        user_id=int(data["user_id"]),
        refresh_token_hash=data["refresh_token_hash"],
        created_at=int(data["created_at"]),
        last_used_at=int(data["last_used_at"]),
        expires_at=int(data["expires_at"]),
        absolute_expires_at=int(data["absolute_expires_at"]),
    )


class SessionRepository:
    def __init__(self, client: Redis) -> None:
        self._client = client

    def create(
        self,
        session: SessionRecord,
        ttl_seconds: int,
    ) -> None:
        key = f"auth:session:{session.session_id}"
        index_key = f"auth:user:{session.user_id}:sessions"

        pipeline = self._client.pipeline(transaction=True)
        pipeline.hset(
            key,
            mapping={
                "user_id": str(session.user_id),
                "refresh_token_hash": session.refresh_token_hash,
                "created_at": str(session.created_at),
                "last_used_at": str(session.last_used_at),
                "expires_at": str(session.expires_at),
                "absolute_expires_at": str(session.absolute_expires_at),
            },
        )
        pipeline.expire(key, ttl_seconds)
        pipeline.zadd(
            index_key,
            {session.session_id: session.last_used_at},
        )
        pipeline.execute()

    def get(self, session_id: str) -> SessionRecord | None:
        key = f"auth:session:{session_id}"
        data = self._client.hgetall(key)

        if not data:
            return None

        return _session_record_from_hash(
            session_id,
            data,
        )

    def rotate(
        self,
        rotation: SessionRotation,
    ) -> SessionRotationResult:
        key = f"auth:session:{rotation.session_id}"
        index_key = f"auth:user:{rotation.user_id}:sessions"

        # 数字 2 表示后面的前两个参数属于 KEYS，其余参数属于 ARGV。
        result = self._client.eval(
            _ROTATE_SESSION_SCRIPT,
            2,
            key,
            index_key,
            rotation.expected_refresh_token_hash,
            rotation.new_refresh_token_hash,
            rotation.rotated_at,
            rotation.expires_at,
            rotation.ttl_seconds,
            rotation.session_id,
        )

        if result == 1:
            return SessionRotationResult.SUCCESS

        if result == 0:
            return SessionRotationResult.SESSION_NOT_FOUND

        if result == -1:
            return SessionRotationResult.TOKEN_MISMATCH

        raise ValueError(f"Unexpected session rotation result: {result}")

    def delete(self, user_id: int, session_id: str) -> None:
        key = f"auth:session:{session_id}"
        index_key = f"auth:user:{user_id}:sessions"
        pipeline = self._client.pipeline(transaction=True)
        pipeline.delete(key)
        pipeline.zrem(
            index_key,
            session_id,
        )

        pipeline.execute()

    def list_for_user(self, user_id: int) -> list[SessionRecord]:
        index_key = f"auth:user:{user_id}:sessions"
        session_ids = self._client.zrevrange(index_key, 0, -1)

        if not session_ids:
            return []

        pipeline = self._client.pipeline(transaction=False)
        for session_id in session_ids:
            key = f"auth:session:{session_id}"
            pipeline.hgetall(key)

        session_hashes = pipeline.execute()

        sessions: list[SessionRecord] = []
        stale_session_ids: list[str] = []

        for session_id, data in zip(
            session_ids,
            session_hashes,
            strict=True,
        ):
            if not data:
                stale_session_ids.append(session_id)
                continue

            sessions.append(
                _session_record_from_hash(
                    session_id,
                    data,
                )
            )

        if stale_session_ids:
            self._client.zrem(index_key, *stale_session_ids)

        return sessions
