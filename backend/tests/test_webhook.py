"""Webhook idempotente: tests de integración (Review Focus 1, 2, 3 y 5 del plan)."""

from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models import Event, Message, Tenant


@pytest.fixture
def webhook_payload() -> dict:
    """Payload estilo Evolution API (ejemplo del plan, sección C)."""
    return {
        "event": "messages.upsert",
        "instance": "auratest",
        "data": {
            "key": {
                "id": "3EB0F9B1B5D6C7D8",
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
            },
            "pushName": "Juan Pérez",
            "messageType": "conversation",
            "message": {
                "conversation": "Hola, necesito una cotización para un tablero",
            },
            "status": "RECEIVED",
        },
    }


@pytest.mark.asyncio
async def test_webhook_idempotency(
    client: AsyncClient, tenant: Tenant, db_session, webhook_payload: dict
):
    """Dos POST idénticos → ambos 200; UNA fila en messages y UNA en events."""
    headers = {"X-Tenant-Slug": tenant.slug}

    response1 = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response1.status_code == HTTPStatus.OK
    data1 = response1.json()
    assert data1["status"] == "ok"
    assert data1["whatsapp_message_id"] == "3EB0F9B1B5D6C7D8"
    assert data1["duplicate"] is False

    response2 = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response2.status_code == HTTPStatus.OK
    data2 = response2.json()
    assert data2["status"] == "ok"
    assert data2["whatsapp_message_id"] == "3EB0F9B1B5D6C7D8"
    assert data2["duplicate"] is True

    message_count = (
        await db_session.execute(
            select(func.count()).select_from(Message).where(Message.tenant_id == tenant.id)
        )
    ).scalar()
    assert message_count == 1

    event_count = (
        await db_session.execute(
            select(func.count()).select_from(Event).where(Event.tenant_id == tenant.id)
        )
    ).scalar()
    assert event_count == 1


@pytest.mark.asyncio
async def test_webhook_unknown_tenant(client: AsyncClient, webhook_payload: dict):
    """Slug desconocido → 404 sin filtrar información."""
    headers = {"X-Tenant-Slug": "nope"}

    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["detail"] == "Tenant no encontrado"


@pytest.mark.asyncio
async def test_webhook_invalid_payload(
    client: AsyncClient, tenant: Tenant, webhook_payload: dict
):
    """Sin data.key.id → 400 sin crash."""
    webhook_payload["data"]["key"].pop("id")
    headers = {"X-Tenant-Slug": tenant.slug}

    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"] == "Payload de webhook inválido"


@pytest.mark.asyncio
async def test_webhook_payload_without_text(
    client: AsyncClient, tenant: Tenant, webhook_payload: dict
):
    """Mensaje sin texto extraíble (audio) → 400 sin crash."""
    webhook_payload["data"]["message"] = {
        "audioMessage": {"url": "https://example.com/audio.ogg"}
    }
    webhook_payload["data"]["messageType"] = "audioMessage"
    headers = {"X-Tenant-Slug": tenant.slug}

    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"] == "Payload de webhook inválido"


@pytest.mark.asyncio
async def test_webhook_redis_down(
    client: AsyncClient,
    tenant: Tenant,
    db_session,
    webhook_payload: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Redis caído → el POST sigue 200 y el mensaje queda persistido."""
    async def mock_publish_event(*args, **kwargs):
        raise RuntimeError("Redis is down")

    monkeypatch.setattr("app.api.v1.webhooks.publish_event", mock_publish_event)

    headers = {"X-Tenant-Slug": tenant.slug}
    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["status"] == "ok"
    assert data["duplicate"] is False

    message = (
        await db_session.execute(
            select(Message).where(Message.tenant_id == tenant.id)
        )
    ).scalar_one_or_none()
    assert message is not None
    assert message.whatsapp_message_id == "3EB0F9B1B5D6C7D8"


@pytest.mark.asyncio
async def test_webhook_inactive_tenant(
    client: AsyncClient, tenant: Tenant, db_session, webhook_payload: dict
):
    """Tenant inactivo → 404 igual que slug desconocido."""
    tenant.is_active = False
    await db_session.commit()

    headers = {"X-Tenant-Slug": tenant.slug}
    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["detail"] == "Tenant no encontrado"


@pytest.mark.asyncio
async def test_webhook_event_payload_message_id(
    client: AsyncClient, tenant: Tenant, db_session, webhook_payload: dict
):
    """El evento persistido en BD lleva el id del mensaje (no None).

    Regresión: mutar event.payload in place no dispara UPDATE en JSONB
    sin MutableDict → la BD guardaba message_id=None.
    """
    headers = {"X-Tenant-Slug": tenant.slug}
    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.OK

    event = (
        await db_session.execute(select(Event).where(Event.tenant_id == tenant.id))
    ).scalar_one()
    await db_session.refresh(event)  # relectura desde la BD (no el estado en memoria)
    assert event.payload["message_id"] is not None
