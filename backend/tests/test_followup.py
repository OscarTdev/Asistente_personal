"""Tests del motor de seguimiento de cotizaciones."""

import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.core.security import create_access_token
from app.models import Contact, Conversation, Message, Quote, TenantModule, User
from app.schemas.channel import IncomingMessage
from app.services.followup import run_followups


@pytest.fixture
def auth_headers(admin_user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    return {"Authorization": f"Bearer {token}"}


class FakeChannel(Channel):
    """Canal de prueba: registra los envíos en lugar de llamar a Evolution."""

    name = "fake"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def parse_incoming(self, payload):
        raise NotImplementedError

    async def send_text(self, to: str, text: str) -> None:
        self.sent.append((to, text))


async def _seed_quote(
    db_session: AsyncSession,
    tenant,
    *,
    days_ago: int,
    contact_name: str = "Cliente Prueba",
    with_reply: bool = False,
) -> tuple[Quote, Contact]:
    now = datetime.now(timezone.utc)
    contact = Contact(
        tenant_id=tenant.id,
        wa_id=f"57300{uuid.uuid4().hex[:8]}",
        name=contact_name,
    )
    db_session.add(contact)
    await db_session.flush()

    conversation = Conversation(
        tenant_id=tenant.id,
        contact_id=contact.id,
        status="open",
    )
    db_session.add(conversation)
    await db_session.flush()

    quote = Quote(
        tenant_id=tenant.id,
        contact_id=contact.id,
        conversation_id=conversation.id,
        status="sent",
        total=185000,
        created_at=now - timedelta(days=days_ago),
        updated_at=now - timedelta(days=days_ago),
    )
    db_session.add(quote)
    await db_session.flush()

    if with_reply:
        db_session.add(
            Message(
                tenant_id=tenant.id,
                conversation_id=conversation.id,
                direction="in",
                type="text",
                content="Sí, me interesa",
                whatsapp_message_id=f"wamid-fu-{uuid.uuid4().hex[:8]}",
                status="received",
                created_at=now - timedelta(days=days_ago - 1),
            )
        )

    await db_session.commit()
    await db_session.refresh(quote)
    await db_session.refresh(contact)
    return quote, contact


@pytest.fixture
def followup_enabled(db_session: AsyncSession, tenant):
    db_session.add(
        TenantModule(
            tenant_id=tenant.id,
            module_key="follow_up",
            name="Seguimiento",
            description="Seguimiento de cotizaciones",
            category="oficios",
            is_enabled=True,
            is_custom=False,
        )
    )


@pytest.mark.asyncio
async def test_round1_sent_at_day3(
    db_session: AsyncSession, tenant, followup_enabled
):
    """Cotización enviada hace 4 días sin respuesta → ronda 1 por WhatsApp."""
    quote, contact = await _seed_quote(db_session, tenant, days_ago=4)
    channel = FakeChannel()

    result = await run_followups(db_session, channel=channel)

    assert result.round1_sent == 1
    assert len(channel.sent) == 1
    to, message = channel.sent[0]
    assert to == contact.wa_id
    assert str(quote.id)[:8] in message


@pytest.mark.asyncio
async def test_no_duplicate_rounds(
    db_session: AsyncSession, tenant, followup_enabled
):
    """La segunda ejecución no vuelve a escribir la misma ronda."""
    await _seed_quote(db_session, tenant, days_ago=4)
    channel = FakeChannel()

    first = await run_followups(db_session, channel=channel)
    second = await run_followups(db_session, channel=channel)

    assert first.round1_sent == 1
    assert second.round1_sent == 0
    assert second.round2_sent == 0
    assert len(channel.sent) == 1


@pytest.mark.asyncio
async def test_replied_quote_is_skipped(
    db_session: AsyncSession, tenant, followup_enabled
):
    """Si el cliente respondió, no se le escribe seguimiento."""
    await _seed_quote(db_session, tenant, days_ago=4, with_reply=True)
    channel = FakeChannel()

    result = await run_followups(db_session, channel=channel)

    assert result.round1_sent == 0
    assert len(channel.sent) == 0


@pytest.mark.asyncio
async def test_round2_at_day7(
    db_session: AsyncSession, tenant, followup_enabled
):
    """Ronda 1 enviada hace 4 días y cotización con 8 días → ronda 2."""
    from app.models import FollowUp

    quote, contact = await _seed_quote(db_session, tenant, days_ago=8)
    now = datetime.now(timezone.utc)
    db_session.add(
        FollowUp(
            tenant_id=tenant.id,
            quote_id=quote.id,
            contact_id=contact.id,
            round=1,
            message_sent="ronda 1 previa",
            created_at=now - timedelta(days=4),
            updated_at=now - timedelta(days=4),
        )
    )
    await db_session.commit()
    channel = FakeChannel()

    result = await run_followups(db_session, channel=channel)

    assert result.round2_sent == 1
    assert len(channel.sent) == 1
    assert "sigue vigente" in channel.sent[0][1]


@pytest.mark.asyncio
async def test_disabled_service_is_skipped(
    db_session: AsyncSession, tenant
):
    """Sin el servicio encendido para el tenant, no se procesa nada."""
    await _seed_quote(db_session, tenant, days_ago=4)
    channel = FakeChannel()

    result = await run_followups(db_session, channel=channel)

    assert result.round1_sent == 0
    assert len(channel.sent) == 0


@pytest.mark.asyncio
async def test_pending_endpoint(
    client: AsyncClient, db_session: AsyncSession, tenant, followup_enabled, auth_headers
):
    """GET /followup/pending lista la cotización con sus días transcurridos."""
    quote, _ = await _seed_quote(db_session, tenant, days_ago=4)

    resp = await client.get("/api/v1/followup/pending", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["quote_id"] == str(quote.id)
    assert item["days_elapsed"] == 4
    assert item["round1_sent_at"] is None
    assert item["replied"] is False


@pytest.mark.asyncio
async def test_run_endpoint_requires_service(
    client: AsyncClient, db_session: AsyncSession, tenant, auth_headers
):
    """POST /followup/run con el servicio apagado → 400 con mensaje claro."""
    resp = await client.post("/api/v1/followup/run", headers=auth_headers)
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert "apagado" in resp.json()["detail"]
