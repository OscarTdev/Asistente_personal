"""WebSocket /ws/events: reenvía los eventos Redis del tenant del usuario.

Protocolo (F1):
- Auth por query param `token` (JWT). Los browsers no permiten headers en
  `new WebSocket`; el token queda en la URL y uvicorn lo registra en el
  access log — trade-off documentado de F1 (local-only).
- Token ausente/inválido/expirado o usuario inactivo → accept() + close(1008)
  sin enviar la trama `connected` (cerrar antes de accept produce un 403 HTTP
  que el navegador reporta como 1006 y el logout no llega al cliente).
- Primera trama: {"type": "connected", "tenant_id": "...", "bot_name": "..."}.
- Cada evento del canal Redis `events:{tenant_id}` se reenvía verbatim.
- El cliente no envía nada; el endpoint solo lee para detectar desconexión.
"""

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from sqlalchemy import select

from app.core.redis import get_redis
from app.core.security import decode_access_token
from app.models import Tenant, User
from app.services.events import events_channel

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/events")
async def events_socket(
    websocket: WebSocket,
    token: str = Query(...),
    redis_client: Redis = Depends(get_redis),
) -> None:
    """Autentica por JWT y reenvía los eventos del canal del tenant.

    La sesión de BD vive SOLO durante la autenticación: una conexión
    WebSocket de larga duración no puede retener una conexión del pool
    (con varias pestañas del panel el pool se drena y TODA la plataforma
    se vuelve lenta). El loop posterior usa únicamente Redis.
    """
    await websocket.accept()

    try:
        from app.core.database import SessionFactory

        try:
            payload = decode_access_token(token)
            user_id = UUID(payload["sub"])
        except Exception:
            logger.debug("Token inválido o expirado en WebSocket")
            await websocket.close(code=1008)
            return

        async with SessionFactory() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user or not user.is_active:
                logger.debug("Usuario no válido en WebSocket: %s", user_id)
                await websocket.close(code=1008)
                return

            result = await db.execute(
                select(Tenant).where(Tenant.id == user.tenant_id)
            )
            tenant = result.scalar_one_or_none()
            if not tenant or not tenant.is_active:
                logger.debug("Tenant no válido en WebSocket: %s", user.tenant_id)
                await websocket.close(code=1008)
                return
            tenant_id = user.tenant_id
            bot_name = tenant.bot_name
        # ── la sesión de BD ya está cerrada; el loop no la necesita ──

        await websocket.send_text(
            json.dumps(
                {
                    "type": "connected",
                    "tenant_id": str(tenant_id),
                    "bot_name": bot_name,
                }
            )
        )

        # Un socket se suscribe únicamente al canal de su tenant (aislamiento).
        channel_name = events_channel(tenant_id)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel_name)

        async def redis_listener() -> None:
            try:
                while True:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                    if message and message["type"] == "message":
                        await websocket.send_text(message["data"])
            except asyncio.CancelledError:
                pass

        listener_task = asyncio.create_task(redis_listener())
        try:
            # El cliente no envía nada; receive() detecta la desconexión.
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass
            await pubsub.unsubscribe(channel_name)
            await pubsub.aclose()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Error inesperado en WebSocket")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
