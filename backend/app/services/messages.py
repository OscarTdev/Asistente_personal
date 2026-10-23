"""Ingesta idempotente de mensajes entrantes."""

import logging
from typing import Any, NamedTuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel, SelfMessageIgnored
from app.models import Conversation, Event, Message, Tenant
from app.services import identity as identity_service

logger = logging.getLogger(__name__)


class IngestResult(NamedTuple):
    """Resultado de la ingesta: (message, event, created)."""

    message: Message
    event: Event | None
    created: bool
    # De quién vino el mensaje y si es del propio teléfono del bot:
    # para marcar como leído (anti-detección de Meta) antes de responder.
    sender_wa_id: str = ""
    from_me: bool = False


logger = logging.getLogger(__name__)


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
       sus respuestas manuales a terceros se ignoran.
    1. parse_incoming (ChannelParseError → 400 en el endpoint).
    2. Resolución de identidad (channel_identities): quién escribe → su
       contacto y SU tenant, venga por WhatsApp, Telegram o la app. El
       legado de WhatsApp crea las identidades perezosamente; los
       desconocidos quedan como prospecto en el tenant del slug.
    3. Dedupe por (tenant_id, whatsapp_message_id) → existente → (msg, None, False).
    4. Get-or-create Conversation (la más reciente del contacto) y actualizar
       last_message_at.
    5. Insert Message (direction="in") y Event "message.received" con payload
       de valores serializables (UUIDs como str).
    6. Commit; IntegrityError (carrera del UNIQUE) → rollback + re-consultar.
    """
    incoming = await channel.parse_incoming(payload)

    if incoming.from_me:
        # Escrito desde el teléfono del dueño. Solo el auto-chat
        # ("mensaje a ti mismo") es el dueño hablándole a su asistente —
        # cuando el bot corre en su propio número. Sus respuestas manuales
        # a terceros (remoteJid ≠ su número) no se ingieren.
        # El número del bot puede estar registrado en CUALQUIER tenant
        # (el del dueño de la plataforma), no en el de plataforma.
        bot_owner = (
            await db.execute(
                select(Tenant).where(
                    Tenant.wa_id == incoming.wa_id, Tenant.is_active.is_(True)
                )
            )
        ).scalar_one_or_none()
        if bot_owner is None:
            raise SelfMessageIgnored("Mensaje propio (fromMe) ignorado")
        # auto-chat: resolvemos su identidad con SU tenant como fallback
        resolved = await identity_service.resolve_identity(
            db,
            channel=channel.identity_channel,
            external_id=incoming.wa_id,
            alias_external_id=incoming.wa_lid,
            fallback_tenant=bot_owner,
            display_name=incoming.push_name,
        )
    else:
        # El núcleo no depende del canal: esta identidad puede ser su número
        # de WhatsApp, su usuario de Telegram o el de la app — siempre es el
        # mismo contacto con el mismo historial. Los desconocidos caen en el
        # tenant de plataforma (la puerta de entrada).
        resolved = await identity_service.resolve_identity(
            db,
            channel=channel.identity_channel,
            external_id=incoming.wa_id,
            alias_external_id=incoming.wa_lid,
            fallback_tenant=tenant,
            display_name=incoming.push_name,
        )

    tenant = resolved.tenant
    contact = resolved.contact

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
        return IngestResult(
            existing_message,
            None,
            False,
            sender_wa_id=incoming.wa_id,
            from_me=incoming.from_me,
        )

    # El contacto viene resuelto por la identidad (mismo humano por
    # cualquier canal = mismo contacto con el mismo historial)

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

    # Transcribir audios en la ingesta (spec §12): el contenido del
    # mensaje pasa de None a texto transcrito. El debounce une el lote
    # como si fuera un mensaje de texto normal. Evolution v2 no siempre
    # incluye el base64 en el webhook: si falta, se descarga del media_url.
    if incoming.message_type == "audio":
        from app.services.audio import transcribe_audio_message

        audio_b64 = incoming.media_base64
        if not audio_b64 and incoming.media_url:
            audio_b64 = await _download_media_as_b64(incoming.media_url)
        if audio_b64:
            try:
                transcription = await transcribe_audio_message(audio_b64)
                if transcription:
                    message.content = transcription
                    logger.info(
                        "Audio transcrito para el mensaje %s (%d caracteres)",
                        incoming.channel_message_id,
                        len(transcription),
                    )
            except Exception:
                logger.warning(
                    "No se pudo transcribir el audio %s; el debounce lo tratará "
                    "como marcador de posición",
                    incoming.channel_message_id,
                )
        else:
            logger.warning(
                "Audio %s sin base64 ni URL descargable: sin transcripción",
                incoming.channel_message_id,
            )

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
        return IngestResult(
            existing_message,
            None,
            False,
            sender_wa_id=incoming.wa_id,
            from_me=incoming.from_me,
        )

    # Reasignar el dict (no mutar in place): JSONB sin MutableDict no detecta
    # cambios internos → el UPDATE no saldría y la BD guardaría message_id=None.
    event.payload = {**event.payload, "message_id": str(message.id)}

    # Actualizar last_message_at con el created_at del mensaje y confirmar todo
    conversation.last_message_at = message.created_at
    await db.commit()

    await db.refresh(message)
    await db.refresh(event)
    logger.debug("Mensaje %s ingerido para tenant %s", message.id, tenant.id)
    return IngestResult(
        message,
        event,
        True,
        sender_wa_id=incoming.wa_id,
        from_me=incoming.from_me,
    )


async def _download_media_as_b64(url: str) -> str | None:
    """Descarga la media del webhook de Evolution y la devuelve en base64.

    Evolution v2 sirve los archivos en media_url (típicamente local); el
    base64 solo viene si la instancia lo tiene habilitado en el webhook.
    """
    import base64

    import httpx

    from app.core.config import get_settings

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            if resp.status_code in (401, 403):
                # Algunas instancias exigen la apikey también para los archivos
                resp = await client.get(
                    url, headers={"apikey": get_settings().evolution_api_key}
                )
            resp.raise_for_status()
            return base64.b64encode(resp.content).decode("ascii")
    except Exception:
        logger.warning("No se pudo descargar la media %s", url[:120])
        return None
