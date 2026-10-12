"""Schemas Pydantic para cotizaciones y sus ítems."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Quote items ──────────────────────────────────────────────────────────────

class QuoteItemCreate(BaseModel):
    catalog_item_id: UUID | None = None
    description: str = Field(..., max_length=200)
    quantity: Decimal = Field(..., gt=0, decimal_places=2)
    unit_price: Decimal = Field(..., ge=0, decimal_places=2)
    position: int = 0


class QuoteItemUpdate(BaseModel):
    description: str | None = Field(None, max_length=200)
    quantity: Decimal | None = Field(None, gt=0, decimal_places=2)
    unit_price: Decimal | None = Field(None, ge=0, decimal_places=2)
    position: int | None = None


class QuoteItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    quote_id: UUID
    catalog_item_id: UUID | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    position: int


# ── Quotes ───────────────────────────────────────────────────────────────────

QuoteStatus = Literal["draft", "sent", "accepted", "rejected", "expired"]


class QuoteCreate(BaseModel):
    contact_id: UUID | None = None
    conversation_id: UUID | None = None
    notes: str | None = None
    valid_until: datetime | None = None
    items: list[QuoteItemCreate] = []


class QuoteUpdate(BaseModel):
    status: QuoteStatus | None = None
    notes: str | None = None
    valid_until: datetime | None = None


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    contact_id: UUID | None
    conversation_id: UUID | None
    status: str
    total: Decimal
    notes: str | None
    valid_until: datetime | None
    created_at: datetime
    updated_at: datetime


class QuoteDetail(QuoteOut):
    items: list[QuoteItemOut] = []


class QuotePage(BaseModel):
    items: list[QuoteOut]
    total: int
    skip: int
    limit: int


# ── AI extraction ─────────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    conversation_id: UUID | None = None


class ExtractedItemSuggestion(BaseModel):
    description: str
    quantity: Decimal
    catalog_item_id: UUID | None = None
    catalog_name: str | None = None
    unit_price: Decimal | None = None
    unit: str | None = None
    matched: bool = False


class ExtractResponse(BaseModel):
    suggestions: list[ExtractedItemSuggestion]
    raw_extraction: list[dict]  # lo que la IA devolvió antes del matching
