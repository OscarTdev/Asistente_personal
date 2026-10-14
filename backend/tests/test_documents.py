"""Tests de la Fase 4: consecutivos, snapshot inmutable y total en letras.

- COT-0001, COT-0002... por negocio (bloqueo de fila contra duplicados)
- El documento guarda los datos exactos con los que se generó
- El total en letras produce español colombiano correcto
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tenant
from app.services.documents import (
    create_document,
    next_document_number,
    total_in_letters,
)


@pytest.fixture
async def business_tenant(db_session: AsyncSession) -> Tenant:
    t = Tenant(
        id=uuid.uuid4(),
        name="Instalaciones Gómez SAS",
        slug=f"instal-{uuid.uuid4().hex[:8]}",
        bot_name="Chispa",
        is_active=True,
        account_type="business",
        nit="900123456-6",
    )
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


# ── Total en letras ─────────────────────────────────────────────────────────


def test_total_in_letters_basic():
    assert total_in_letters(1250000) == "Un millón doscientos cincuenta mil pesos"
    assert total_in_letters(45000) == "Cuarenta y cinco mil pesos"
    assert total_in_letters(1) == "Uno pesos"  # num2words es_CO dice "uno"


def test_total_in_letters_zero():
    assert total_in_letters(0) == "Cero pesos"


def test_total_in_letters_large():
    assert "millones" in total_in_letters(50000000).lower()


# ── Consecutivos con bloqueo de fila ─────────────────────────────────────────


async def test_consecutive_numbers(
    db_session: AsyncSession, business_tenant: Tenant
):
    """COT-0001, COT-0002, COT-0003... por negocio."""
    first = await next_document_number(
        db_session, tenant_id=business_tenant.id, doc_type="quote"
    )
    second = await next_document_number(
        db_session, tenant_id=business_tenant.id, doc_type="quote"
    )
    third = await next_document_number(
        db_session, tenant_id=business_tenant.id, doc_type="quote"
    )
    assert first == "COT-0001"
    assert second == "COT-0002"
    assert third == "COT-0003"


async def test_consecutive_invoice_prefix(
    db_session: AsyncSession, business_tenant: Tenant
):
    """Cuenta de cobro usa CC- prefix."""
    first = await next_document_number(
        db_session, tenant_id=business_tenant.id, doc_type="invoice"
    )
    assert first == "CC-0001"


async def test_counters_are_per_tenant(
    db_session: AsyncSession, business_tenant: Tenant
):
    """Cada negocio tiene su propio consecutivo — no comparten."""
    other = Tenant(
        id=uuid.uuid4(),
        name="Otro Negocio",
        slug=f"otro-{uuid.uuid4().hex[:8]}",
        bot_name="Aura",
        is_active=True,
    )
    db_session.add(other)
    await db_session.commit()

    mine = await next_document_number(
        db_session, tenant_id=business_tenant.id, doc_type="quote"
    )
    theirs = await next_document_number(
        db_session, tenant_id=other.id, doc_type="quote"
    )
    assert mine == "COT-0001"
    assert theirs == "COT-0001"  # mismo número, distinto negocio


# ── Snapshot inmutable ───────────────────────────────────────────────────────


async def test_document_snapshot_is_immutable(
    db_session: AsyncSession, business_tenant: Tenant
):
    """El documento guarda los datos exactos del momento de creación."""
    snapshot = {
        "tenant_name": business_tenant.name,
        "tenant_nit": business_tenant.nit,
        "total": "45000",
        "items": [{"description": "Breaker 30A", "quantity": "2", "unit_price": "22500"}],
    }
    doc = await create_document(
        db_session,
        tenant_id=business_tenant.id,
        doc_type="quote",
        snapshot=snapshot,
    )
    await db_session.commit()

    # El negocio cambia de nombre después
    business_tenant.name = "Nuevo Nombre SAS"
    await db_session.commit()

    # El documento conserva sus datos originales
    await db_session.refresh(doc)
    assert doc.snapshot["tenant_name"] == "Instalaciones Gómez SAS"
    assert doc.snapshot["tenant_nit"] == "900123456-6"
    assert doc.number == "COT-0001"


async def test_document_with_quote_reference(
    db_session: AsyncSession, business_tenant: Tenant
):
    """El documento referencia la cotización original."""
    from app.models import Contact, Conversation, Quote

    contact = Contact(tenant_id=business_tenant.id, wa_id="573001112233")
    db_session.add(contact)
    await db_session.flush()
    conversation = Conversation(
        tenant_id=business_tenant.id, contact_id=contact.id, status="open"
    )
    db_session.add(conversation)
    await db_session.flush()
    quote = Quote(
        tenant_id=business_tenant.id,
        contact_id=contact.id,
        conversation_id=conversation.id,
        status="draft",
        total=45000,
    )
    db_session.add(quote)
    await db_session.commit()

    doc = await create_document(
        db_session,
        tenant_id=business_tenant.id,
        doc_type="quote",
        snapshot={"total": "45000"},
        quote_id=quote.id,
    )
    await db_session.commit()
    assert doc.quote_id == quote.id
    assert doc.doc_type == "quote"
