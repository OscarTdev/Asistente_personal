"""Tests de las métricas del dashboard del panel."""

import uuid
from datetime import datetime, timezone
from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models import Contact, Conversation, Message, ServiceUsage, User


@pytest.fixture
def auth_headers(admin_user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_stats_empty_tenant(client: AsyncClient, auth_headers: dict[str, str]):
    """Tenant sin actividad: métricas en cero y servicios del registro."""
    resp = await client.get("/api/v1/dashboard/stats", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()
    assert data["bot_name"] == "Aura"
    assert data["contacts"]["total"] == 0
    assert data["contacts"]["active_last_7d"] == 0
    assert data["quotes"]["total"] == 0
    assert data["messages_last_7d"] == 0
    # Todos los servicios del registro aparecen con su estado de desarrollo
    keys = [s["key"] for s in data["services"]]
    assert "quoter" in keys
    from app.core.modules_registry import DEV_STATUS

    for service in data["services"]:
        expected = DEV_STATUS.get(service["key"], "development")
        assert service["dev_status"] == expected, f"{service['key']}: {service['dev_status']} != {expected}"
    assert all(s["interactions"] == 0 for s in data["services"])


@pytest.mark.asyncio
async def test_stats_count_activity_and_quote_logs_usage(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    tenant,
):
    """Actividad real alimenta las métricas; crear cotización registra uso."""
    now = datetime.now(timezone.utc)

    contact = Contact(tenant_id=tenant.id, wa_id="573005554443", name="Cliente Uno")
    db_session.add(contact)
    await db_session.flush()

    conversation = Conversation(
        tenant_id=tenant.id,
        contact_id=contact.id,
        status="open",
        last_message_at=now,
    )
    db_session.add(conversation)
    await db_session.flush()

    message = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction="in",
        type="text",
        content="me cotizas un tablero?",
        whatsapp_message_id="wamid-stats-1",
        status="received",
    )
    db_session.add(message)
    db_session.add(
        ServiceUsage(tenant_id=tenant.id, module_key="quoter", kind="extraction")
    )
    await db_session.commit()

    # Crear una cotización por la API → debe registrar el uso del servicio
    quote_payload = {
        "contact_id": str(contact.id),
        "items": [
            {"description": "Tablero metálico 8 circuitos", "quantity": 1, "unit_price": 89000}
        ],
    }
    resp = await client.post("/api/v1/quotes", json=quote_payload, headers=auth_headers)
    assert resp.status_code == HTTPStatus.CREATED

    resp = await client.get("/api/v1/dashboard/stats", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()

    assert data["contacts"]["total"] == 1
    assert data["contacts"]["active_last_7d"] == 1
    assert data["messages_last_7d"] == 1
    assert data["quotes"]["total"] == 1
    assert data["quotes"]["by_status"] == {"draft": 1}

    quoter = next(s for s in data["services"] if s["key"] == "quoter")
    # 1 extracción sembrada + 1 cotización creada vía API
    assert quoter["interactions"] == 2
    assert quoter["interactions_7d"] == 2


@pytest.mark.asyncio
async def test_usage_not_logged_on_failed_quote(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Una cotización inválida no registra interacción del servicio."""
    resp = await client.post(
        "/api/v1/quotes",
        json={"items": [{"description": "X", "quantity": 0, "unit_price": 100}]},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY  # quantity debe ser > 0

    resp = await client.get("/api/v1/dashboard/stats", headers=auth_headers)
    data = resp.json()
    quoter = next(s for s in data["services"] if s["key"] == "quoter")
    assert quoter["interactions"] == 0
