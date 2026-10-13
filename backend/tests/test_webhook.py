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
    client: AsyncClient,
    tenant: Tenant,
    db_session,
    webhook_payload: dict,
    webhook_headers: dict,
):
    """Dos POST idénticos → ambos 200; UNA fila en messages y UNA en events."""
    headers = {"X-Tenant-Slug": tenant.slug, **webhook_headers}

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
            select(func.count())
            .select_from(Message)
            .where(Message.tenant_id == tenant.id)
            .where(Message.direction == "in")
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
async def test_webhook_unknown_tenant(
    client: AsyncClient, webhook_payload: dict, webhook_headers: dict
):
    """Slug desconocido → 404 sin filtrar información."""
    headers = {"X-Tenant-Slug": "nope", **webhook_headers}

    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["detail"] == "Tenant no encontrado"


@pytest.mark.asyncio
async def test_webhook_invalid_payload(
    client: AsyncClient,
    tenant: Tenant,
    webhook_payload: dict,
    webhook_headers: dict,
):
    """Sin data.key.id → 400 sin crash."""
    webhook_payload["data"]["key"].pop("id")
    headers = {"X-Tenant-Slug": tenant.slug, **webhook_headers}

    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"] == "Payload de webhook inválido"


@pytest.mark.asyncio
async def test_webhook_payload_without_text(
    client: AsyncClient,
    tenant: Tenant,
    db_session,
    webhook_payload: dict,
    webhook_headers: dict,
):
    """Fase B: mensaje de audio → 200 aceptado y persistido como audio."""
    webhook_payload["data"]["message"] = {
        "audioMessage": {"url": "https://example.com/audio.ogg"}
    }
    webhook_payload["data"]["messageType"] = "audioMessage"
    headers = {"X-Tenant-Slug": tenant.slug, **webhook_headers}

    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == "ok"

    # El mensaje quedó persistido como audio (los precios no se procesan aquí)
    from sqlalchemy import select

    from app.models import Message

    rows = (
        await db_session.execute(select(Message).where(Message.type == "audio"))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].direction == "in"


@pytest.mark.asyncio
async def test_webhook_redis_down(
    client: AsyncClient,
    tenant: Tenant,
    db_session,
    webhook_payload: dict,
    webhook_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Redis caído → el POST sigue 200 y el mensaje queda persistido."""
    async def mock_publish_event(*args, **kwargs):
        raise RuntimeError("Redis is down")

    monkeypatch.setattr("app.api.v1.webhooks.publish_event", mock_publish_event)

    headers = {"X-Tenant-Slug": tenant.slug, **webhook_headers}
    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["status"] == "ok"
    assert data["duplicate"] is False

    message = (
        await db_session.execute(
            select(Message)
            .where(Message.tenant_id == tenant.id)
            .where(Message.direction == "in")
        )
    ).scalar_one_or_none()
    assert message is not None
    assert message.whatsapp_message_id == "3EB0F9B1B5D6C7D8"


@pytest.mark.asyncio
async def test_webhook_inactive_tenant(
    client: AsyncClient,
    tenant: Tenant,
    db_session,
    webhook_payload: dict,
    webhook_headers: dict,
):
    """Tenant inactivo → 404 igual que slug desconocido."""
    tenant.is_active = False
    await db_session.commit()

    headers = {"X-Tenant-Slug": tenant.slug, **webhook_headers}
    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["detail"] == "Tenant no encontrado"


@pytest.mark.asyncio
async def test_webhook_event_payload_message_id(
    client: AsyncClient,
    tenant: Tenant,
    db_session,
    webhook_payload: dict,
    webhook_headers: dict,
):
    """El evento persistido en BD lleva el id del mensaje (no None).

    Regresión: mutar event.payload in place no dispara UPDATE en JSONB
    sin MutableDict → la BD guardaba message_id=None.
    """
    headers = {"X-Tenant-Slug": tenant.slug, **webhook_headers}
    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.OK

    event = (
        await db_session.execute(select(Event).where(Event.tenant_id == tenant.id))
    ).scalar_one()
    await db_session.refresh(event)  # relectura desde la BD (no el estado en memoria)
    assert event.payload["message_id"] is not None


# ── Autenticación del webhook (fail-closed) ─────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_rejects_missing_secret(
    client: AsyncClient, tenant: Tenant, webhook_payload: dict, webhook_headers: dict
):
    """Sin la cabecera X-Webhook-Secret → 401: la puerta no abre."""
    headers = {"X-Tenant-Slug": tenant.slug}  # sin secreto
    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_webhook_rejects_wrong_secret(
    client: AsyncClient, tenant: Tenant, webhook_payload: dict, webhook_headers: dict
):
    """Secreto incorrecto → 401 (comparación de tiempo constante)."""
    headers = {
        "X-Tenant-Slug": tenant.slug,
        "X-Webhook-Secret": "secreto-equivocado",
    }
    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_webhook_rejects_when_secret_unconfigured(
    client: AsyncClient,
    tenant: Tenant,
    webhook_payload: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Sin WEBHOOK_SECRET en el servidor también es 401: no hay modo abierto."""
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.api.deps.get_settings",
        lambda: SimpleNamespace(webhook_secret=""),
    )
    headers = {"X-Tenant-Slug": tenant.slug, "X-Webhook-Secret": "cualquiera"}
    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ── Auto-chat del dueño (el bot corre en su propio número) ──────────────────


@pytest.mark.asyncio
async def test_webhook_self_chat_of_registered_owner(
    client: AsyncClient,
    tenant: Tenant,
    db_session,
    webhook_payload: dict,
    webhook_headers: dict,
):
    """fromMe + remoteJid = su propio número = el dueño hablándole al bot."""
    tenant.wa_id = "573001234567"  # el mismo número que trae el payload
    await db_session.commit()
    webhook_payload["data"]["key"]["fromMe"] = True

    headers = {"X-Tenant-Slug": tenant.slug, **webhook_headers}
    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == "ok"

    message = (
        await db_session.execute(
            select(Message).where(Message.direction == "in")
        )
    ).scalars().one()
    assert message.whatsapp_message_id == "3EB0F9B1B5D6C7D8"


@pytest.mark.asyncio
async def test_webhook_owner_manual_reply_ignored(
    client: AsyncClient,
    tenant: Tenant,
    db_session,
    webhook_payload: dict,
    webhook_headers: dict,
):
    """fromMe a un tercero (respuesta manual del dueño desde su teléfono) → ignorado."""
    webhook_payload["data"]["key"]["fromMe"] = True
    # remoteJid del payload (573001234567) NO es el número del dueño

    headers = {"X-Tenant-Slug": tenant.slug, **webhook_headers}
    response = await client.post(
        "/api/v1/webhooks/whatsapp", headers=headers, json=webhook_payload
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == "ignored"

    count = (
        await db_session.execute(
            select(func.count()).select_from(Message)
        )
    ).scalar_one()
    assert count == 0
