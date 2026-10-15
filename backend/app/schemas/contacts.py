"""Schemas Pydantic para clientes (contactos de WhatsApp) del panel."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_TAGS = 10


def _normalize_tags(value: list[str] | None) -> list[str] | None:
    """Etiquetas limpias: sin vacíos ni repetidas, máx 10, 30 chars cada una."""
    if value is None:
        return None
    seen: dict[str, None] = {}
    for raw in value:
        tag = raw.strip()[:30].lower()
        if tag:
            seen.setdefault(tag, None)
    return list(seen)[:MAX_TAGS]


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
    tags: list[str] = []
    email: str | None = None
    address: str | None = None

    # Contactos previos al CRM tienen tags NULL en la BD → lista vacía
    _tags_coerce = field_validator("tags", mode="before")(lambda v: v or [])


class ContactPage(BaseModel):
    items: list[ContactOut]
    total: int
    skip: int
    limit: int


class ContactDetail(ContactOut):
    recent_messages: list[ContactMessage] = []


class ContactMessagesPage(BaseModel):
    """Historial paginado del cliente (más reciente primero)."""

    items: list[ContactMessage]
    total: int
    skip: int
    limit: int


class ContactUpdate(BaseModel):
    """Campos editables del cliente desde el panel (mini CRM incluido)."""

    name: str | None = Field(None, min_length=1, max_length=100)
    notes: str | None = Field(None, max_length=2000)
    is_active: bool | None = None
    tags: list[str] | None = None
    email: str | None = Field(None, max_length=120)
    address: str | None = Field(None, max_length=300)

    _tags_norm = field_validator("tags")(lambda v: _normalize_tags(v))


class ContactNoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class ContactNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content: str
    created_at: datetime


class ContactQuoteOut(BaseModel):
    """Cotización del cliente para el historial de su ficha."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    total: int
    created_at: datetime
