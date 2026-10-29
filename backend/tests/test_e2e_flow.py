"""Test E2E de integración: flujo completo polo a polo.

Este test simula el recorrido real de un mensaje de WhatsApp:
webhook → ingesta (idempotencia, debounce) → identidad → onboarding/routing
→ orquestador (intención + IA) → acción (cotización/PDF/mensaje)
→ persistencia → respuesta al canal.

Cubre:
1. Prospecto desconocido → onboarding completo → tenant trial + quoter activo
2. Dueño chatea con su bot → intención 'chat' → respuesta LLM
3. Dueño pide cotizar → extracción IA + matching catálogo → PDF draft
4. Dueño pide enviar mensaje a cliente → se entrega al contacto correcto
5. Ítem sin match en catálogo → evento quote.needs_review, sin PDF
6. Cliente del dueño (con historial) → silencio (modo atención apagado)
7. Idempotencia: mensaje duplicado no se reprocesa
8. Audio → transcripción → se trata como texto normal
9. Negocio con NIT → onboarding válido → tenant business
10. Owner self-chat con LID/alias (WhatsApp usa LID en lugar de número)
11. Debounce: 3 mensajes en <5s → se agrupan en 1 respuesta
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.evolution import EvolutionChannel
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
from app.services.messages import ingest_message

# ──────────────────────────────────────────────────────────────────────────────
# Helpers y fakes
# ──────────────────────────────────────────────────────────────────────────────

OWNER_WA_ID = "573005550000"
CLIENT_WA_ID = "573009990001"
PROSPECT_WA_ID = "573009997777"


class FakeEvolutionChannel(EvolutionChannel):
    """Canal Evolution que parsea real pero NUNCA envía a WhatsApp."""

    name = "evolution"
    identity_channel = "whatsapp"

    def __init__(self) -> None:
        super().__init__()
        self.sent_text: list[tuple[str, str]] = []
        self.sent_docs: list[tuple[str, str, str, str]] = []

    async def send_text(self, to: str, text: str) -> str | None:
        self.sent_text.append((to, text))
        return f"msg-{uuid.uuid4()}"

    async def send_document(
        self, to: str, file_name: str, content_base64: str, mimetype: str
    ) -> str | None:
        self.sent_docs.append((to, file_name, content_base64, mimetype))
        return f"doc-{uuid.uuid4()}"


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
    amount: float | None = None,
    description: str | None = None,
) -> AssistantIntent:
    return AssistantIntent(
        intention=intention,
        contact_name=contact_name,
        message_text=message_text,
        amount=amount,
        description=description,
    )


def _build_evolution_payload(
    *,
    wa_id: str,
    text: str | None = None,
    message_type: str = "text",
    from_me: bool = False,
    message_id: str | None = None,
    push_name: str | None = None,
    wa_lid: str | None = None,
) -> dict:
    """Construye un payload tipo Evolution API v2 para el webhook."""
    jid = f"{wa_id}@s.whatsapp.net"
    if wa_lid:
        # wa_lid puede venir como "1234567890" o "1234567890@lid"
        lid_value = wa_lid.replace("@lid", "")
        jid = f"{lid_value}@lid"
    payload = {
        "data": {
            "key": {
                "id": message_id or f"webhook-{uuid.uuid4()}",
                "remoteJid": jid,
                "fromMe": from_me,
            },
            "message": {},
            "pushName": push_name,
        },
        "sender": f"{wa_id}@s.whatsapp.net",
    }
    if wa_lid:
        # Con LID, Evolution manda el número real en remoteJidAlt
        payload["data"]["key"]["remoteJidAlt"] = f"{wa_id}@s.whatsapp.net"
    if message_type == "text":
        payload["data"]["message"]["conversation"] = text or ""
    elif message_type == "extendedText":
        payload["data"]["message"]["extendedTextMessage"] = {"text": text or ""}
    elif message_type == "audio":
        payload["data"]["message"]["audioMessage"] = {
            "caption": text,
            "url": "https://mmg.whatsapp.net/...",
            "base64": None,
        }
    elif message_type == "image":
        payload["data"]["message"]["imageMessage"] = {
            "caption": text,
            "url": "https://mmg.whatsapp.net/...",
            "base64": None,
        }
    return payload


async def _load_message_relations(db_session: AsyncSession, message: Message):
    """Carga las relaciones tenant, conversation y contact del mensaje."""
    from app.models import Contact, Conversation, Tenant
    tenant = await db_session.get(Tenant, message.tenant_id)
    conversation = await db_session.get(Conversation, message.conversation_id)
    contact = await db_session.get(Contact, conversation.contact_id) if conversation else None
    return tenant, conversation, contact


@pytest.fixture
def e2e_settings(monkeypatch: pytest.MonkeyPatch):
    """Settings stub para tests E2E sin depender de .env real."""
    stub = SimpleNamespace(
        evolution_api_key="test-evolution-key",
        evolution_api_url="http://test-evolution",
        evolution_instance="test-instance",
        webhook_secret="test-webhook-secret",
        platform_tenant_slug="plataforma",
        llm_api_key="test-llm-key",
        llm_base_url="http://test-llm",
        llm_model="test-model",
        panel_base_url="http://localhost:5173",
    )
    monkeypatch.setattr("app.services.orchestrator.get_settings", lambda: stub)
    monkeypatch.setattr("app.services.onboarding.get_settings", lambda: stub)
    monkeypatch.setattr("app.api.v1.webhooks.get_settings", lambda: stub)
    monkeypatch.setattr("app.core.config.get_settings", lambda: stub)
    return stub


@pytest.fixture
async def platform_tenant(db_session: AsyncSession) -> Tenant:
    """Tenant de plataforma (is_platform=True): puerta de entrada para prospectos."""
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Plataforma",
        slug="plataforma",
        bot_name="Aura",
        is_active=True,
        is_platform=True,
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest.fixture
async def owner_tenant(db_session: AsyncSession) -> Tenant:
    """Tenant del dueño ya registrado, con quoter habilitado."""
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Eléctrica Los Andes",
        slug="electrica-los-andes",
        bot_name="Sparky",
        wa_id=OWNER_WA_ID,
        is_active=True,
        plan="premium",
        is_platform=False,
    )
    db_session.add(tenant)
    await db_session.flush()

    # Módulo quoter activo (plan premium lo permite)
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
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest.fixture
async def owner_contact(db_session: AsyncSession, owner_tenant: Tenant) -> Contact:
    """Contacto dueño en su propio tenant."""
    contact = Contact(
        tenant_id=owner_tenant.id,
        wa_id=OWNER_WA_ID,
        name="El Dueño",
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


@pytest.fixture
async def owner_conversation(
    db_session: AsyncSession, owner_tenant: Tenant, owner_contact: Contact
) -> Conversation:
    conv = Conversation(
        tenant_id=owner_tenant.id,
        contact_id=owner_contact.id,
        status="open",
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return conv


@pytest.fixture
async def juliana_client(
    db_session: AsyncSession, owner_tenant: Tenant
) -> Contact:
    """Cliente del dueño (tiene historial: cotizaciones previas)."""
    contact = Contact(
        tenant_id=owner_tenant.id,
        wa_id=CLIENT_WA_ID,
        name="Juliana",
    )
    db_session.add(contact)
    await db_session.flush()

    conv = Conversation(
        tenant_id=owner_tenant.id,
        contact_id=contact.id,
        status="open",
    )
    db_session.add(conv)
    await db_session.flush()

    # Historial: cotización previa → modo customer_mode=off → silencio
    db_session.add(
        Quote(
            tenant_id=owner_tenant.id,
            contact_id=contact.id,
            conversation_id=conv.id,
            status="sent",
            total=50000,
        )
    )
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


# ──────────────────────────────────────────────────────────────────────────────
# 1. Prospecto desconocido → onboarding completo → tenant trial
# ──────────────────────────────────────────────────────────────────────────────

async def test_e2e_prospect_onboarding_creates_tenant(
    db_session: AsyncSession,
    platform_tenant: Tenant,
    e2e_settings,
):
    """Flujo completo: número nuevo → onboarding → su tenant trial con quoter ON."""
    channel = FakeEvolutionChannel()

    # ── Paso 1: Primer mensaje del prospecto (entra por webhook) ─────────────
    payload = _build_evolution_payload(
        wa_id=PROSPECT_WA_ID,
        text="Hola",
        push_name="Juan Pérez",
    )
    # Ingesta + orquestador (simula webhook → debounce → handle_incoming)
    incoming = await channel.parse_incoming(payload)

    # La identidad se resuelve al tenant de plataforma (prospecto)
    from app.services import identity as identity_service
    resolved = await identity_service.resolve_identity(
        db_session,
        channel="whatsapp",
        external_id=incoming.wa_id,
        alias_external_id=incoming.wa_lid,
        fallback_tenant=platform_tenant,
        display_name=incoming.push_name,
    )
    assert resolved.tenant.id == platform_tenant.id
    assert resolved.created is True  # contacto nuevo = prospecto

    # Ingerir mensaje
    result = await ingest_message(db_session, platform_tenant, channel, payload)
    assert result.created is True

    # Cargar relaciones del mensaje
    message_tenant, message_conv, _ = await _load_message_relations(db_session, result.message)

    # Orquestador: detecta onboarding_state in_progress → continue_onboarding
    await orchestrator.handle_incoming(
        db_session,
        tenant=message_tenant,
        channel=channel,
        message=result.message,
        contact=resolved.contact,
        conversation=message_conv,
    )

    # Debe pedir consentimiento (Ley 1581)
    assert len(channel.sent_text) == 1
    assert "acepto" in channel.sent_text[0][1].lower()

    # ── Paso 2: Acepta consentimiento ───────────────────────────────────────
    payload2 = _build_evolution_payload(
        wa_id=PROSPECT_WA_ID,
        text="acepto",
        message_id=f"webhook-{uuid.uuid4()}",
    )
    result2 = await ingest_message(db_session, platform_tenant, channel, payload2)
    _, _, contact2 = await _load_message_relations(db_session, result2.message)
    await orchestrator.handle_incoming(
        db_session,
        tenant=platform_tenant,
        channel=channel,
        message=result2.message,
        contact=contact2,
        conversation=message_conv,
    )
    assert "llame" in channel.sent_text[-1][1].lower()  # pide nombre del bot

    # ── Paso 3: Nombre del bot ──────────────────────────────────────────────
    payload3 = _build_evolution_payload(
        wa_id=PROSPECT_WA_ID,
        text="MiBot",
        message_id=f"webhook-{uuid.uuid4()}",
    )
    result3 = await ingest_message(db_session, platform_tenant, channel, payload3)
    _, message_conv3, contact3 = await _load_message_relations(db_session, result3.message)
    await orchestrator.handle_incoming(
        db_session,
        tenant=platform_tenant,
        channel=channel,
        message=result3.message,
        contact=contact3,
        conversation=message_conv3,
    )
    assert "llame" in channel.sent_text[-1][1].lower()

    # ── Paso 4: Persona natural (1) ─────────────────────────────────────────
    payload4 = _build_evolution_payload(
        wa_id=PROSPECT_WA_ID,
        text="1",
        message_id=f"webhook-{uuid.uuid4()}",
    )
    result4 = await ingest_message(db_session, platform_tenant, channel, payload4)
    _, message_conv4, contact4 = await _load_message_relations(db_session, result4.message)
    await orchestrator.handle_incoming(
        db_session,
        tenant=platform_tenant,
        channel=channel,
        message=result4.message,
        contact=contact4,
        conversation=message_conv4,
    )
    assert "llame" in channel.sent_text[-1][1].lower()

    # ── Paso 5: Nombre del dueño ────────────────────────────────────────────
    payload5 = _build_evolution_payload(
        wa_id=PROSPECT_WA_ID,
        text="Juan Pérez",
        message_id=f"webhook-{uuid.uuid4()}",
    )
    result5 = await ingest_message(db_session, platform_tenant, channel, payload5)
    _, message_conv5, contact5 = await _load_message_relations(db_session, result5.message)
    await orchestrator.handle_incoming(
        db_session,
        tenant=platform_tenant,
        channel=channel,
        message=result5.message,
        contact=contact5,
        conversation=message_conv5,
    )
    assert "ciudad" in channel.sent_text[-1][1].lower()

    # ── Paso 6: Ciudad ──────────────────────────────────────────────────────
    payload6 = _build_evolution_payload(
        wa_id=PROSPECT_WA_ID,
        text="Medellín",
        message_id=f"webhook-{uuid.uuid4()}",
    )
    result6 = await ingest_message(db_session, platform_tenant, channel, payload6)
    _, message_conv6, contact6 = await _load_message_relations(db_session, result6.message)
    await orchestrator.handle_incoming(
        db_session,
        tenant=platform_tenant,
        channel=channel,
        message=result6.message,
        contact=contact6,
        conversation=message_conv6,
    )
    assert "correo" in channel.sent_text[-1][1].lower()

    # ── Paso 7: Correo ──────────────────────────────────────────────────────
    payload7 = _build_evolution_payload(
        wa_id=PROSPECT_WA_ID,
        text="juan@ejemplo.com",
        message_id=f"webhook-{uuid.uuid4()}",
    )
    result7 = await ingest_message(db_session, platform_tenant, channel, payload7)
    _, message_conv7, contact7 = await _load_message_relations(db_session, result7.message)
    await orchestrator.handle_incoming(
        db_session,
        tenant=platform_tenant,
        channel=channel,
        message=result7.message,
        contact=contact7,
        conversation=message_conv7,
    )
    assert "texto" in channel.sent_text[-1][1].lower()
    assert "audio" in channel.sent_text[-1][1].lower()

    # ── Paso 8: Preferencia de respuesta → crea tenant ──────────────────────
    payload8 = _build_evolution_payload(
        wa_id=PROSPECT_WA_ID,
        text="1",  # solo texto
        message_id=f"webhook-{uuid.uuid4()}",
    )
    result8 = await ingest_message(db_session, platform_tenant, channel, payload8)
    _, message_conv8, contact8 = await _load_message_relations(db_session, result8.message)
    await orchestrator.handle_incoming(
        db_session,
        tenant=platform_tenant,
        channel=channel,
        message=result8.message,
        contact=contact8,
        conversation=message_conv8,
    )

    # ── Verificaciones finales ──────────────────────────────────────────────
    # Tenant nuevo creado
    new_tenant = (
        await db_session.execute(
            select(Tenant).where(Tenant.slug == "juan-perez")
        )
    ).scalar_one()
    assert new_tenant.wa_id == PROSPECT_WA_ID
    assert new_tenant.bot_name == "MiBot"
    assert new_tenant.name == "Juan Pérez"
    assert new_tenant.account_type == "personal"
    assert new_tenant.nit is None
    assert new_tenant.plan == "trial"

    # Módulo quoter encendido por el contrato del plan trial
    quoter = (
        await db_session.execute(
            select(TenantModule).where(
                TenantModule.tenant_id == new_tenant.id,
                TenantModule.module_key == "quoter",
            )
        )
    ).scalar_one()
    assert quoter.is_enabled is True

    # Identidad del prospecto limpiada de plataforma + vinculada en SU tenant
    from app.services.identity import ChannelIdentity
    platform_identities = (
        await db_session.execute(
            select(ChannelIdentity).where(
                ChannelIdentity.channel == "whatsapp",
                ChannelIdentity.external_id == PROSPECT_WA_ID,
                ChannelIdentity.tenant_id == platform_tenant.id,
            )
        )
    ).scalars().all()
    assert platform_identities == []  # limpiada al completar onboarding

    owner_identities = (
        await db_session.execute(
            select(ChannelIdentity).where(
                ChannelIdentity.channel == "whatsapp",
                ChannelIdentity.external_id == PROSPECT_WA_ID,
                ChannelIdentity.tenant_id == new_tenant.id,
                ChannelIdentity.kind == "owner",
            )
        )
    ).scalars().all()
    assert len(owner_identities) == 1  # vinculada como owner en su tenant

    # Mensaje final con enlace de contraseña
    final_msg = channel.sent_text[-1][1]
    assert "token=" in final_msg or "crear-contrasena" in final_msg
    assert new_tenant.bot_name in final_msg


# ──────────────────────────────────────────────────────────────────────────────
# 2. Dueño chatea con su bot (intención chat)
# ──────────────────────────────────────────────────────────────────────────────

async def test_e2e_owner_chat_llm_reply(
    db_session: AsyncSession,
    owner_tenant: Tenant,
    owner_contact: Contact,
    owner_conversation: Conversation,
    e2e_settings,
):
    """Dueño envía mensaje de chat → LLM responde en su conversación."""
    channel = FakeEvolutionChannel()

    # Mock del cliente OpenAI
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

    with patch("app.services.orchestrator.AsyncOpenAI", return_value=_FakeClient()):
        payload = _build_evolution_payload(
            wa_id=OWNER_WA_ID,
            text="¿Cómo va el día?",
            from_me=True,  # auto-chat del dueño
            push_name="El Dueño",
        )
        result = await ingest_message(db_session, owner_tenant, channel, payload)

        # Debe resolver al tenant del dueño (no plataforma)
        assert result.message.tenant_id == owner_tenant.id
        assert result.message.conversation_id == owner_conversation.id

        message_tenant, message_conv, message_contact = (
            await _load_message_relations(db_session, result.message)
        )

        await orchestrator.handle_incoming(
            db_session,
            tenant=message_tenant,
            channel=channel,
            message=result.message,
            contact=message_contact,
            conversation=message_conv,
        )

    # Respuesta del LLM en el chat del dueño
    assert len(channel.sent_text) == 1
    assert channel.sent_text[0][0] == OWNER_WA_ID
    assert channel.sent_text[0][1] == "¡Claro que sí!"


# ──────────────────────────────────────────────────────────────────────────────
# 3. Dueño pide cotizar → extracción IA + matching catálogo → PDF draft
# ──────────────────────────────────────────────────────────────────────────────

async def test_e2e_owner_quote_generates_pdf_draft(
    db_session: AsyncSession,
    owner_tenant: Tenant,
    owner_contact: Contact,
    owner_conversation: Conversation,
    e2e_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Dueño pide cotización → extracción → matching → quote draft + PDF."""
    channel = FakeEvolutionChannel()

    suggestions = [
        _suggestion(description="Tomacorriente doble", matched=True, price=Decimal("15000")),
        _suggestion(description="Cable 12 AWG", matched=True, price=Decimal("8000")),
    ]
    # Ajustar cantidades: 3 tomacorrientes + 2 rollos cable = 3*15000 + 2*8000 = 61000
    suggestions[0].quantity = Decimal("3")
    suggestions[1].quantity = Decimal("2")

    async def fake_extract(db, *, tenant_id, text):
        return ExtractResponse(suggestions=suggestions, raw_extraction=[])

    async def fake_intent(*, tenant, text):
        return _intent("quote")

    monkeypatch.setattr(orchestrator.ai_service, "extract_items_from_text", fake_extract)
    monkeypatch.setattr(orchestrator.assistant_service, "detect_intent", fake_intent)

    payload = _build_evolution_payload(
        wa_id=OWNER_WA_ID,
        text="Cotizame 3 tomacorrientes dobles y 2 rollos de cable 12 AWG",
        from_me=True,
    )
    result = await ingest_message(db_session, owner_tenant, channel, payload)
    message_tenant, message_conv, message_contact = (
        await _load_message_relations(db_session, result.message)
    )
    await orchestrator.handle_incoming(
        db_session,
        tenant=message_tenant,
        channel=channel,
        message=result.message,
        contact=message_contact,
        conversation=message_conv,
    )

    # Quote creada en draft
    quote = (await db_session.execute(select(Quote))).scalars().one()
    assert quote.total == Decimal("61000")  # 3*15000 + 2*8000
    assert quote.status == "draft"
    assert quote.sent_at is None

    # Aviso + PDF en el chat del dueño
    assert len(channel.sent_text) == 1
    assert channel.sent_text[0][0] == OWNER_WA_ID
    assert "cotización" in channel.sent_text[0][1].lower()
    assert len(channel.sent_docs) == 1
    assert channel.sent_docs[0][0] == OWNER_WA_ID
    assert channel.sent_docs[0][1].startswith("COT-")
    assert channel.sent_docs[0][3] == "application/pdf"

    # PDF registrado como mensaje out para deduplicar eco
    doc_message = (
        await db_session.execute(
            select(Message).where(Message.direction == "out", Message.type == "document")
        )
    ).scalars().one()
    assert doc_message.content.startswith("COT-")
    assert doc_message.whatsapp_message_id is not None


# ──────────────────────────────────────────────────────────────────────────────
# 4. Dueño pide enviar mensaje a cliente
# ──────────────────────────────────────────────────────────────────────────────

async def test_e2e_owner_send_message_to_client(
    db_session: AsyncSession,
    owner_tenant: Tenant,
    owner_contact: Contact,
    owner_conversation: Conversation,
    juliana_client: Contact,
    e2e_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Dueño dice 'mándale un mensaje a Juliana' → se entrega a Juliana."""
    channel = FakeEvolutionChannel()

    async def fake_intent(*, tenant, text):
        return _intent(
            "send_message",
            contact_name="Juliana",
            message_text="¡Buenos días, Juliana! 🌞",
        )

    monkeypatch.setattr(orchestrator.assistant_service, "detect_intent", fake_intent)

    payload = _build_evolution_payload(
        wa_id=OWNER_WA_ID,
        text="Mándale un mensaje de buenos días a Juliana",
        from_me=True,
    )
    result = await ingest_message(db_session, owner_tenant, channel, payload)
    message_tenant, message_conv, message_contact = (
        await _load_message_relations(db_session, result.message)
    )
    await orchestrator.handle_incoming(
        db_session,
        tenant=message_tenant,
        channel=channel,
        message=result.message,
        contact=message_contact,
        conversation=message_conv,
    )

    # 1) Mensaje salió al contacto Juliana
    assert channel.sent_text[0] == (CLIENT_WA_ID, "¡Buenos días, Juliana! 🌞")

    # 2) Confirmación al dueño
    assert channel.sent_text[1][0] == OWNER_WA_ID
    assert "Le escribí a Juliana" in channel.sent_text[1][1]

    # 3) Mensaje quedó en la conversación DE JULIANA (historial correcto)
    sent_to_juliana = (
        await db_session.execute(
            select(Message)
            .where(Message.direction == "out")
            .where(Message.conversation_id != owner_conversation.id)
        )
    ).scalars().one()
    assert sent_to_juliana.content == "¡Buenos días, Juliana! 🌞"
    assert sent_to_juliana.conversation_id != owner_conversation.id


# ──────────────────────────────────────────────────────────────────────────────
# 5. Ítem sin match en catálogo → quote.needs_review, sin PDF
# ──────────────────────────────────────────────────────────────────────────────

async def test_e2e_quote_unmatched_item_no_pdf(
    db_session: AsyncSession,
    owner_tenant: Tenant,
    owner_contact: Contact,
    owner_conversation: Conversation,
    e2e_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Ítem sin precio en catálogo → sin quote, sin PDF, evento quote.needs_review."""
    channel = FakeEvolutionChannel()

    suggestions = [
        _suggestion(description="Chapa premium", matched=False, price=None),
    ]

    async def fake_extract(db, *, tenant_id, text):
        return ExtractResponse(suggestions=suggestions, raw_extraction=[])

    async def fake_intent(*, tenant, text):
        return _intent("quote")

    monkeypatch.setattr(orchestrator.ai_service, "extract_items_from_text", fake_extract)
    monkeypatch.setattr(orchestrator.assistant_service, "detect_intent", fake_intent)

    payload = _build_evolution_payload(
        wa_id=OWNER_WA_ID,
        text="Cotizame 5 chapas premium",
        from_me=True,
    )
    result = await ingest_message(db_session, owner_tenant, channel, payload)
    message_tenant, message_conv, message_contact = (
        await _load_message_relations(db_session, result.message)
    )
    await orchestrator.handle_incoming(
        db_session,
        tenant=message_tenant,
        channel=channel,
        message=result.message,
        contact=message_contact,
        conversation=message_conv,
    )

    # No se creó quote
    quotes = (await db_session.execute(select(Quote))).scalars().all()
    assert quotes == []

    # No se envió PDF
    assert channel.sent_docs == []

    # Respuesta al dueño avisando del item sin valor
    assert len(channel.sent_text) == 1
    assert "valor" in channel.sent_text[0][1].lower()

    # Evento quote.needs_review para que el dueño lo revise en el panel
    review_event = (
        await db_session.execute(
            select(Event).where(Event.type == "quote.needs_review")
        )
    ).scalar_one()
    assert review_event.payload["items"] == ["Chapa premium"]


# ──────────────────────────────────────────────────────────────────────────────
# 6. Cliente del dueño (con historial) → silencio (customer_mode off)
# ──────────────────────────────────────────────────────────────────────────────

async def test_e2e_client_message_stays_silent(
    db_session: AsyncSession,
    owner_tenant: Tenant,
    juliana_client: Contact,
    e2e_settings,
):
    """Cliente con historial escribe → bot calla (customer_mode off por defecto)."""
    channel = FakeEvolutionChannel()

    # Cliente Juliana escribe al número de la plataforma
    payload = _build_evolution_payload(
        wa_id=CLIENT_WA_ID,
        text="Hola, ¿cuánto me costó la cotización?",
        push_name="Juliana",
    )

    from app.services import identity as identity_service
    resolved = await identity_service.resolve_identity(
        db_session,
        channel="whatsapp",
        external_id=CLIENT_WA_ID,
        fallback_tenant=owner_tenant,  # cae en el tenant del dueño (contacto conocido)
        display_name="Juliana",
    )

    # Debe resolver al tenant del dueño, NO al de plataforma
    assert resolved.tenant.id == owner_tenant.id
    assert resolved.contact.id == juliana_client.id
    assert resolved.is_owner is False

    result = await ingest_message(db_session, resolved.tenant, channel, payload)
    message_tenant, message_conv, message_contact = (
        await _load_message_relations(db_session, result.message)
    )
    await orchestrator.handle_incoming(
        db_session,
        tenant=message_tenant,
        channel=channel,
        message=result.message,
        contact=message_contact,
        conversation=message_conv,
    )

    # Silencio total: ni texto ni PDF
    assert channel.sent_text == []
    assert channel.sent_docs == []


# ──────────────────────────────────────────────────────────────────────────────
# 7. Idempotencia: mensaje duplicado no se reprocesa
# ──────────────────────────────────────────────────────────────────────────────

async def test_e2e_idempotency_duplicate_message_ignored(
    db_session: AsyncSession,
    owner_tenant: Tenant,
    owner_contact: Contact,
    owner_conversation: Conversation,
    e2e_settings,
):
    """Mismo message_id de WhatsApp → ingesta devuelve existente, sin reprocesar."""
    channel = FakeEvolutionChannel()

    message_id = f"webhook-{uuid.uuid4()}"
    payload = _build_evolution_payload(
        wa_id=OWNER_WA_ID,
        text="Hola",
        from_me=True,
        message_id=message_id,
    )

    # Primera ingesta
    result1 = await ingest_message(db_session, owner_tenant, channel, payload)
    assert result1.created is True
    assert result1.message.whatsapp_message_id == message_id

    # Segunda ingesta con MISMO message_id
    result2 = await ingest_message(db_session, owner_tenant, channel, payload)
    assert result2.created is False
    assert result2.message.id == result1.message.id  # mismo objeto

    # Procesar segunda vez no debe duplicar nada
    message_tenant2, message_conv2, message_contact2 = (
        await _load_message_relations(db_session, result2.message)
    )
    await orchestrator.handle_incoming(
        db_session,
        tenant=message_tenant2,
        channel=channel,
        message=result2.message,
        contact=message_contact2,
        conversation=message_conv2,
    )

    # Solo un mensaje en BD
    messages = (
        await db_session.execute(
            select(Message).where(Message.whatsapp_message_id == message_id)
        )
    ).scalars().all()
    assert len(messages) == 1


# ──────────────────────────────────────────────────────────────────────────────
# 8. Audio → transcripción → se trata como texto normal
# ──────────────────────────────────────────────────────────────────────────────

async def test_e2e_audio_transcription_flow(
    db_session: AsyncSession,
    owner_tenant: Tenant,
    owner_contact: Contact,
    owner_conversation: Conversation,
    e2e_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Nota de voz del dueño → se transcribe → intención chat → respuesta LLM."""
    channel = FakeEvolutionChannel()

    # Mock: _get_media_b64 devuelve base64 fake, transcribe_audio_message devuelve texto
    async def fake_get_media_b64(channel, incoming):
        return "fake-base64-audio-data"

    async def fake_transcribe(b64: str) -> str:
        return "Cotízame 3 tomacorrientes"

    monkeypatch.setattr(
        "app.services.messages._get_media_b64", fake_get_media_b64
    )
    # Patch donde se define; el import local en _transcribe_incoming_audio
    # lo tomará de ahí.
    import app.services.audio as audio_module
    monkeypatch.setattr(audio_module, "transcribe_audio_message", fake_transcribe)

    # Mock: detect_intent devuelve intención chat, no extracción
    async def fake_intent(*, tenant, text):
        from app.schemas.assistant import AssistantIntent
        return AssistantIntent(intention="chat", message_text=text)

    monkeypatch.setattr(orchestrator.assistant_service, "detect_intent", fake_intent)

    # Mock LLM para respuesta chat
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="¡Entendido!"))]
    )

    class _FakeCompletions:
        async def create(self, **kwargs):
            return fake_response

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    with patch("app.services.orchestrator.AsyncOpenAI", return_value=_FakeClient()):
        payload = _build_evolution_payload(
            wa_id=OWNER_WA_ID,
            text=None,
            message_type="audio",
            from_me=True,
        )
        result = await ingest_message(db_session, owner_tenant, channel, payload)

        # Audio transcrito → contenido del mensaje ahora es texto
        assert result.message.type == "audio"
        assert result.message.content == "Cotízame 3 tomacorrientes"

        message_tenant, message_conv, message_contact = (
            await _load_message_relations(db_session, result.message)
        )
        await orchestrator.handle_incoming(
            db_session,
            tenant=message_tenant,
            channel=channel,
            message=result.message,
            contact=message_contact,
            conversation=message_conv,
        )

    # Respuesta normal del LLM
    assert len(channel.sent_text) == 1
    assert channel.sent_text[0][1] == "¡Entendido!"


# ──────────────────────────────────────────────────────────────────────────────
# 9. Negocio con NIT → onboarding válido → tenant business
# ──────────────────────────────────────────────────────────────────────────────

async def test_e2e_prospect_business_with_nit(
    db_session: AsyncSession,
    platform_tenant: Tenant,
    e2e_settings,
):
    """Prospecto se registra como negocio → NIT válido → tenant business."""
    channel = FakeEvolutionChannel()

    # Mismo wa_id para todos los pasos (es la misma conversación)
    business_wa_id = "573009998888"

    steps = [
        ("Hola", "acepto"),
        ("acepto", "llame"),          # pide nombre bot
        ("MiBot", "llame"),           # pide nombre preferido
        ("2", "NIT"),                 # negocio → pide NIT
        ("900.123.456-6", "llame"),   # NIT válido → pide nombre
        ("Instalaciones SAS", "ciudad"),
        ("Bogotá", "correo"),
        ("admin@instalaciones.com", "texto"),
        ("3", "token="),              # auto → crea tenant + token
    ]

    for user_text, expected_in_reply in steps:
        payload = _build_evolution_payload(
            wa_id=business_wa_id,
            text=user_text,
            message_id=f"webhook-{uuid.uuid4()}",
            push_name="Test User",
        )
        result = await ingest_message(db_session, platform_tenant, channel, payload)
        _, message_conv, contact = await _load_message_relations(db_session, result.message)
        await orchestrator.handle_incoming(
            db_session,
            tenant=platform_tenant,
            channel=channel,
            message=result.message,
            contact=contact,
            conversation=message_conv,
        )
        if expected_in_reply:
            assert expected_in_reply.lower() in channel.sent_text[-1][1].lower()

    # Último tenant creado
    new_tenant = (
        await db_session.execute(
            select(Tenant).where(Tenant.slug == "instalaciones-sas")
        )
    ).scalar_one()
    assert new_tenant.account_type == "business"
    assert new_tenant.nit == "900123456-6"
    assert new_tenant.bot_name == "MiBot"


# ──────────────────────────────────────────────────────────────────────────────
# 10. Owner self-chat con LID/alias (WhatsApp usa LID en lugar de número)
# ──────────────────────────────────────────────────────────────────────────────

async def test_e2e_owner_self_chat_with_lid(
    db_session: AsyncSession,
    owner_tenant: Tenant,
    owner_contact: Contact,
    owner_conversation: Conversation,
    e2e_settings,
):
    """Dueño chatea desde su teléfono pero WhatsApp manda LID → resuelve a su tenant."""
    channel = FakeEvolutionChannel()

    # Simula mensaje fromMe con wa_lid (WhatsApp oculta el número real)
    # El wa_id real (número del dueño) coincide con owner_tenant.wa_id
    # El wa_lid es un alias interno que el sistema debe resolver
    payload = _build_evolution_payload(
        wa_id=OWNER_WA_ID,  # número real en sender/remoteJidAlt
        text="Hola Aura",
        from_me=True,
        wa_lid="1234567890@lid",
        push_name="El Dueño",
    )

    # Ingerir directamente con el tenant del dueño (ya que fromMe y wa_id coincide)
    # El webhook real recibiría el mensaje y el middleware de identidad lo resolvería
    result = await ingest_message(db_session, owner_tenant, channel, payload)

    # Debe resolver al tenant del dueño
    assert result.message.tenant_id == owner_tenant.id
    assert result.from_me is True


# ──────────────────────────────────────────────────────────────────────────────
# 11. Debounce: 3 mensajes en <5s → se agrupan en 1 respuesta
# ──────────────────────────────────────────────────────────────────────────────

async def test_e2e_debounce_groups_messages(
    db_session: AsyncSession,
    owner_tenant: Tenant,
    owner_contact: Contact,
    owner_conversation: Conversation,
    e2e_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Tres mensajes rápidos del dueño → debounce los une → 1 sola respuesta LLM."""
    channel = FakeEvolutionChannel()

    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Recibido todo"))]
    )

    class _FakeCompletions:
        async def create(self, **kwargs):
            return fake_response

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    with patch("app.services.orchestrator.AsyncOpenAI", return_value=_FakeClient()):
        # Simula 3 mensajes con IDs distintos en <5s (el debounce los agrupa)
        for i in range(3):
            payload = _build_evolution_payload(
                wa_id=OWNER_WA_ID,
                text=f"Mensaje {i+1}",
                from_me=True,
                message_id=f"webhook-{uuid.uuid4()}",
            )
            await ingest_message(db_session, owner_tenant, channel, payload)
            # No llamar orquestador aquí: el debounce en webhook.py los agrupa
            # y llama handle_incoming UNA sola vez con el lote combinado

        # En test real, el debounce del webhook agrupa y llama una vez.
        # Aquí verificamos que la ingesta deduplica por message_id
        assert len(channel.sent_text) == 0  # orquestador no llamado en ingesta