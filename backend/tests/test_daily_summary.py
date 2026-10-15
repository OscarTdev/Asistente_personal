"""Tests del resumen diario proactivo (el módulo que hace volver al usuario)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact, Quote, Reminder, Tenant


@pytest.fixture
def owner_headers(admin_user) -> dict[str, str]:
    from app.core.security import create_access_token

    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_daily_summary_lists_todays_reminders(
    db_session: AsyncSession, tenant: Tenant, admin_user
):
    """El resumen de hoy incluye los recordatorios de hoy."""
    from app.services.daily_summary import generate_daily_summary

    now = datetime.now(UTC)
    db_session.add(
        Reminder(
            tenant_id=tenant.id,
            content="Llamar a Juliana de Laureles",
            remind_at=now.replace(hour=14, minute=0, second=0, microsecond=0),
        )
    )
    await db_session.commit()

    text = await generate_daily_summary(db_session, tenant=tenant)
    assert "Llamar a Juliana" in text
    assert "Hoy tienes" in text


@pytest.mark.asyncio
async def test_daily_summary_lists_pending_quotes(
    db_session: AsyncSession, tenant: Tenant
):
    """El resumen muestra las cotizaciones enviadas sin respuesta."""
    from app.services.daily_summary import generate_daily_summary

    contact = Contact(tenant_id=tenant.id, wa_id="573001112233", name="María")
    db_session.add(contact)
    await db_session.flush()

    db_session.add(
        Quote(
            tenant_id=tenant.id,
            contact_id=contact.id,
            status="sent",
            total=45000,
            created_at=datetime.now(UTC) - timedelta(days=3),
        )
    )
    await db_session.commit()

    text = await generate_daily_summary(db_session, tenant=tenant)
    assert "cotizaciones esperan" in text
    assert "45,000" in text
    assert "María" in text


@pytest.mark.asyncio
async def test_daily_summary_empty_day(
    db_session: AsyncSession, tenant: Tenant
):
    """Día tranquilo: mensaje positivo, no una lista vacía."""
    from app.services.daily_summary import generate_daily_summary

    text = await generate_daily_summary(db_session, tenant=tenant)
    assert "nada pendiente" in text


@pytest.mark.asyncio
async def test_daily_summary_marks_overdue_reminders(
    db_session: AsyncSession, tenant: Tenant
):
    """Los recordatorios de días anteriores aparecen como pendientes."""
    from app.services.daily_summary import generate_daily_summary

    db_session.add(
        Reminder(
            tenant_id=tenant.id,
            content="Comprar breakers (olvidado ayer)",
            remind_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    await db_session.commit()

    text = await generate_daily_summary(db_session, tenant=tenant)
    assert "pendientes de días anteriores" in text
