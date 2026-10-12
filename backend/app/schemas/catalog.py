"""Schemas Pydantic para el catálogo de precios."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CatalogItemCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: str | None = None
    unit: str | None = Field(None, max_length=50)
    unit_price: Decimal = Field(..., ge=0, decimal_places=2)
    is_active: bool = True


class CatalogItemUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = None
    unit: str | None = Field(None, max_length=50)
    unit_price: Decimal | None = Field(None, ge=0, decimal_places=2)
    is_active: bool | None = None


class CatalogItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    unit: str | None
    unit_price: Decimal
    is_active: bool


class CatalogPage(BaseModel):
    items: list[CatalogItemOut]
    total: int
    skip: int
    limit: int


class CatalogImportResult(BaseModel):
    created: int
    updated: int
    errors: list[str]
