"""Ingesta idempotente de mensajes entrantes."""

import logging
from typing import Any, NamedTuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel, SelfMessageIgnored
from app.models import Contact, Conversation, Event, Message, Tenant

logger = logging.getLogger(__name__)


class IngestResult(NamedTuple):
    """Resultado de la ingesta: (message, event, created)."""

    message: Message
    event: Event | None
    created: bool


async def _resolve_tenant(
    db: AsyncSession, wa_id: str, fallback: Tenant
) -> Tenant:
    """Un número de bot compartido: el remitente identifica al tenant.

    Si quien escribe es un técnico registrado (tenants.wa_id) → SU tenant
    (su historial, su catálogo, su plan). Si no → el del slug/instancia
    (comportamiento original: clientes del bot en modo instancia única).
    """
    tenant = (
        await db.execute(
            select(Tenant).where(Tenant.wa_id == wa_id, Tenant.is_active)
        )
    ).scalar_one_or_none()
    return tenant or fallback


async def ingest_message(
    db: AsyncSession,
    tenant: Tenant,
    channel: Channel,
    payload: dict[str, Any],
) -> IngestResult:
    """Procesa un mensaje entrante de forma idempotente.

    Pasos:
    0. fromMe: solo el auto-chat del dueño ("mensaje a ti mismo", remoteJid
       = su propio número = tenants.wa_id) es conversación con el asistente;
       sus respuestas manuales a terceros se ignoran. De los demás
       remitentes NO se re-routearía nada: el orquestador decide el rol.
    1. parse_incoming (ChannelParseError → 400 en el endpoint).
    2. Si el remitente no es fromMe y está registrado como dueño de un
       tenant → se enruta a SU tenant (número compartido).
    3. Dedupe por (tenant_id, whatsapp_message_id) → existente → (msg, None, False).
    4. Get-or-create Contact por (tenant_id, wa_id); rellena name si estaba NULL.
    5. Get-or-create Conversation (la más reciente del contacto) y actualizar
       last_message_at.
    6. Insert Message (direction="in") y Event "message.received" con payload
       de valores serializables (UUIDs como str).
    7. Commit; IntegrityError (carrera del UNIQUE) → rollback + re-consultar.
    """
    incoming = await channel.parse_incoming(payload)

    if incoming.from_me:
        # Escrito desde el teléfono del dueño. Solo el auto-chat
        # ("mensaje a ti mismo") es el dueño hablándole a su asistente —
        # cuando el bot corre en su propio número. Sus respuestas manuales
        # a terceros (remoteJid ≠ su número) no se ingieren.
        if not (tenant.wa_id and incoming.wa_id == tenant.wa_id):
            raise SelfMessageIgnored("Mensaje propio (fromMe) ignorado")
        # auto-chat: sigue con el tenant del slug, sin re-routear
    else:
        tenant = await _resolve_tenant(db, incoming.wa_id, tenant)

    # Dedupe por (tenant_id, whatsapp_message_id)
    stmt = (
        select(Message)
        .where(Message.tenant_id == tenant.id)
        .where(Message.whatsapp_message_id == incoming.channel_message_id)
    )
    result = await db.execute(stmt)
    existing_message = result.scalar_one_or_none()
    if existing_message:
        logger.debug(
            "Mensaje duplicado %s para tenant %s", incoming.channel_message_id, tenant.id
        )
        return IngestResult(existing_message, None, False)

    # Get-or-create Contact por (tenant_id, wa_id)
    stmt = (
        select(Contact)
        .where(Contact.tenant_id == tenant.id)
        .where(Contact.wa_id == incoming.wa_id)
    )
    result = await db.execute(stmt)
    contact = result.scalar_one_or_none()
    if contact is None:
        contact = Contact(
            tenant_id=tenant.id,
            wa_id=incoming.wa_id,
            name=incoming.push_name,
        )
        db.add(contact)
        await db.flush()
        # Sin wa_id (teléfono) en logs — dato personal (Ley 1581)
        logger.debug("Contacto creado %s (tenant %s)", contact.id, tenant.id)
    elif incoming.push_name and contact.name is None:
        contact.name = incoming.push_name
        await db.flush()
        logger.debug("Nombre del contacto %s actualizado desde push_name", contact.id)

    # Get-or-create Conversation (la más reciente del contacto)
    stmt = (
        select(Conversation)
        .where(Conversation.contact_id == contact.id)
        .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.id.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    if conversation is None:
        conversation = Conversation(
            tenant_id=tenant.id,
            contact_id=contact.id,
            status="open",
        )
        db.add(conversation)
        await db.flush()
        logger.debug("Conversación %s creada para contacto %s", conversation.id, contact.id)

    # Insert Message
    message = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction="in",
        type=incoming.message_type,
        content=incoming.text,
        whatsapp_message_id=incoming.channel_message_id,
        status="received",
    )
    db.add(message)

    # Insert Event (payload serializable: UUIDs como str, psycopg no serializa UUID en JSONB)
    event = Event(
        tenant_id=tenant.id,
        type="message.received",
        payload={
            "message_id": None,  # se reemplaza tras el flush
            "conversation_id": str(conversation.id),
            "contact_id": str(contact.id),
            "contact_wa_id": incoming.wa_id,
            "push_name": incoming.push_name,
            "direction": "in",
            "preview": (incoming.text or "")[:120] or None,
        },
    )
    db.add(event)

    try:
        await db.flush()
    except IntegrityError:
        # Carrera: otro proceso insertó el mismo (tenant_id, whatsapp_message_id)
        # entre el dedupe y el insert → rollback y devolver el existente.
        await db.rollback()
        logger.debug("IntegrityError en insert de mensaje, probable duplicado")
        stmt = (
            select(Message)
            .where(Message.tenant_id == tenant.id)
            .where(Message.whatsapp_message_id == incoming.channel_message_id)
        )
        result = await db.execute(stmt)
        existing_message = result.scalar_one_or_none()
        if existing_message is None:
            raise
        return IngestResult(existing_message, None, False)

    # Reasignar el dict (no mutar in place): JSONB sin MutableDict no detecta
    # cambios internos → el UPDATE no saldría y la BD guardaría message_id=None.
    event.payload = {**event.payload, "message_id": str(message.id)}

    # Actualizar last_message_at con el created_at del mensaje y confirmar todo
    conversation.last_message_at = message.created_at
    await db.commit()

    await db.refresh(message)
    await db.refresh(event)
    logger.debug("Mensaje %s ingerido para tenant %s", message.id, tenant.id)
    return IngestResult(message, event, True)
