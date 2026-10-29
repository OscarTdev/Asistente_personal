from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ActiveBotUser(BaseModel):
    contact_id: UUID
    name: str
    wa_id: str
    last_activity_at: datetime
    last_direction: str
    messages: int


class RealtimeActivity(BaseModel):
    window_minutes: int
    active_now: int
    messages_in_window: int
    last_activity_at: datetime | None
    users: list[ActiveBotUser]
