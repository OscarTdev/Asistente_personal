"""Tests de la Fase 3: registro completo con consentimiento y token.

- El consentimiento se registra antes de pedir cualquier dato (Ley 1581)
- Ciudad, correo y preferencia de respuesta se piden paso a paso
- El enlace de un solo uso crea la contraseña del panel (D7): jamás por chat
- La máquina de estados vive en onboarding_sessions (JSONB, reanudable)
"""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Consent,
    Contact,
    Conversation,
    Message,
    OnboardingSession,
    Tenant,
    User,
)
from app.services import orchestrator


async def _say_raw(db_session, tenant, chat, channel, text: str) -> None:
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


class FakeChannel:
    name = "fake"
    identity_channel = "whatsapp"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def parse_incoming(self, payload):
        raise NotImplementedError

    async def send_text(self, to: str, text: str) -> str | None:
        self.sent.append((to, text))
        return None


@pytest.fixture
def bot_settings(monkeypatch: pytest.MonkeyPatch):
    stub = SimpleNamespace(
        evolution_api_key="test-key",
        panel_base_url="http://localhost:5173",
    )
    monkeypatch.setattr("app.services.orchestrator.get_settings", lambda: stub)
    monkeypatch.setattr("app.services.onboarding.get_settings", lambda: stub)


async def _seed_prospect(
    db_session: AsyncSession, tenant: Tenant, wa_id: str = "573009997777"
) -> dict:
    contact = Contact(tenant_id=tenant.id, wa_id=wa_id, name="Prospecto")
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
        content="Hola",
        whatsapp_message_id=f"in-{uuid.uuid4()}",
        status="received",
    )
    db_session.add(message)
    await db_session.commit()
    return {"contact": contact, "conversation": conversation, "message": message}


async def _say(
    db_session, tenant, chat, channel, text
):
    await _say_raw(db_session, tenant, chat, channel, text)


async def test_full_onboarding_with_consent_city_email_and_token(
    db_session: AsyncSession, tenant: Tenant, bot_settings
):
    """El registro completo: consentimiento → datos → tenant + enlace."""
    channel = FakeChannel()
    chat = await _seed_prospect(db_session, tenant)

    # 1) Bienvenida + consentimiento
    await orchestrator.handle_incoming(
        db_session, tenant=tenant, channel=channel,
        message=chat["message"], contact=chat["contact"],
        conversation=chat["conversation"],
    )
    assert "acepto" in channel.sent[0][1].lower()
    await db_session.refresh(chat["contact"])
    assert chat["contact"].onboarding_state == "in_progress"

    # 2) Acepta → pide nombre del bot
    await _say(db_session, tenant, chat, channel, "acepto")
    assert "llame" in channel.sent[-1][1].lower()

    # El consentimiento quedó registrado (Ley 1581)
    consent = (
        await db_session.execute(select(Consent))
    ).scalars().one()
    assert consent.consent_type == "privacy_policy"
    assert consent.contact_id == chat["contact"].id

    # 3) Nombre del bot → nombre preferido del dueño
    await _say(db_session, tenant, chat, channel, "Aura")
    assert "llame" in channel.sent[-1][1].lower()

    # 4) Persona natural → SIN NIT, pide nombre
    await _say(db_session, tenant, chat, channel, "1")
    assert "llame" in channel.sent[-1][1].lower()

    # 5) Nombre → ciudad
    await _say(db_session, tenant, chat, channel, "Juan Pérez")
    assert "ciudad" in channel.sent[-1][1].lower()

    # 6) Ciudad → correo
    await _say(db_session, tenant, chat, channel, "Medellín")
    assert "correo" in channel.sent[-1][1].lower()

    # 7) Correo → preferencia de respuesta
    await _say(db_session, tenant, chat, channel, "juan@ejemplo.com")
    assert "texto" in channel.sent[-1][1].lower()
    assert "audio" in channel.sent[-1][1].lower()

    # 8) Preferencia → crea el tenant + enlace de contraseña
    await _say(db_session, tenant, chat, channel, "1")

    new_tenant = (
        await db_session.execute(
            select(Tenant).where(Tenant.slug == "juan-perez")
        )
    ).scalar_one()
    assert new_tenant.wa_id == "573009997777"
    assert new_tenant.account_type == "personal"
    assert new_tenant.bot_name == "Aura"

    # El enlace de la contraseña está en el mensaje final
    final_message = channel.sent[-1][1]
    assert "crear-contrasena" in final_message or "contraseña" in final_message.lower()
    assert "token=" in final_message

    # La sesión de onboarding quedó cerrada
    sessions = (
        await db_session.execute(
            select(OnboardingSession).where(
                OnboardingSession.contact_id == chat["contact"].id
            )
        )
    ).scalars().all()
    assert len(sessions) == 1
    assert sessions[0].is_active is False

    await db_session.refresh(chat["contact"])
    assert chat["contact"].onboarding_state is None


async def test_onboarding_business_with_nit(
    db_session: AsyncSession, tenant: Tenant, bot_settings
):
    """Negocio: pide NIT después del tipo de cuenta."""
    channel = FakeChannel()
    chat = await _seed_prospect(db_session, tenant, wa_id="573009996666")

    async def _say(text: str) -> None:
        await _say_raw(db_session, tenant, chat, channel, text)

    await orchestrator.handle_incoming(
        db_session, tenant=tenant, channel=channel,
        message=chat["message"], contact=chat["contact"],
        conversation=chat["conversation"],
    )
    await _say("acepto")
    await _say("Chispa")
    await _say("2")  # negocio

    # Debe pedir el NIT
    assert "NIT" in channel.sent[-1][1]

    # NIT válido → pide el nombre
    await _say("900.123.456-6")
    assert "llame" in channel.sent[-1][1].lower()

    # Completa el resto
    await _say("Instalaciones SAS")
    await _say("Cali")
    await _say("admin@instalaciones.com")
    await _say("3")  # automático

    new_tenant = (
        await db_session.execute(
            select(Tenant).where(Tenant.slug == "instalaciones-sas")
        )
    ).scalar_one()
    assert new_tenant.account_type == "business"
    assert new_tenant.nit == "900123456-6"


async def test_onboarding_new_order_uses_preferred_name_and_real_email(
    db_session: AsyncSession, tenant: Tenant, bot_settings
):
    """El flujo nuevo pregunta trato, tipo y correo en el orden acordado."""
    channel = FakeChannel()
    chat = await _seed_prospect(db_session, tenant, wa_id="573009996555")

    await orchestrator.handle_incoming(
        db_session, tenant=tenant, channel=channel,
        message=chat["message"], contact=chat["contact"],
        conversation=chat["conversation"],
    )
    for answer in ("acepto", "Chispa", "Oscar", "1", "oscar@example.com", "1"):
        await _say_raw(db_session, tenant, chat, channel, answer)

    new_tenant = (
        await db_session.execute(
            select(Tenant).where(Tenant.slug == "oscar")
        )
    ).scalar_one()
    user = (
        await db_session.execute(
            select(User).where(User.tenant_id == new_tenant.id)
        )
    ).scalar_one()

    assert new_tenant.bot_name == "Chispa"
    assert chat["contact"].name == "Oscar"
    assert user.email == "oscar@example.com"
    assert user.full_name == "Oscar"
    assert user.is_active is False


async def test_onboarding_session_is_resumable(
    db_session: AsyncSession, tenant: Tenant, bot_settings
):
    """La sesión sobrevive entre mensajes: los datos parciales no se pierden."""
    channel = FakeChannel()
    chat = await _seed_prospect(db_session, tenant)

    await orchestrator.handle_incoming(
        db_session, tenant=tenant, channel=channel,
        message=chat["message"], contact=chat["contact"],
        conversation=chat["conversation"],
    )
    await _say(db_session, tenant, chat, channel, "acepto")
    await _say(db_session, tenant, chat, channel, "Mi Bot")
    await _say(db_session, tenant, chat, channel, "1")  # persona natural

    # La sesión tiene los datos parciales
    session = (
        await db_session.execute(
            select(OnboardingSession).where(
                OnboardingSession.contact_id == chat["contact"].id,
                OnboardingSession.is_active.is_(True),
            )
        )
    ).scalar_one()
    assert session.data["bot_name"] == "Mi Bot"
    assert session.data["account_type"] == "personal"
    assert session.step == "owner_name"

    # Reanuda y completa
    await _say(db_session, tenant, chat, channel, "Juan")
    await _say(db_session, tenant, chat, channel, "Bogotá")
    await _say(db_session, tenant, chat, channel, "j@j.com")
    await _say(db_session, tenant, chat, channel, "1")

    new_tenant = (
        await db_session.execute(
            select(Tenant).where(Tenant.slug == "juan")
        )
    ).scalar_one()
    assert new_tenant.bot_name == "Mi Bot"


async def test_consent_required_before_any_data(
    db_session: AsyncSession, tenant: Tenant, bot_settings
):
    """Sin aceptar, el bot re-pregunta el consentimiento — no pasa nada más."""
    channel = FakeChannel()
    chat = await _seed_prospect(db_session, tenant)

    await orchestrator.handle_incoming(
        db_session, tenant=tenant, channel=channel,
        message=chat["message"], contact=chat["contact"],
        conversation=chat["conversation"],
    )
    # Responde con basura: el bot insiste en el consentimiento
    await _say(db_session, tenant, chat, channel, "no quiero")
    assert "acepto" in channel.sent[-1][1].lower()

    # No se creó ninguna sesión de datos aún (sigue en consent)
    session = (
        await db_session.execute(
            select(OnboardingSession).where(
                OnboardingSession.contact_id == chat["contact"].id
            )
        )
    ).scalar_one()
    assert session.step == "consent"
