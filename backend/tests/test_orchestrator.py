"""Tests del cerebro del asistente: roles, onboarding y acciones del dueño.

El modelo de producto: al bot le escriben los clientes de la PLATAFORMA
(los técnicos). Uno nuevo es un prospecto → onboarding que crea su tenant.
Un dueño registrado → su asistente (cotiza, manda mensajes, conversa).
Los clientes de los dueños (contactos con historial) → silencio.
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.models import (
    Contact,
    Conversation,
    Event,
    Message,
    Quote,
    Tenant,
    TenantModule,
)
from app.schemas.assistant import AssistantIntent
from app.schemas.quotes import ExtractedItemSuggestion, ExtractResponse
from app.services import orchestrator

OWNER_WA_ID = "573005550000"


class FakeChannel(Channel):
    """Canal de prueba: registra envíos en lugar de llamar a Evolution."""

    name = "fake"

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


def _intent(
    intention: str = "chat",
    contact_name: str | None = None,
    message_text: str | None = None,
) -> AssistantIntent:
    return AssistantIntent(
        intention=intention, contact_name=contact_name, message_text=message_text
    )


@pytest.fixture
def bot_settings(monkeypatch: pytest.MonkeyPatch):
    """Settings del orquestador sin depender del .env real."""
    stub = SimpleNamespace(
        evolution_api_key="test-key",
        llm_api_key="test-llm-key",
        llm_base_url="http://test-llm",
        llm_model="test-model",
    )
    monkeypatch.setattr("app.services.orchestrator.get_settings", lambda: stub)


async def _seed_chat(
    db_session: AsyncSession,
    tenant: Tenant,
    *,
    wa_id: str,
    content: str | None = "Cotizame 3 tomacorrientes dobles",
    message_type: str = "text",
    name: str | None = "Remitente",
) -> dict:
    contact = Contact(tenant_id=tenant.id, wa_id=wa_id, name=name)
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
        type=message_type,
        content=content,
        whatsapp_message_id=f"in-{uuid.uuid4()}",
        status="received",
    )
    db_session.add(message)
    await db_session.commit()
    return {"contact": contact, "conversation": conversation, "message": message}


@pytest.fixture
async def owner_chat(db_session: AsyncSession, tenant: Tenant) -> dict:
    """Dueño registrado (su número es la llave) con quoter encendido."""
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
    chat = await _seed_chat(db_session, tenant, wa_id=OWNER_WA_ID, name="El Dueño")
    await db_session.commit()
    return chat


@pytest.fixture
async def juliana(db_session: AsyncSession, tenant: Tenant) -> Contact:
    contact = Contact(tenant_id=tenant.id, wa_id="573009990001", name="Juliana")
    db_session.add(contact)
    await db_session.commit()
    return contact


async def _run_as_owner(
    db_session: AsyncSession,
    tenant: Tenant,
    chat: dict,
    channel: FakeChannel,
    monkeypatch: pytest.MonkeyPatch,
    *,
    intent: AssistantIntent,
    suggestions: list[ExtractedItemSuggestion] | None = None,
) -> None:
    async def fake_extract(db, *, tenant_id, text):
        return ExtractResponse(suggestions=suggestions or [], raw_extraction=[])

    async def fake_intent(*, tenant, text):
        return intent

    monkeypatch.setattr(
        orchestrator.ai_service, "extract_items_from_text", fake_extract
    )
    monkeypatch.setattr(orchestrator.assistant_service, "detect_intent", fake_intent)
    await orchestrator.handle_incoming(
        db_session,
        tenant=tenant,
        channel=channel,
        message=chat["message"],
        contact=chat["contact"],
        conversation=chat["conversation"],
    )


# ── Onboarding: el bot es la puerta de entrada ─────────────────────────────


async def test_prospect_onboarding_full_flow(
    db_session: AsyncSession, tenant: Tenant, bot_settings
):
    """Número desconocido → registro conversacional → SU tenant en trial."""
    channel = FakeChannel()
    chat = await _seed_chat(
        db_session, tenant, wa_id="573009997777", content="Hola"
    )

    _call = lambda: orchestrator.handle_incoming(  # noqa: E731
        db_session,
        tenant=tenant,
        channel=channel,
        message=chat["message"],
        contact=chat["contact"],
        conversation=chat["conversation"],
    )

    # 1) «Acepta la política» (consentimiento)
    await _call()
    assert "acepto" in channel.sent[0][1].lower()

    # 2) Acepta → pide nombre del bot
    chat["message"].content = "acepto"
    await db_session.commit()
    await _call()
    assert "llame" in channel.sent[1][1].lower()

    # 3) Nombre del bot → tipo de cuenta
    chat["message"].content = "Aura"
    await db_session.commit()
    await _call()
    assert "persona natural" in channel.sent[2][1].lower()

    # 4) Persona natural → SIN NIT, pide nombre
    chat["message"].content = "1"
    await db_session.commit()
    await _call()
    assert "llame" in channel.sent[3][1].lower()

    # 5) Nombre → ciudad
    chat["message"].content = "Juan Pérez"
    await db_session.commit()
    await _call()
    assert "ciudad" in channel.sent[4][1].lower()

    # 6) Ciudad → correo
    chat["message"].content = "Medellín"
    await db_session.commit()
    await _call()
    assert "correo" in channel.sent[5][1].lower()

    # 7) Correo → preferencia
    chat["message"].content = "juan@ejemplo.com"
    await db_session.commit()
    await _call()
    assert "texto" in channel.sent[6][1].lower()

    # 8) Preferencia → crea el tenant
    chat["message"].content = "1"
    await db_session.commit()
    await _call()

    new_tenant = (
        await db_session.execute(
            select(Tenant).where(Tenant.slug == "juan-perez")
        )
    ).scalar_one()
    assert new_tenant.wa_id == "573009997777"
    assert new_tenant.bot_name == "Aura"
    assert new_tenant.name == "Juan Pérez"
    assert new_tenant.plan == "trial"
    # Persona natural: sin NIT (regla del producto)
    assert new_tenant.account_type == "personal"
    assert new_tenant.nit is None

    # El contrato del plan trial: su cotizador queda encendido
    quoter = (
        await db_session.execute(
            select(TenantModule).where(
                TenantModule.tenant_id == new_tenant.id,
                TenantModule.module_key == "quoter",
            )
        )
    ).scalar_one()
    assert quoter.is_enabled is True

    await db_session.refresh(chat["contact"])
    assert chat["contact"].onboarding_state is None

    menu = channel.sent[7][1]
    assert "¿Con qué quieres empezar?" in menu
    assert "Aura" in menu
    assert "contraseña" in menu.lower() or "token=" in menu


async def test_prospect_business_flow_asks_and_validates_nit(
    db_session: AsyncSession, tenant: Tenant, bot_settings
):
    """Negocio o empresa → NIT obligatorio con dígito de verificación."""
    channel = FakeChannel()
    chat = await _seed_chat(
        db_session, tenant, wa_id="573009996666", content="Hola"
    )

    async def _say(text: str) -> None:
        chat["message"].content = text
        await db_session.commit()
        await orchestrator.handle_incoming(
            db_session,
            tenant=tenant,
            channel=channel,
            message=chat["message"],
            contact=chat["contact"],
            conversation=chat["conversation"],
        )

    await _say("Hola")    # bienvenida + consentimiento
    await _say("acepto")  # → pide nombre del bot
    await _say("Chispa")  # → pregunta el tipo de cuenta
    await _say("2")       # negocio → pide NIT
    assert "NIT" in channel.sent[-1][1]

    # NIT con dígito incorrecto → re-pregunta, no avanza
    await _say("900123456-7")  # el DV correcto de esa base es 6
    assert "No pude validar" in channel.sent[-1][1]

    # NIT válido → pide el nombre
    await _say("900.123.456-6")
    assert "llame" in channel.sent[-1][1].lower()

    # Completa el resto del registro
    await _say("Instalaciones El Rayo SAS")
    await _say("Cali")
    await _say("admin@rayo.com")
    await _say("3")

    new_tenant = (
        await db_session.execute(
            select(Tenant).where(Tenant.slug == "instalaciones-el-rayo-sas")
        )
    ).scalar_one()
    assert new_tenant.account_type == "business"
    assert new_tenant.nit == "900123456-6"
    assert new_tenant.bot_name == "Chispa"


async def test_onboarding_slug_uniqueness(
    db_session: AsyncSession, bot_settings
):
    """Dos negocios con el mismo nombre no se pisan el slug."""
    from app.services.onboarding import _unique_slug

    db_session.add(Tenant(name="Juan Pérez", slug="juan-perez", bot_name="Aura"))
    await db_session.commit()

    slug = await _unique_slug(db_session, "Juan Pérez")
    assert slug == "juan-perez-2"


async def test_client_with_history_stays_silent(
    db_session: AsyncSession, tenant: Tenant, bot_settings
):
    """Un cliente del dueño (con cotizaciones) NUNCA entra a onboarding."""
    channel = FakeChannel()
    chat = await _seed_chat(db_session, tenant, wa_id="573001112233")
    db_session.add(
        Quote(
            tenant_id=tenant.id,
            contact_id=chat["contact"].id,
            conversation_id=chat["conversation"].id,
            status="sent",
            total=1000,
        )
    )
    await db_session.commit()

    await orchestrator.handle_incoming(
        db_session,
        tenant=tenant,
        channel=channel,
        message=chat["message"],
        contact=chat["contact"],
        conversation=chat["conversation"],
    )
    assert channel.sent == []
    assert channel.docs == []


# ── El dueño le habla a su asistente ───────────────────────────────────────


async def test_owner_orders_quote_gets_pdf_draft(
    db_session: AsyncSession,
    tenant: Tenant,
    owner_chat: dict,
    bot_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """El dueño pide cotizar → quote en draft con PDF en SU chat."""
    channel = FakeChannel()
    suggestions = [
        _suggestion(description="Tomacorriente doble", matched=True, price=Decimal("15000"))
    ]

    await _run_as_owner(
        db_session,
        tenant,
        owner_chat,
        channel,
        monkeypatch,
        intent=_intent("quote"),
        suggestions=suggestions,
    )

    quote = (await db_session.execute(select(Quote))).scalars().one()
    assert quote.total == 45000
    # Draft: el dueño la revisa y la envía; el seguimiento entra al marcarla
    assert quote.status == "draft"
    assert quote.sent_at is None

    # El aviso y el PDF llegan al chat del dueño
    assert len(channel.sent) == 1
    assert channel.sent[0][0] == OWNER_WA_ID
    assert "cotización" in channel.sent[0][1].lower()
    assert len(channel.docs) == 1
    assert channel.docs[0][0] == OWNER_WA_ID

    # El PDF enviado quedó registrado (con id para deduplicar el eco)
    doc_message = (
        await db_session.execute(
            select(Message).where(Message.direction == "out", Message.type == "document")
        )
    ).scalars().one()
    assert doc_message.content.startswith("cotizacion_")


async def test_owner_quote_for_named_client(
    db_session: AsyncSession,
    tenant: Tenant,
    owner_chat: dict,
    juliana: Contact,
    bot_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """«Cotizale a Juliana...» → la cotización queda ligada a Juliana."""
    channel = FakeChannel()
    suggestions = [
        _suggestion(description="Tomacorriente doble", matched=True, price=Decimal("15000"))
    ]

    await _run_as_owner(
        db_session,
        tenant,
        owner_chat,
        channel,
        monkeypatch,
        intent=_intent("quote", contact_name="Juliana"),
        suggestions=suggestions,
    )

    quote = (await db_session.execute(select(Quote))).scalars().one()
    assert quote.contact_id == juliana.id
    assert "Juliana" in channel.sent[0][1]


async def test_owner_send_message_action(
    db_session: AsyncSession,
    tenant: Tenant,
    owner_chat: dict,
    juliana: Contact,
    bot_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """«Mandale un mensaje de buenos días a Juliana» → el asistente lo hace."""
    channel = FakeChannel()

    await _run_as_owner(
        db_session,
        tenant,
        owner_chat,
        channel,
        monkeypatch,
        intent=_intent(
            "send_message",
            contact_name="Juliana",
            message_text="¡Buenos días, Juliana! 🌞",
        ),
    )

    # 1) El mensaje salió al CONTACTO; 2) confirmación al dueño
    assert channel.sent[0] == ("573009990001", "¡Buenos días, Juliana! 🌞")
    assert channel.sent[1][0] == OWNER_WA_ID
    assert "Le escribí a Juliana" in channel.sent[1][1]

    # El mensaje quedó en la conversación DE JULIANA (historial correcto)
    sent_to_juliana = (
        await db_session.execute(
            select(Message)
            .where(Message.direction == "out")
            .where(Message.conversation_id != owner_chat["conversation"].id)
        )
    ).scalars().one()
    assert sent_to_juliana.content == "¡Buenos días, Juliana! 🌞"


async def test_send_message_unknown_contact_asks(
    db_session: AsyncSession,
    tenant: Tenant,
    owner_chat: dict,
    bot_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Nombre que no existe → el asistente pregunta, no arriesga."""
    channel = FakeChannel()

    await _run_as_owner(
        db_session,
        tenant,
        owner_chat,
        channel,
        monkeypatch,
        intent=_intent("send_message", contact_name="Nadie", message_text="Hola"),
    )

    assert len(channel.sent) == 1
    assert channel.sent[0][0] == OWNER_WA_ID
    assert "No encontré" in channel.sent[0][1]


async def test_send_message_ambiguous_contact_asks(
    db_session: AsyncSession,
    tenant: Tenant,
    owner_chat: dict,
    bot_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Dos contactos con el mismo nombre → pregunta a cuál."""
    channel = FakeChannel()
    db_session.add(Contact(tenant_id=tenant.id, wa_id="573009990002", name="Juliana"))
    db_session.add(Contact(tenant_id=tenant.id, wa_id="573009990003", name="Juliana"))
    await db_session.commit()

    await _run_as_owner(
        db_session,
        tenant,
        owner_chat,
        channel,
        monkeypatch,
        intent=_intent("send_message", contact_name="Juliana", message_text="Hola"),
    )

    assert len(channel.sent) == 1
    assert "Encontré varios" in channel.sent[0][1]


async def test_owner_unmatched_items_no_pdf(
    db_session: AsyncSession,
    tenant: Tenant,
    owner_chat: dict,
    bot_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Ítem sin precio del catálogo → sin cotización, sin PDF, y queda en revisión."""
    channel = FakeChannel()
    suggestions = [
        _suggestion(description="Chapa premium", matched=False, price=None)
    ]

    await _run_as_owner(
        db_session,
        tenant,
        owner_chat,
        channel,
        monkeypatch,
        intent=_intent("quote"),
        suggestions=suggestions,
    )

    quotes = (await db_session.execute(select(Quote))).scalars().all()
    assert quotes == []
    assert channel.docs == []
    assert len(channel.sent) == 1
    assert "valor" in channel.sent[0][1].lower()

    review_event = (
        await db_session.execute(
            select(Event).where(Event.type == "quote.needs_review")
        )
    ).scalar_one()
    assert review_event.payload["items"] == ["Chapa premium"]


async def test_owner_audio_gets_ack_document_silent(
    db_session: AsyncSession,
    tenant: Tenant,
    owner_chat: dict,
    bot_settings,
):
    """Notas de voz del dueño piden aclaración; documentos van en silencio."""
    channel = FakeChannel()

    chat = owner_chat
    chat["message"].type = "audio"
    chat["message"].content = None
    await db_session.commit()
    await orchestrator.handle_incoming(
        db_session,
        tenant=tenant,
        channel=channel,
        message=chat["message"],
        contact=chat["contact"],
        conversation=chat["conversation"],
    )
    assert len(channel.sent) == 1
    assert "Te recibí" in channel.sent[0][1]

    # Un documento (eco de un PDF nuestro incluido) no genera respuesta
    chat["message"].type = "document"
    chat["message"].content = None
    chat["message"].whatsapp_message_id = f"in-{uuid.uuid4()}"
    await db_session.commit()
    await orchestrator.handle_incoming(
        db_session,
        tenant=tenant,
        channel=channel,
        message=chat["message"],
        contact=chat["contact"],
        conversation=chat["conversation"],
    )
    assert len(channel.sent) == 1  # sin cambios: silencio


async def test_owner_chat_gets_llm_reply(
    db_session: AsyncSession,
    tenant: Tenant,
    owner_chat: dict,
    bot_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Intención 'chat' → el LLM conversacional responde en su chat."""
    channel = FakeChannel()
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="¡Claro que sí!"))]
    )

    class _FakeCompletions:
        async def create(self, **kwargs):
            return fake_response

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr(orchestrator, "AsyncOpenAI", lambda **kwargs: _FakeClient())

    await _run_as_owner(
        db_session, tenant, owner_chat, channel, monkeypatch, intent=_intent("chat")
    )

    assert channel.sent == [(OWNER_WA_ID, "¡Claro que sí!")]


async def test_bot_channel_failure_is_graceful(
    db_session: AsyncSession,
    tenant: Tenant,
    owner_chat: dict,
    bot_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Si el canal revienta, el orquestador no propaga la excepción."""

    class BrokenChannel(FakeChannel):
        async def send_text(self, to: str, text: str) -> str | None:
            raise RuntimeError("Evolution caído")

    channel = BrokenChannel()
    suggestions = [
        _suggestion(description="Tomacorriente doble", matched=True, price=Decimal("15000"))
    ]

    await _run_as_owner(
        db_session,
        tenant,
        owner_chat,
        channel,
        monkeypatch,
        intent=_intent("quote"),
        suggestions=suggestions,
    )
    # No revienta: el try/except del orquestador lo atrapa y lo registra
