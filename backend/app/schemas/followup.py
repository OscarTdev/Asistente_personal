"""Schemas del servicio de seguimiento de cotizaciones."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class FollowUpPendingItem(BaseModel):
    """Cotización enviada y su estado de seguimiento."""

    quote_id: UUID
    contact_name: str | None
    contact_wa_id: str
    total: str
    sent_at: datetime
    days_elapsed: int
    round1_sent_at: datetime | None = None
    round2_sent_at: datetime | None = None
    replied: bool


class FollowUpPendingPage(BaseModel):
    items: list[FollowUpPendingItem]
    total: int


class FollowUpRunResult(BaseModel):
    round1_sent: int
    round2_sent: int
    errors: int
