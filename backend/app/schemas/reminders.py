"""Schemas Pydantic para la agenda de recordatorios del panel."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ReminderStatus = Literal["pending", "sent", "done", "cancelled"]


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content: str
    remind_at: datetime
    status: str
    sent_at: datetime | None
    created_at: datetime


class ReminderCreate(BaseModel):
    """Programar desde el panel: igual que por chat, con fecha ISO."""

    content: str = Field(min_length=1, max_length=500)
    remind_at: datetime


class ReminderStatusUpdate(BaseModel):
    """Cierre manual desde el panel: el dueño lo hizo o lo cancela."""

    status: Literal["done", "cancelled"]
