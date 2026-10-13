"""Tests del cerebro del bot: el flujo completo de cotización por WhatsApp.

Cubre la cadena crítica que no tenía pruebas: extracción → cotización →
PDF → envío → estado 'sent'. Con FakeChannel y extracción stubbeada.
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.models import Contact, Conversation, Message, Quote, Tenant, TenantModule
from app.schemas.quotes import ExtractedItemSuggestion, ExtractResponse
from app.services import orchestrator


class FakeChannel(Channel):
    """Canal de prueba: registra textos y documentos en lugar de llamar a Evolution."""

    name = "fake"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.docs: list[tuple[str, str, str, str]] = []

    async def parse_incoming(self, payload):
        raise NotImplementedError

    async def send_text(self, to: str, text: str) -> None:
        self.sent.append((to, text))

    async def send_document(
        self, to: str, file_name: str, content_base64: str, mimetype: str
    ) -> None:
        self.docs.append((to, file_name, content_base64, mimetype))


def _suggestion(
    *, description: str, matched: bool, price: Decimal | None
) -> ExtractedItemSuggestion:
    return ExtractedItemSuggestion(
        description=description,
        quantity=Decimal("3"),
        catalog_item_id=None,
        catalog_name=description if matched else None,
        unit_price=price,
        unit=None,
        matched=matched,
    )


@pytest.fixture
def bot_settings(monkeypatch: pytest.MonkeyPatch):
    """Settings del orquestador sin depender del .env real."""
    stub = SimpleNamespace(evolution_api_key="test-key")
    monkeypatch.setattr(
        "app.services.orchestrator.get_settings", lambda: stub
    )


@pytest.fixture
async def bot_chat(db_session: AsyncSession, tenant: Tenant) -> dict:
    """Quoter encendido + contacto + conversación + mensaje entrante."""
    db_session.add(
        TenantModule(
            tenant_id=tenant.id,
            module_key="quoter",
            name="Cotizador",
            description="",
            category="oficios",
            is_enabled=True,
        )
    )
    contact = Contact(
        tenant_id=tenant.id, wa_id="573001112233", name="Juliana"
    )
    db_session.add(contact)
    await db_session.flush()

    conversation = Conversation(
        tenant_id=tenant.id, contact_id=contact.id, status="open"
    )
    db_session.add(conversation)
    await db_session.flush()

    message = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction="in",
        type="text",
        content="Necesito 3 tomacorrientes dobles",
        whatsapp_message_id=f"in-{uuid.uuid4()}",
        status="received",
    )
    db_session.add(message)
    await db_session.commit()

    return {
        "contact": contact,
        "conversation": conversation,
        "message": message,
    }


async def _run_bot(
    db_session: AsyncSession,
    tenant: Tenant,
    chat: dict,
    channel: FakeChannel,
    suggestions: list[ExtractedItemSuggestion],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_extract(db, *, tenant_id, text):
        return ExtractResponse(suggestions=suggestions, raw_extraction=[])

    monkeypatch.setattr(
        orchestrator.ai_service, "extract_items_from_text", fake_extract
    )
    await orchestrator.handle_incoming(
        db_session,
        tenant=tenant,
        channel=channel,
        message=chat["message"],
        contact=chat["contact"],
        conversation=chat["conversation"],
    )


async def test_bot_quotes_and_marks_sent(
    db_session: AsyncSession,
    tenant: Tenant,
    bot_chat: dict,
    bot_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Flujo feliz: ítems con precio → cotización enviada y en estado 'sent'."""
    channel = FakeChannel()
    suggestions = [
        _suggestion(description="Tomacorriente doble", matched=True, price=Decimal("15000"))
    ]

    await _run_bot(db_session, tenant, bot_chat, channel, suggestions, monkeypatch)

    quote = (
        await db_session.execute(select(Quote))
    ).scalars().one()
    assert quote.total == 45000
    # A3: tras enviar el PDF, la cotización queda 'sent' (con fecha) para
    # que el seguimiento la cobre
    assert quote.status == "sent"
    assert quote.sent_at is not None

    # El cliente recibió el aviso y el PDF (C2: BytesIO → getvalue sin TypeError)
    assert len(channel.sent) == 1
    assert "cotización" in channel.sent[0][1].lower()
    assert len(channel.docs) == 1
    assert channel.docs[0][1].endswith(".pdf")


async def test_bot_never_quotes_unmatched_items(
    db_session: AsyncSession,
    tenant: Tenant,
    bot_chat: dict,
    bot_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """C3: ítem sin match en catálogo → sin cotización ni PDF; respuesta amable.

    La IA nunca inventa precios: un ítem a $0 no se le envía a un cliente.
    """
    channel = FakeChannel()
    suggestions = [
        _suggestion(description="Chapa eléctrica premium", matched=False, price=None)
    ]

    await _run_bot(db_session, tenant, bot_chat, channel, suggestions, monkeypatch)

    quotes = (
        await db_session.execute(select(Quote))
    ).scalars().all()
    assert quotes == []
    assert channel.docs == []
    assert len(channel.sent) == 1
    assert "valor" in channel.sent[0][1].lower()


async def test_bot_channel_failure_is_graceful(
    db_session: AsyncSession,
    tenant: Tenant,
    bot_chat: dict,
    bot_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Si el canal revienta, el orquestador no propaga la excepción."""

    class BrokenChannel(FakeChannel):
        async def send_text(self, to: str, text: str) -> None:
            raise RuntimeError("Evolution caído")

    channel = BrokenChannel()
    suggestions = [
        _suggestion(description="Tomacorriente doble", matched=True, price=Decimal("15000"))
    ]

    await _run_bot(db_session, tenant, bot_chat, channel, suggestions, monkeypatch)
    # No revienta: el try/except del orquestador lo atrapa y lo registra
