"""Onboarding: el bot es la puerta de entrada del producto.

Un número desconocido (prospecto: un técnico futuro cliente de la
plataforma) le escribe al bot → el asistente se presenta, pregunta cómo
quiere que lo llamen, registra sus datos paso a paso y crea SU tenant
(plan trial) con su número como llave de enrutamiento. Al terminar,
ofrece sus servicios y le envía el enlace para crear la contraseña del
panel — NUNCA se pide la contraseña por chat (D7).

La máquina de estados vive en `onboarding_sessions` (paso actual +
datos acumulados en JSONB, expiración, reanudable). El contacto del
prospecto vive en el tenant de plataforma; el nuevo dueño queda routado
a su propio contexto desde el siguiente mensaje.
"""

import logging
import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.core.config import get_settings
from app.core.nit import clean_nit, validate_nit
from app.models import (
    Consent,
    Contact,
    Conversation,
    Message,
    OnboardingSession,
    Tenant,
)
from app.services.entitlements import apply_plan

logger = logging.getLogger(__name__)

# Expiración de la sesión de onboarding: 24 horas para completar el registro
SESSION_TTL = timedelta(hours=24)
# Expiración del enlace de un solo uso para la contraseña
PASSWORD_TOKEN_MINUTES = 30

# Versión de la política de privacidad que se acepta
POLICY_VERSION = "1.0"

_WELCOME = (
    "¡Hola! 👋 Soy tu asistente personal: te ayudo a cotizar, a escribirle "
    "a tus clientes y a que no se te escape ni un peso.\n\n"
    "Antes de empezar, necesito que aceptes nuestra política de "
    "tratamiento de datos (Ley 1581). Es rápida, lo prometo.\n\n"
    "Responde «acepto» para continuar."
)
_CONSENT_ASKED = (
    "Para registrarte necesito tu consentimiento para el tratamiento de "
    "tus datos personales. Responde «acepto» para continuar."
)
_ASK_BOT_NAME = "¡Gracias! ¿Cómo quieres que me llame?"
_ASK_ACCOUNT_TYPE = (
    "¡Un gusto! Antes de empezar: ¿eres 1️⃣ persona natural "
    "o 2️⃣ negocio o empresa? (Responde 1 o 2)"
)
_ASK_NIT = (
    "¿Cuál es el NIT de la empresa? Escríbelo con el dígito de "
    "verificación (ej: 900.123.456-7). Si no lo tienes a mano, "
    "escribe «después»."
)
_NIT_RETRY = (
    "No pude validar ese NIT. Revisa el dígito de verificación "
    "(ej: 900.123.456-7) o escribe «después» para dejarlo pendiente."
)
_ASK_NAME = (
    "¿Cómo prefieres que te llame? "
    "(tu nombre o el de tu negocio)"
)
_ASK_CITY = "¿En qué ciudad operas? (ej: Medellín, Bogotá, Cali)"
_ASK_EMAIL = (
    "¿Cuál es tu correo electrónico? Te enviaremos la cotizaciones "
    "y el acceso al panel. (Si no tienes ahora, escribe «después»)"
)
_EMAIL_RETRY = "Ese correo no parece válido. Revísalo o escribe «después»."
_ASK_RESPONSE_PREF = (
    "Última pregunta: ¿prefieres que te responda por 1️⃣ texto, "
    "2️⃣ audio o 3️⃣ automático? (Responde 1, 2 o 3)"
)
_PANEL_LINK_TEMPLATE = (
    "¡Listo! Ya soy {bot_name} 🎉\n\n"
    "Tu cuenta está creada. Esto es lo que puedo hacer por ti:\n\n"
    "📄 Cotizaciones — pídeme materiales con cantidades y te armo la "
    "cotización en PDF\n"
    "📨 Mensajes — «mandale un mensaje de buenos días a Juliana»\n"
    "📅 Seguimiento de cotizaciones — escribo a tus clientes a los 3 y 7 "
    "días (con el plan Premium)\n\n"
    "Para acceder a tu panel de administración y configurar tu "
    "catálogo, crea tu contraseña aquí (vence en 30 minutos):\n\n"
    "{panel_url}\n\n"
    "¿Con qué quieres empezar?"
)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return value.strip("-")[:50] or "cliente"


async def _send_out(
    db: AsyncSession,
    *,
    tenant_id,
    conversation: Conversation,
    channel: Channel,
    wa_id: str,
    text: str,
) -> None:
    """Envía y persiste; el id real deduplica el eco del webhook."""
    sent_id = await channel.send_text(wa_id, text)
    db.add(
        Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction="out",
            type="text",
            content=text,
            whatsapp_message_id=sent_id or f"bot-{uuid.uuid4()}",
            status="sent",
        )
    )
    await db.commit()


async def _unique_slug(db: AsyncSession, base: str) -> str:
    slug = _slugify(base)
    candidate = slug
    suffix = 2
    while True:
        exists = (
            await db.execute(select(Tenant).where(Tenant.slug == candidate))
        ).scalar_one_or_none()
        if exists is None:
            return candidate
        candidate = f"{slug}-{suffix}"
        suffix += 1


def _generate_panel_token(tenant_id) -> str:
    """Token de un solo uso para crear la contraseña del panel (D7).

    JWT con caducidad corta: NUNCA se pide la contraseña por chat.
    """
    from app.core.security import create_access_token

    # El token lleva el propósito + el tenant aún no existe: usamos un
    # identificador efímero ligado al número del dueño
    return create_access_token(
        user_id=uuid.UUID(int=0),  # no es un usuario real
        tenant_id=tenant_id,
        role="onboarding",
        expires_delta=timedelta(minutes=PASSWORD_TOKEN_MINUTES),
    )


async def _get_or_create_session(
    db: AsyncSession, *, contact: Contact
) -> OnboardingSession:
    """Obtiene la sesión activa del contacto o crea una nueva."""
    session = (
        await db.execute(
            select(OnboardingSession)
            .where(
                OnboardingSession.contact_id == contact.id,
                OnboardingSession.is_active.is_(True),
                OnboardingSession.expires_at > datetime.now(UTC),
            )
            .order_by(OnboardingSession.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if session is not None:
        return session
    session = OnboardingSession(
        contact_id=contact.id,
        step="consent",
        data={},
        expires_at=datetime.now(UTC) + SESSION_TTL,
    )
    db.add(session)
    await db.flush()
    return session


async def start_onboarding(
    db: AsyncSession,
    *,
    contact: Contact,
    conversation: Conversation,
    channel: Channel,
    tenant: Tenant,
) -> None:
    """Arranca el registro conversacional de un prospecto nuevo."""
    # Marca el contacto para que el orquestador sepa que está en onboarding
    contact.onboarding_state = "in_progress"
    await db.commit()

    # Crea (o reusa) la sesión
    await _get_or_create_session(db, contact=contact)
    await db.commit()

    await _send_out(
        db,
        tenant_id=tenant.id,
        conversation=conversation,
        channel=channel,
        wa_id=contact.wa_id,
        text=_WELCOME,
    )
    logger.info("Onboarding iniciado (contacto %s)", contact.id)


async def continue_onboarding(
    db: AsyncSession,
    *,
    contact: Contact,
    conversation: Conversation,
    channel: Channel,
    tenant: Tenant,
    text: str,
) -> None:
    """Un paso del registro: cada respuesta avanza la máquina de estados."""
    session = await _get_or_create_session(db, contact=contact)
    answer = text.strip()
    data: dict[str, Any] = dict(session.data or {})

    async def ask(question: str) -> None:
        await _send_out(
            db,
            tenant_id=tenant.id,
            conversation=conversation,
            channel=channel,
            wa_id=contact.wa_id,
            text=question,
        )

    async def save_step(step: str) -> None:
        session.step = step
        session.data = data
        await db.commit()

    # ── Paso: consentimiento ─────────────────────────────────────────────
    if session.step == "consent":
        if answer.lower().strip(" .!") in ("acepto", "aceptar", "si", "sí", "ok"):
            # Registrar el consentimiento (Ley 1581)
            db.add(
                Consent(
                    tenant_id=tenant.id,
                    contact_id=contact.id,
                    consent_type="privacy_policy",
                    policy_version=POLICY_VERSION,
                    channel="whatsapp",
                )
            )
            await save_step("bot_name")
            await ask(_ASK_BOT_NAME)
            return
        await ask(_CONSENT_ASKED)
        return

    # ── Paso: nombre del asistente ───────────────────────────────────────
    if session.step == "bot_name":
        if not answer:
            await ask(_ASK_BOT_NAME)
            return
        data["bot_name"] = answer[:30]
        await save_step("account_type")
        await ask(_ASK_ACCOUNT_TYPE)
        return

    # ── Paso: tipo de cuenta ────────────────────────────────────────────
    if session.step == "account_type":
        choice = answer.lower()
        business_words = ("negocio", "empresa", "compañía", "compania", "pyme")
        if "2" in choice or any(word in choice for word in business_words):
            data["account_type"] = "business"
            await save_step("nit")
            await ask(_ASK_NIT)
            return
        if "1" in choice or any(word in choice for word in ("persona", "natural", "independiente")):
            data["account_type"] = "personal"
            await save_step("owner_name")
            await ask(_ASK_NAME)
            return
        await ask(_ASK_ACCOUNT_TYPE)
        return

    # ── Paso: NIT (solo negocio) ─────────────────────────────────────────
    if session.step == "nit":
        if answer.lower().strip(" .") in ("despues", "después", "luego", "nose", "no sé"):
            data["nit"] = None
            await save_step("owner_name")
            await ask(_ASK_NAME)
            return
        if not validate_nit(answer):
            await ask(_NIT_RETRY)
            return
        data["nit"] = clean_nit(answer)
        await save_step("owner_name")
        await ask(_ASK_NAME)
        return

    # ── Paso: nombre del dueño ──────────────────────────────────────────
    if session.step == "owner_name":
        if not answer:
            await ask("¿Me repites tu nombre o el de tu negocio?")
            return
        data["owner_name"] = answer[:60]
        await save_step("city")
        await ask(_ASK_CITY)
        return

    # ── Paso: ciudad ────────────────────────────────────────────────────
    if session.step == "city":
        if not answer:
            await ask(_ASK_CITY)
            return
        data["city"] = answer[:50]
        await save_step("email")
        await ask(_ASK_EMAIL)
        return

    # ── Paso: correo ─────────────────────────────────────────────────────
    if session.step == "email":
        if answer.lower().strip(" .") in ("despues", "después", "luego", "nose", "no sé"):
            data["email"] = None
            await save_step("response_pref")
            await ask(_ASK_RESPONSE_PREF)
            return
        if not _EMAIL_RE.match(answer):
            await ask(_EMAIL_RETRY)
            return
        data["email"] = answer.lower()[:100]
        await save_step("response_pref")
        await ask(_ASK_RESPONSE_PREF)
        return

    # ── Paso: preferencia de respuesta ───────────────────────────────────
    if session.step == "response_pref":
        choice = answer.lower()
        if "1" in choice or "texto" in choice:
            data["response_pref"] = "text"
        elif "2" in choice or "audio" in choice:
            data["response_pref"] = "audio"
        else:
            data["response_pref"] = "auto"
        await save_step("create")
        # Fall through al paso final
        session.step = "create"
        session.data = data
        await db.commit()

    # ── Paso final: crear el tenant ─────────────────────────────────────
    if session.step == "create":
        owner_name = data.get("owner_name", "Cliente")
        slug = await _unique_slug(db, owner_name)
        new_tenant = Tenant(
            name=owner_name,
            slug=slug,
            bot_name=data.get("bot_name", "Aura"),
            wa_id=contact.wa_id,
            account_type=data.get("account_type", "personal"),
            nit=data.get("nit"),
        )
        db.add(new_tenant)
        await db.flush()

        # Plan trial: su cotizador queda activo con el contrato de planes
        await apply_plan(
            db, tenant_id=new_tenant.id, plan="trial", provider="system"
        )

        # Deja de ser el contacto-puerta de la plataforma
        from app.services.identity import clear_identities

        await clear_identities(
            db, channel="whatsapp", external_id=contact.wa_id
        )

        # Cerrar la sesión de onboarding
        session.is_active = False
        contact.onboarding_state = None
        await db.commit()

        # Generar el enlace de un solo uso para crear la contraseña (D7)
        settings = get_settings()
        token = _generate_panel_token(new_tenant.id)
        panel_url = f"{settings.panel_base_url}/crear-contrasena?token={token}"

        bot_name = data.get("bot_name", "Aura")
        await ask(_PANEL_LINK_TEMPLATE.format(
            bot_name=bot_name,
            panel_url=panel_url,
        ))
        logger.info(
            "Tenant '%s' creado por onboarding (dueño registrado por wa_id)", slug
        )
        return
