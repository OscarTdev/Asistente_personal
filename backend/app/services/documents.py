"""Consecutivos de documentos y snapshot inmutable (spec §10).

Cada negocio tiene su propio consecutivo por tipo: COT-0001 para
cotizaciones, CC-0001 para cuentas de cobro. El bloqueo de fila
(SELECT FOR UPDATE) garantiza que dos cotizaciones simultáneas jamás
comparten número.

El documento guarda un snapshot de los datos con los que se generó:
si el negocio cambia su nombre, NIT o logo, los PDFs ya emitidos
conservan sus datos originales.
"""

import logging
from decimal import Decimal
from uuid import UUID

from num2words import num2words
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentCounter, TenantBranding

logger = logging.getLogger(__name__)

_DOC_PREFIX = {"quote": "COT", "invoice": "CC", "visit_report": "IV"}


async def next_document_number(
    db: AsyncSession, *, tenant_id: UUID, doc_type: str
) -> str:
    """Consecutivo por negocio y tipo con bloqueo de fila.

    SELECT ... FOR UPDATE evita que dos requests concurrentes saquen
    el mismo número.
    """
    row = (
        await db.execute(
            select(DocumentCounter)
            .where(
                DocumentCounter.tenant_id == tenant_id,
                DocumentCounter.doc_type == doc_type,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()

    if row is None:
        row = DocumentCounter(
            tenant_id=tenant_id, doc_type=doc_type, last_number=0
        )
        db.add(row)
        await db.flush()

    row.last_number += 1
    await db.flush()

    prefix = _DOC_PREFIX.get(doc_type, "DOC")
    return f"{prefix}-{row.last_number:04d}"


def total_in_letters(amount: Decimal | float | int) -> str:
    """Total en letras para documentos colombianos.

    $1.250.000 → «Un millón doscientos cincuenta mil pesos»
    [VERIFICAR] entonación exacta para es_CO en contextos legales.
    """
    value = int(amount)
    words = num2words(value, lang="es_CO")
    # Capitalizar la primera letra
    words = words[0].upper() + words[1:]
    return f"{words} pesos"


async def create_document(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    doc_type: str,
    snapshot: dict,
    quote_id: UUID | None = None,
) -> Document:
    """Crea un documento con consecutivo e inmutabilidad del snapshot."""
    number = await next_document_number(db, tenant_id=tenant_id, doc_type=doc_type)
    document = Document(
        tenant_id=tenant_id,
        doc_type=doc_type,
        number=number,
        status="draft",
        snapshot=snapshot,
        quote_id=quote_id,
    )
    db.add(document)
    await db.flush()
    logger.info("Documento %s creado para tenant %s", number, tenant_id)
    return document


async def get_branding(
    db: AsyncSession, *, tenant_id: UUID
) -> TenantBranding | None:
    """Branding del negocio (pie de página, color, datos bancarios)."""
    return (
        await db.execute(
            select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
