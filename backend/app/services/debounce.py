"""Agrupación de mensajes (debounce): varios mensajes seguidos = una respuesta.

Spec §7 — comportamiento:
- El webhook guarda el mensaje, lo registra en el lote de su conversación
  y responde 200 de inmediato.
- El lote se procesa cuando pasan `debounce_seconds` sin mensajes nuevos
  (tope: `debounce_max_wait` desde el primero, para no dejar sin respuesta
  a quien escribe sin parar).
- Candado por conversación: un solo lote en proceso a la vez. Los mensajes
  que llegan mientras se procesa forman el siguiente lote.
- Redis caído no rompe el webhook: el llamador procesa directo sin agrupar.

El scheduler vive en el proceso web (asyncio); la migración a ARQ (Fase 9)
no cambia la lógica: register/process ya son funciones de cola.
"""

import asyncio
import logging
import time
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select

from app.channels import get_channel
from app.core.config import get_settings
from app.core.database import SessionFactory
from app.models import Contact, Conversation, Message, Tenant
from app.services.orchestrator import handle_incoming

logger = logging.getLogger(__name__)

# Chequeos agendados por conversación (viven en este proceso)
_pending: dict[str, asyncio.Task] = {}


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def _close(client: Redis) -> None:
    try:
        await client.aclose()
    except AttributeError:  # redis-py antiguo
        await client.close()


def _should_process(
    quiet: float, waited: float, debounce: float, max_wait: float
) -> bool:
    """¿Se procesa el lote ahora?

    - Silencio de `debounce` segundos → sí.
    - Tope de `max_wait` desde el primer mensaje → sí (no esperar para siempre).
    """
    if waited >= max_wait:
        return True
    return quiet >= debounce


def _merge_messages(messages: list[Message]) -> str:
    """Une el lote en un solo texto, en orden.

    El contenido sin texto (audios pendientes de transcripción, imágenes)
    entra como marcador de posición en su posición.
    """
    parts: list[str] = []
    for message in messages:
        content = (message.content or "").strip()
        parts.append(content if content else f"[{message.type}]")
    return "\n".join(parts)


def _schedule(conversation_id: str, delay: float) -> None:
    pending = _pending.get(conversation_id)
    if pending is not None and not pending.done():
        # El chequeo ya agendado re-evalúa el silencio cuando se dispare:
        # mensajes nuevos solo actualizan last:{conv}
        return
    task = asyncio.create_task(_check(conversation_id, delay))
    _pending[conversation_id] = task
    task.add_done_callback(lambda t: _pending.pop(conversation_id, None))


async def register_message(
    *, tenant_id: UUID, conversation_id: UUID, message_id: UUID
) -> None:
    """Webhook: registra el mensaje en el lote y agenda el procesamiento."""
    settings = get_settings()
    client = _redis()
    try:
        now = time.time()
        await client.rpush(f"batch:{conversation_id}", str(message_id))
        await client.set(f"last:{conversation_id}", now)
        await client.set(f"first:{conversation_id}", now, nx=True)
        _schedule(str(conversation_id), float(settings.debounce_seconds))
    finally:
        await _close(client)


async def _check(conversation_id: str, delay: float) -> None:
    await asyncio.sleep(delay)
    settings = get_settings()
    client = _redis()
    try:
        first = await client.get(f"first:{conversation_id}")
        last = await client.get(f"last:{conversation_id}")
        if first is None or last is None:
            return
        now = time.time()
        quiet = now - float(last)
        waited = now - float(first)
        if not _should_process(
            quiet,
            waited,
            float(settings.debounce_seconds),
            float(settings.debounce_max_wait),
        ):
            # Aún hay tráfico: esperar el silencio restante
            remaining = max(0.05, float(settings.debounce_seconds) - quiet)
            _schedule(conversation_id, remaining)
            return
        await process_now(UUID(conversation_id))
    finally:
        await _close(client)


async def process_now(conversation_id: UUID) -> int:
    """Procesa el lote de la conversación (candado por conversación).

    Devuelve cuántos mensajes se tomaron del lote. Si otro proceso tiene
    el candado, los mensajes quedan para su ciclo.
    """
    client = _redis()
    try:
        lock_key = f"lock:{conversation_id}"
        got_lock = await client.set(lock_key, "1", nx=True, ex=300)
        if not got_lock:
            return 0  # otro lote en proceso; el resto se toma en su ciclo
        try:
            ids = await client.lrange(f"batch:{conversation_id}", 0, -1)
            if ids:
                await client.delete(f"batch:{conversation_id}")
            await client.delete(f"first:{conversation_id}")
        finally:
            await client.delete(lock_key)
    finally:
        await _close(client)

    if not ids:
        return 0
    await _run_batch(conversation_id, [UUID(value) for value in ids])
    return len(ids)


async def _run_batch(conversation_id, message_ids: list[UUID]) -> None:
    """Ejecuta el cerebro sobre el lote unificado con su propia sesión."""
    conv_id = conversation_id if isinstance(conversation_id, UUID) else UUID(conversation_id)
    async with SessionFactory() as db:
        conversation = (
            await db.execute(
                select(Conversation).where(Conversation.id == conv_id)
            )
        ).scalar_one_or_none()
        if conversation is None:
            return
        tenant = (
            await db.execute(
                select(Tenant).where(Tenant.id == conversation.tenant_id)
            )
        ).scalar_one()
        contact = (
            await db.execute(
                select(Contact).where(Contact.id == conversation.contact_id)
            )
        ).scalar_one()
        messages = (
            (
                await db.execute(
                    select(Message)
                    .where(Message.id.in_(message_ids))
                    .order_by(Message.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        if not messages:
            return
        merged = _merge_messages(list(messages))
        if not merged:
            return
        channel = get_channel("evolution")
        await handle_incoming(
            db,
            tenant=tenant,
            channel=channel,
            message=messages[-1],
            contact=contact,
            conversation=conversation,
            text_override=merged,
        )
        logger.debug("Lote de %d mensajes procesado en %s", len(messages), conversation_id)
