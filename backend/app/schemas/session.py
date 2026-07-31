from datetime import datetime

from pydantic import BaseModel


class UserSessionResponse(BaseModel):
    id: str
    current: bool
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime


class UserSessionListResponse(BaseModel):
    sessions: list[UserSessionResponse]
