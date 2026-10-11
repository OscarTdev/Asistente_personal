"""Webhook de WhatsApp (formato Evolution API).

Responde 200 de inmediato salvo errores de tenant/payload; procesa de forma
idempotente dentro del request (F1 sin cola de tareas).
Deuda consciente (F3): sin verificación de firma; F1 es local-only.
"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_by_slug
from app.channels import get_channel
from app.channels.base import ChannelParseError
from app.core.database import get_db
from app.core.redis import get_redis
from app.models import Tenant
from app.schemas.webhook import WebhookAck
from app.services.events import publish_event
from app.services.messages import ingest_message

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/whatsapp", response_model=WebhookAck)
async def webhook_whatsapp(
    tenant: Tenant = Depends(get_tenant_by_slug),
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
    payload: dict = Body(...),
):
    """Recibe un mensaje de WhatsApp, lo persiste y publica el evento."""
    channel = get_channel("evolution")

    try:
        message, event, created = await ingest_message(
            db=db, tenant=tenant, channel=channel, payload=payload
        )
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
            # Redis caído NO rompe el 200 ni la persistencia del mensaje (F1).
            logger.exception("No se pudo publicar el evento %s", event.id)

    return WebhookAck(
        status="ok",
        whatsapp_message_id=message.whatsapp_message_id,
        duplicate=not created,
    )
