from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class EventOut(BaseModel):
    id: UUID
    tenant_id: UUID
    type: str
    created_at: datetime
    data: dict[str, Any]  # = event.payload
