"""Schemas Pydantic para clientes (contactos de WhatsApp) del panel."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContactMessage(BaseModel):
    """Mensaje reciente de la conversación del cliente."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    direction: str
    type: str
    content: str | None
    created_at: datetime


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wa_id: str
    name: str | None
    notes: str | None
    is_active: bool
    created_at: datetime
    last_interaction_at: datetime | None = None
    messages_count: int = 0
    interactions_count: int = 0


class ContactPage(BaseModel):
    items: list[ContactOut]
    total: int
    skip: int
    limit: int


class ContactDetail(ContactOut):
    recent_messages: list[ContactMessage] = []


class ContactUpdate(BaseModel):
    """Campos editables del cliente desde el panel."""

    name: str | None = Field(None, min_length=1, max_length=100)
    notes: str | None = Field(None, max_length=2000)
    is_active: bool | None = None
