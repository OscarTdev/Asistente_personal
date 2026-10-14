"""Tests de la Fase 5-6: confirmación del dueño, cuenta de cobro y pagos.

- El asistente JAMÁS envía una cotización al cliente sin confirmación
- La cuenta de cobro se genera con consecutivo CC-0001 y total en letras
- Los eventos de pago se guardan primero (idempotentes) y procesan después
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Contact,
    Conversation,
    Document,
    Message,
    PendingAction,
    Tenant,
    TenantModule,
)
from app.schemas.assistant import AssistantIntent
from app.schemas.quotes import ExtractedItemSuggestion, ExtractResponse
from app.services import orchestrator

OWNER_WA_ID = "573005550000"


class FakeChannel:
    name = "fake"
    identity_channel = "whatsapp"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.docs: list[tuple[str, str, str, str]] = []

    async def parse_incoming(self, payload):
        raise NotImplementedError

    async def send_text(self, to: str, text: str) -> str | None:
        self.sent.append((to, text))
        return None

    async def send_document(
        self, to: str, file_name: str, content_base64: str, mimetype: str
    ) -> str | None:
        self.docs.append((to, file_name, content_base64, mimetype))
        return None


def _intent(intention: str = "chat", **kwargs) -> AssistantIntent:
    return AssistantIntent(intention=intention, **kwargs)


@pytest.fixture
def bot_settings(monkeypatch: pytest.MonkeyPatch):
    stub = SimpleNamespace(
        evolution_api_key="test-key",
        llm_api_key="test-llm-key",
        llm_base_url="http://test-llm",
        llm_model="test-model",
        panel_base_url="http://localhost:5173",
    )
    monkeypatch.setattr("app.services.orchestrator.get_settings", lambda: stub)


async def _seed_owner_chat(
    db_session: AsyncSession, tenant: Tenant, with_juliana: bool = True
) -> dict:
    """Dueño registrado con quoter encendido, chat activo y Juliana."""
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
    tenant.wa_id = OWNER_WA_ID
    contact = Contact(tenant_id=tenant.id, wa_id=OWNER_WA_ID, name="El Dueño")
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
        content="Cotizale a Juliana 3 tomacorrientes",
        whatsapp_message_id=f"in-{uuid.uuid4()}",
        status="received",
    )
    db_session.add(message)

    juliana = None
    if with_juliana:
        juliana = Contact(
            tenant_id=tenant.id, wa_id="573009990001", name="Juliana"
        )
        db_session.add(juliana)

    await db_session.commit()
    return {
        "contact": contact,
        "conversation": conversation,
        "message": message,
        "juliana": juliana,
    }


async def _run(
    db_session, tenant, chat, channel, monkeypatch, *,
    intent: AssistantIntent,
    suggestions=None,
) -> None:
    async def fake_extract(db, *, tenant_id, text):
        return ExtractResponse(
            suggestions=suggestions or [], raw_extraction=[]
        )

    async def fake_intent(*, tenant, text):
        return intent

    monkeypatch.setattr(
        orchestrator.ai_service, "extract_items_from_text", fake_extract
    )
    monkeypatch.setattr(
        orchestrator.assistant_service, "detect_intent", fake_intent
    )
    await orchestrator.handle_incoming(
        db_session, tenant=tenant, channel=channel,
        message=chat["message"], contact=chat["contact"],
        conversation=chat["conversation"],
    )


# ── Confirmación del dueño (spec §9.1) ──────────────────────────────────────


async def test_quote_asks_confirmation_before_sending(
    db_session: AsyncSession, tenant: Tenant, bot_settings, monkeypatch
):
    """El asistente JAMÁS envía al cliente sin confirmación explícita."""
    channel = FakeChannel()
    chat = await _seed_owner_chat(db_session, tenant)

    suggestion = ExtractedItemSuggestion(
        description="Tomacorriente doble",
        quantity=Decimal("3"),
        catalog_item_id=None,
        catalog_name="Tomacorriente doble",
        unit_price=Decimal("15000"),
        unit=None,
        matched=True,
    )

    await _run(
        db_session, tenant, chat, channel, monkeypatch,
        intent=_intent("quote", contact_name="Juliana"),
        suggestions=[suggestion],
    )

    # El PDF va al dueño, no a Juliana
    assert all(doc[0] == OWNER_WA_ID for doc in channel.docs)
    assert not any(doc[0] == "573009990001" for doc in channel.docs)

    # El mensaje pregunta
    assert any("envíe" in sent[1].lower() or "enviar" in sent[1].lower() for sent in channel.sent)

    # Hay una acción pendiente
    pending = (
        await db_session.execute(
            select(PendingAction).where(PendingAction.status == "pending")
        )
    ).scalar_one()
    assert pending.action_type == "send_quote"
    assert "quote_id" in pending.payload


async def test_owner_confirms_and_bot_sends_to_client(
    db_session: AsyncSession, tenant: Tenant, bot_settings, monkeypatch
):
    """El dueño dice «sí» → el bot envía al cliente y marca 'sent'."""
    channel = FakeChannel()
    chat = await _seed_owner_chat(db_session, tenant)

    suggestion = ExtractedItemSuggestion(
        description="Tomacorriente doble",
        quantity=Decimal("3"),
        catalog_item_id=None,
        catalog_name="Tomacorriente doble",
        unit_price=Decimal("15000"),
        unit=None,
        matched=True,
    )

    # 1) Dueño pide la cotización
    await _run(
        db_session, tenant, chat, channel, monkeypatch,
        intent=_intent("quote", contact_name="Juliana"),
        suggestions=[suggestion],
    )

    # 2) Dueño confirma
    chat["message"].content = "sí, envíala"
    await db_session.commit()
    await _run(
        db_session, tenant, chat, channel, monkeypatch,
        intent=_intent("confirm", message_text="sí"),
    )

    # El PDF SÍ se envió a Juliana
    assert any(
        doc[0] == "573009990001" and doc[1].endswith(".pdf")
        for doc in channel.docs
    ), f"Docs enviados: {[(d[0], d[1]) for d in channel.docs]}"

    # La cotización quedó en 'sent'
    from app.models import Quote

    quote = (
        await db_session.execute(select(Quote))
    ).scalars().one()
    assert quote.status == "sent"
    assert quote.sent_at is not None

    # La acción pendiente quedó confirmada
    pending = (
        await db_session.execute(select(PendingAction))
    ).scalar_one()
    assert pending.status == "confirmed"


async def test_owner_cancels_and_bot_does_not_send(
    db_session: AsyncSession, tenant: Tenant, bot_settings, monkeypatch
):
    """El dueño dice «no» → el bot NO envía al cliente."""
    channel = FakeChannel()
    chat = await _seed_owner_chat(db_session, tenant)

    suggestion = ExtractedItemSuggestion(
        description="Tomacorriente doble",
        quantity=Decimal("3"),
        catalog_item_id=None,
        catalog_name="Tomacorriente doble",
        unit_price=Decimal("15000"),
        unit=None,
        matched=True,
    )

    await _run(
        db_session, tenant, chat, channel, monkeypatch,
        intent=_intent("quote", contact_name="Juliana"),
        suggestions=[suggestion],
    )

    chat["message"].content = "no, espera"
    await db_session.commit()
    await _run(
        db_session, tenant, chat, channel, monkeypatch,
        intent=_intent("confirm", message_text="no"),
    )

    # NO se envió nada a Juliana
    assert not any(doc[0] == "573009990001" for doc in channel.docs)

    # La acción quedó cancelada
    pending = (
        await db_session.execute(select(PendingAction))
    ).scalar_one()
    assert pending.status == "cancelled"


# ── Cuenta de cobro (CC-0001) ──────────────────────────────────────────────


async def test_invoice_creates_document_and_asks(
    db_session: AsyncSession, tenant: Tenant, bot_settings, monkeypatch
):
    """El dueño pide cuenta de cobro → CC-0001 + PDF + confirmación."""
    channel = FakeChannel()
    chat = await _seed_owner_chat(db_session, tenant)

    await _run(
        db_session, tenant, chat, channel, monkeypatch,
        intent=_intent(
            "invoice",
            contact_name="Juliana",
            amount=500000,
            description="Instalación de 5 tomacorrientes",
        ),
    )

    # Se creó el documento con consecutivo CC
    doc = (
        await db_session.execute(
            select(Document).where(Document.doc_type == "invoice")
        )
    ).scalar_one()
    assert doc.number.startswith("CC-")
    assert doc.snapshot["amount"] in ("500000", "500000.0")
    assert "tomacorrientes" in doc.snapshot["description"]

    # El PDF se envió al dueño
    assert any(doc[0] == OWNER_WA_ID for doc in channel.docs)

    # Hay una acción pendiente de confirmación
    pending = (
        await db_session.execute(
            select(PendingAction).where(PendingAction.action_type == "send_invoice")
        )
    ).scalar_one()
    assert pending.status == "pending"


# ── Eventos de pago idempotentes (spec §11) ────────────────────────────────


async def test_payment_event_saved_first(
    db_session: AsyncSession, tenant: Tenant
):
    """El evento de pago se guarda antes de procesar (UNIQUE = idempotente)."""
    from app.models import PaymentWebhookEvent

    db_session.add(
        PaymentWebhookEvent(
            provider="mercadopago",
            provider_ref="mp:12345",
            status="pending",
            payload={"payment_id": "12345"},
        )
    )
    await db_session.commit()

    # Duplicado → IntegrityError
    db_session.add(
        PaymentWebhookEvent(
            provider="mercadopago",
            provider_ref="mp:12345",
            status="pending",
            payload={"payment_id": "12345"},
        )
    )
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()

    # Solo hay uno
    events = (
        await db_session.execute(
            select(PaymentWebhookEvent).where(
                PaymentWebhookEvent.provider_ref == "mp:12345"
            )
        )
    ).scalars().all()
    assert len(events) == 1


async def test_payment_event_tracks_attempts(
    db_session: AsyncSession, tenant: Tenant
):
    """El evento registra intentos y errores para reintentos."""
    from app.models import PaymentWebhookEvent

    event = PaymentWebhookEvent(
        provider="mercadopago",
        provider_ref="mp:67890",
        status="failed",
        payload={"payment_id": "67890"},
        attempts=3,
        last_error="Connection timeout",
    )
    db_session.add(event)
    await db_session.commit()

    saved = (
        await db_session.execute(
            select(PaymentWebhookEvent).where(
                PaymentWebhookEvent.provider_ref == "mp:67890"
            )
        )
    ).scalar_one()
    assert saved.attempts == 3
    assert saved.last_error == "Connection timeout"
    assert saved.status == "failed"
