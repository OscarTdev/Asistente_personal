"""Servicio CRUD para el catálogo de precios.

Principios:
- Aislamiento por tenant_id en toda operación.
- Soft-delete: is_active = False (nunca borrado físico).
- Import CSV: upsert por (tenant_id, name) con csv del stdlib.
"""

import csv
import io
import logging
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem
from app.schemas.catalog import (
    CatalogImportResult,
    CatalogItemCreate,
    CatalogItemUpdate,
    CatalogPage,
)

logger = logging.getLogger(__name__)


async def list_catalog(
    db: AsyncSession,
    tenant_id: UUID,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    active_only: bool = True,
) -> CatalogPage:
    """Lista ítems del catálogo con paginación y búsqueda opcional por nombre."""
    base = select(CatalogItem).where(CatalogItem.tenant_id == tenant_id)
    if active_only:
        base = base.where(CatalogItem.is_active.is_(True))
    if search:
        base = base.where(CatalogItem.name.ilike(f"%{search}%"))

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    items_stmt = base.order_by(CatalogItem.name).offset(skip).limit(limit)
    items = (await db.execute(items_stmt)).scalars().all()

    return CatalogPage(items=list(items), total=total, skip=skip, limit=limit)


async def get_catalog_item(
    db: AsyncSession, tenant_id: UUID, item_id: UUID
) -> CatalogItem | None:
    """Obtiene un ítem por id verificando el tenant."""
    result = await db.execute(
        select(CatalogItem)
        .where(CatalogItem.id == item_id)
        .where(CatalogItem.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def create_catalog_item(
    db: AsyncSession, tenant_id: UUID, data: CatalogItemCreate
) -> CatalogItem:
    """Crea un nuevo ítem en el catálogo."""
    item = CatalogItem(
        tenant_id=tenant_id,
        name=data.name,
        description=data.description,
        unit=data.unit,
        unit_price=data.unit_price,
        is_active=data.is_active,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def update_catalog_item(
    db: AsyncSession, item: CatalogItem, data: CatalogItemUpdate
) -> CatalogItem:
    """Actualiza los campos presentes en el payload."""
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return item


async def deactivate_catalog_item(db: AsyncSession, item: CatalogItem) -> CatalogItem:
    """Soft-delete: marca el ítem como inactivo."""
    item.is_active = False
    await db.commit()
    await db.refresh(item)
    return item


async def import_catalog_csv(
    db: AsyncSession, tenant_id: UUID, csv_bytes: bytes
) -> CatalogImportResult:
    """Carga masiva desde CSV (upsert por nombre dentro del tenant).

    Columnas esperadas: nombre,descripcion,unidad,precio_unitario
    La primera fila puede ser encabezado (se detecta si 'nombre' o 'name' está presente).
    """
    text = csv_bytes.decode("utf-8-sig")  # utf-8-sig quita BOM de Excel
    reader = csv.DictReader(io.StringIO(text))

    # Normalizar nombres de columna a minúsculas sin espacios
    def _norm(s: str) -> str:
        return s.strip().lower().replace(" ", "_")

    created = 0
    updated = 0
    errors: list[str] = []

    for row_num, raw_row in enumerate(reader, start=2):
        row = {_norm(k): v.strip() for k, v in raw_row.items() if k}

        name = row.get("nombre") or row.get("name", "")
        if not name:
            errors.append(f"Fila {row_num}: nombre vacío, omitida")
            continue

        price_str = row.get("precio_unitario") or row.get("unit_price") or row.get("precio") or ""
        try:
            unit_price = Decimal(price_str.replace(",", "."))
            if unit_price < 0:
                raise ValueError("precio negativo")
        except (InvalidOperation, ValueError):
            errors.append(f"Fila {row_num}: precio inválido '{price_str}', omitida")
            continue

        description = row.get("descripcion") or row.get("description") or None
        unit = row.get("unidad") or row.get("unit") or None

        # Upsert por (tenant_id, name)
        result = await db.execute(
            select(CatalogItem)
            .where(CatalogItem.tenant_id == tenant_id)
            .where(CatalogItem.name == name)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.unit_price = unit_price
            existing.description = description if description else existing.description
            existing.unit = unit if unit else existing.unit
            existing.is_active = True
            updated += 1
        else:
            db.add(CatalogItem(
                tenant_id=tenant_id,
                name=name,
                description=description,
                unit=unit,
                unit_price=unit_price,
                is_active=True,
            ))
            created += 1

    await db.commit()
    logger.info(
        "CSV import tenant %s: %d creados, %d actualizados, %d errores",
        tenant_id, created, updated, len(errors),
    )
    return CatalogImportResult(created=created, updated=updated, errors=errors)
