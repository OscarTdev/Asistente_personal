"""Webhook de WhatsApp (formato Evolution API).

Responde 200 de inmediato; el cerebro conversacional corre en background.
Deduplicación idempotente dentro del request. Deuda consciente: sin
verificación de firma (F1 local-only) — pendiente para producción.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_by_slug
from app.channels import get_channel
from app.channels.base import ChannelParseError, SelfMessageIgnored
from app.core.database import SessionFactory, get_db
from app.core.redis import get_redis
from app.models import Contact, Conversation, Message, Tenant
from app.schemas.webhook import WebhookAck
from app.services.events import publish_event
from app.services.messages import ingest_message

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/whatsapp", response_model=WebhookAck)
async def webhook_whatsapp(
    background_tasks: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant_by_slug),
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
    payload: dict = Body(...),
):
    """Recibe un mensaje de WhatsApp, lo persiste y dispara el cerebro."""
    channel = get_channel("evolution")

    try:
        message, event, created = await ingest_message(
            db=db, tenant=tenant, channel=channel, payload=payload
        )
    except SelfMessageIgnored:
        # Mensaje escrito a mano desde el teléfono del bot: se acusa y se ignora
        return WebhookAck(status="ignored", whatsapp_message_id="self", duplicate=False)
    except ChannelParseError as exc:
        logger.debug("Payload de webhook inválido para tenant %s", tenant.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload de webhook inválido",
        ) from exc

    if created and event is not None:
        try:
            await publish_event(redis_client, tenant.id, event)
        except Exception:
            # Redis caído NO rompe el 200 ni la persistencia del mensaje.
            logger.exception("No se pudo publicar el evento %s", event.id)

        # El cerebro conversacional corre en background: el cliente no espera
        background_tasks.add_task(_run_orchestrator, tenant.id, message.id)

    return WebhookAck(
        status="ok",
        whatsapp_message_id=message.whatsapp_message_id,
        duplicate=not created,
    )


async def _run_orchestrator(tenant_id, message_id) -> None:
    """Ejecuta el cerebro con su propia sesión (la del request ya cerró)."""
    from app.services.orchestrator import handle_incoming

    try:
        async with SessionFactory() as db:
            tenant = (
                await db.execute(select(Tenant).where(Tenant.id == tenant_id))
            ).scalar_one()
            message = (
                await db.execute(select(Message).where(Message.id == message_id))
            ).scalar_one()
            conversation = (
                await db.execute(
                    select(Conversation).where(
                        Conversation.id == message.conversation_id
                    )
                )
            ).scalar_one()
            contact = (
                await db.execute(
                    select(Contact).where(Contact.id == conversation.contact_id)
                )
            ).scalar_one()

            channel = get_channel("evolution")
            await handle_incoming(
                db,
                tenant=tenant,
                channel=channel,
                message=message,
                contact=contact,
                conversation=conversation,
            )
    except Exception:
        logger.exception(
            "El orquestador falló para el mensaje %s del tenant %s", message_id, tenant_id
        )
