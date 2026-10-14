"""Webhook de WhatsApp (formato Evolution API).

Responde 200 de inmediato; el cerebro conversacional corre en background.
Deduplicación idempotente dentro del request. Deuda consciente: sin
verificación de firma (F1 local-only) — pendiente para producción.

Webhook de pagos de MercadoPago: verifica la firma, responde 200 y procesa
en background (consulta el pago a la API de MP y aplica el plan del tenant
que pagó — sin afectar a los demás).
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_platform_tenant, verify_webhook_secret
from app.channels import get_channel
from app.channels.base import ChannelParseError, SelfMessageIgnored
from app.core.config import get_settings
from app.core.database import SessionFactory, get_db
from app.core.redis import get_redis
from app.models import (
    Contact,
    Conversation,
    Message,
    Tenant,
)
from app.schemas.webhook import WebhookAck
from app.services.events import publish_event
from app.services.mercadopago import PaymentSignatureError, verify_signature
from app.services.messages import ingest_message

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/whatsapp", response_model=WebhookAck)
async def webhook_whatsapp(
    background_tasks: BackgroundTasks,
    tenant: Tenant = Depends(get_platform_tenant),
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
    payload: dict = Body(...),
    _webhook_auth: None = Depends(verify_webhook_secret),
):
    """Recibe un mensaje de WhatsApp, lo persiste y dispara el cerebro.

    Fail-closed: sin el secreto compartido (cabecera X-Webhook-Secret
    configurada en la instancia de Evolution) la puerta no abre.

    Con UN número compartido no hay X-Tenant-Slug: el remitente se resuelve
    por su número (channel_identities); los desconocidos caen en el tenant
    de plataforma (onboarding y soporte).
    """
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

        # El cerebro corre con agrupación (spec §7): varios mensajes seguidos
        # de la misma conversación se procesan como uno solo tras una pausa.
        # Redis caído → procesamiento directo sin agrupar.
        background_tasks.add_task(
            _process_message, tenant.id, message.conversation_id, message.id
        )

    return WebhookAck(
        status="ok",
        whatsapp_message_id=message.whatsapp_message_id,
        duplicate=not created,
    )


async def _process_message(
    tenant_id, conversation_id, message_id
) -> None:
    """Registra el mensaje en el lote con espera de 5 s (spec §7).

    Si Redis no está disponible, procesa directo: la respuesta inmediata
    es mejor que ninguna.
    """
    from app.services import debounce

    try:
        await debounce.register_message(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            message_id=message_id,
        )
    except Exception:
        logger.exception(
            "Agrupación no disponible (¿Redis caído?); procesando directo"
        )
        await _run_orchestrator(tenant_id, message_id)


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


@router.post("/payments/mercadopago")
async def webhook_mercadopago(
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict:
    """Notificación de pago de MercadoPago.

    Verifica la firma (HMAC con MERCADOPAGO_WEBHOOK_SECRET), responde 200 de
    inmediato y procesa en background: consulta el pago a la API de MP y, si
    está aprobado, activa el plan premium SOLO del tenant que pagó.
    """
    settings = get_settings()

    try:
        body = await request.json()
    except Exception:
        body = {}
    data = body.get("data") or {}
    data_id = data.get("id") or request.query_params.get("data.id")

    if not settings.mercadopago_webhook_secret:
        # Fase manual: sin secreto configurado no hay nada verificable.
        logger.warning(
            "Webhook de MercadoPago sin MERCADOPAGO_WEBHOOK_SECRET: ignorado"
        )
        return {"status": "ignored"}

    try:
        verify_signature(
            secret=settings.mercadopago_webhook_secret,
            x_signature=request.headers.get("x-signature", ""),
            x_request_id=request.headers.get("x-request-id"),
            data_id=str(data_id) if data_id else None,
        )
    except PaymentSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Firma inválida"
        ) from exc

    if not data_id:
        # Notificación sin pago (p. ej. ping de configuración de MP)
        return {"status": "ok"}

    if settings.mercadopago_access_token:
        background_tasks.add_task(_apply_mercadopago_payment, str(data_id))
    else:
        logger.info(
            "Webhook de MP sin MERCADOPAGO_ACCESS_TOKEN: pago %s queda pendiente "
            "de la fase 2 (activación manual desde el panel)",
            data_id,
        )

    return {"status": "ok"}


async def _apply_mercadopago_payment(payment_id: str) -> None:
    """Guarda el evento primero (idempotente), procesa después (spec §11)."""
    from sqlalchemy.exc import IntegrityError

    from app.models import PaymentWebhookEvent
    from app.services.mercadopago import process_payment_notification

    settings = get_settings()
    try:
        async with SessionFactory() as db:
            # 1) Guardar el evento: idempotencia real — si ya existe,
            #    la restricción UNIQUE lo bloquea y no se procesa de nuevo
            event = PaymentWebhookEvent(
                provider="mercadopago",
                provider_ref=f"mp:{payment_id}",
                status="pending",
                payload={"payment_id": payment_id},
            )
            db.add(event)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                logger.info("Evento MP %s ya registrado: idempotente", payment_id)
                return

            # 2) Procesar: si falla, el evento queda 'failed' para reintentar
            try:
                tenant = await process_payment_notification(
                    db,
                    payment_id=payment_id,
                    access_token=settings.mercadopago_access_token,
                )
                if tenant is not None:
                    event.status = "processed"
                    logger.info(
                        "Suscripción premium activada para '%s' (pago MP %s)",
                        tenant.slug,
                        payment_id,
                    )
                else:
                    # Pago no aprobado o inválido: el evento queda registrado
                    # para auditoría pero no activa nada
                    event.status = "processed"
                    logger.info(
                        "Pago MP %s procesado sin cambio de plan", payment_id
                    )
                await db.commit()
            except Exception as exc:
                await db.rollback()
                # El evento ya se guardó: reintentar en la próxima notificación
                async with SessionFactory() as retry_db:
                    retry_event = (
                        await retry_db.execute(
                            select(PaymentWebhookEvent).where(
                                PaymentWebhookEvent.provider_ref == f"mp:{payment_id}"
                            )
                        )
                    ).scalar_one_or_none()
                    if retry_event is not None:
                        retry_event.status = "failed"
                        retry_event.attempts += 1
                        retry_event.last_error = str(exc)[:500]
                        await retry_db.commit()
                logger.exception("Error procesando el pago de MP %s", payment_id)
    except Exception:
        logger.exception("Error guardando el evento MP %s", payment_id)
