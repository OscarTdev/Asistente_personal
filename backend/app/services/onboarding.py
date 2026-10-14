"""Onboarding: el bot es la puerta de entrada del producto.

Un número desconocido (prospecto: un técnico futuro cliente de la
plataforma) le escribe al bot → el asistente se presenta, pregunta cómo
quiere que lo llamen, registra sus datos y crea SU tenant (plan trial)
con su número como llave de enrutamiento. A partir del siguiente mensaje,
habla con su propio asistente en su propio contexto.

Los clientes de los dueños (contactos con cotizaciones o seguimientos)
nunca entran a onboarding: sus respuestas quedan registradas y el bot
permanece en silencio con ellos.
"""

import logging
import re
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.core.nit import clean_nit, validate_nit
from app.models import Contact, Conversation, Message, Tenant
from app.services.entitlements import apply_plan

logger = logging.getLogger(__name__)

# Estados del onboarding (contacts.onboarding_state)
ASK_BOT_NAME = "ask_bot_name"
# Cada estado lleva sus datos parciales tras ":" (el nombre puede traer ":",
# así que el prefijo se pela con startswith y el resto con rsplit).
ASK_ACCOUNT_TYPE_PREFIX = "ask_account_type:"
ASK_NIT_PREFIX = "ask_nit:"
ASK_OWNER_NAME_PREFIX = "ask_owner_name:"  # <bot>:<tipo de cuenta>:<nit>

_WELCOME = (
    "¡Hola! 👋 Soy tu asistente personal: te ayudo a cotizar, a escribirle "
    "a tus clientes y a que no se te escape ni un peso.\n\n"
    "¿Cómo quieres que me llame?"
)
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
    "Última pregunta: ¿cómo prefieres que te llame? "
    "(tu nombre o el de tu negocio)"
)


def _slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return value.strip("-")[:50] or "cliente"


def _services_menu(bot_name: str) -> str:
    return (
        f"¡Listo! Ya soy {bot_name} 🎉\n\n"
        "Esto es lo que puedo hacer por ti:\n\n"
        "📄 Cotizaciones — pídeme materiales con cantidades y te armo la "
        "cotización en PDF\n"
        "📨 Mensajes — «mandale un mensaje de buenos días a Juliana»\n"
        "📅 Seguimiento de cotizaciones — escribo a tus clientes a los 3 y 7 "
        "días de cada cotización enviada (con el plan Premium)\n\n"
        "¿Con qué quieres empezar?"
    )


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


async def start_onboarding(
    db: AsyncSession,
    *,
    contact: Contact,
    conversation: Conversation,
    channel: Channel,
    tenant: Tenant,
) -> None:
    """Arranca el registro conversacional de un prospecto nuevo."""
    contact.onboarding_state = ASK_BOT_NAME
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
    """Un paso del registro: nombre del bot → datos del dueño → crear tenant."""
    state = contact.onboarding_state or ""
    answer = text.strip()

    async def ask(question: str) -> None:
        await _send_out(
            db,
            tenant_id=tenant.id,
            conversation=conversation,
            channel=channel,
            wa_id=contact.wa_id,
            text=question,
        )

    if state == ASK_BOT_NAME:
        if not answer:
            await ask(_WELCOME)
            return
        bot_name = answer[:30]
        contact.onboarding_state = f"{ASK_ACCOUNT_TYPE_PREFIX}{bot_name}"
        await db.commit()
        await ask(_ASK_ACCOUNT_TYPE)
        return

    if state.startswith(ASK_ACCOUNT_TYPE_PREFIX):
        bot_name = state[len(ASK_ACCOUNT_TYPE_PREFIX) :]
        choice = answer.lower()
        business_words = ("negocio", "empresa", "compañía", "compania", "pyme")
        if "2" in choice or any(word in choice for word in business_words):
            # Negocio o empresa → se pide NIT con dígito de verificación
            contact.onboarding_state = f"{ASK_NIT_PREFIX}{bot_name}"
            await db.commit()
            await ask(_ASK_NIT)
            return
        if "1" in choice or any(word in choice for word in ("persona", "natural", "independiente")):
            # Persona natural → sin NIT, directo al nombre
            contact.onboarding_state = f"{ASK_OWNER_NAME_PREFIX}{bot_name}:personal:"
            await db.commit()
            await ask(_ASK_NAME)
            return
        await ask(_ASK_ACCOUNT_TYPE)
        return

    if state.startswith(ASK_NIT_PREFIX):
        bot_name = state[len(ASK_NIT_PREFIX) :]
        if answer.lower().strip(" .") in ("despues", "después", "luego", "nose", "no sé"):
            contact.onboarding_state = f"{ASK_OWNER_NAME_PREFIX}{bot_name}:business:"
            await db.commit()
            await ask(_ASK_NAME)
            return
        if not validate_nit(answer):
            await ask(_NIT_RETRY)
            return
        nit = clean_nit(answer)
        contact.onboarding_state = f"{ASK_OWNER_NAME_PREFIX}{bot_name}:business:{nit}"
        await db.commit()
        await ask(_ASK_NAME)
        return

    if state.startswith(ASK_OWNER_NAME_PREFIX):
        rest = state[len(ASK_OWNER_NAME_PREFIX) :]
        bot_name, account_type, nit = rest.rsplit(":", 2)
        if not answer:
            await ask("¿Me repites tu nombre o el de tu negocio?")
            return

        owner_name = answer[:60]
        slug = await _unique_slug(db, owner_name)
        new_tenant = Tenant(
            name=owner_name,
            slug=slug,
            bot_name=bot_name,
            wa_id=contact.wa_id,
            account_type=account_type,
            nit=nit or None,
        )
        db.add(new_tenant)
        await db.flush()

        # Plan trial: su cotizador queda activo con el contrato de planes
        await apply_plan(
            db, tenant_id=new_tenant.id, plan="trial", provider="system"
        )

        # Deja de ser el contacto-puerta de la plataforma: su identidad de
        # prospecto se limpia para que su próximo mensaje lo routee a SU
        # tenant como dueño (y no al fallback como prospecto).
        from app.services.identity import clear_identities

        await clear_identities(
            db, channel="whatsapp", external_id=contact.wa_id
        )

        contact.onboarding_state = None
        await db.commit()
        await ask(_services_menu(bot_name))
        logger.info(
            "Tenant '%s' creado por onboarding (dueño registrado por wa_id)", slug
        )
        return
