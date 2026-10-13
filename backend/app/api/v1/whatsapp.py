"""Conexión WhatsApp del panel: estado de la instancia, QR y prueba de envío."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, require_role
from app.channels import get_channel
from app.core.config import get_settings
from app.models import User

logger = logging.getLogger(__name__)
router = APIRouter()


class TestSendRequest(BaseModel):
    number: str = Field(..., min_length=8, max_length=20)
    text: str = Field(default="Prueba del asistente Aura", max_length=500)


@router.get("/status")
async def connection_status(_current_user: User = Depends(get_current_user)):
    """Estado de la instancia de WhatsApp (open | close | connecting | offline)."""
    channel = get_channel("evolution")
    state = await channel.connection_state()
    settings = get_settings()
    instance_state = (state.get("instance") or {}).get("state", "offline")
    return {"state": instance_state, "instance": settings.evolution_instance}


@router.post("/connect")
async def connect(_admin: User = Depends(require_role("admin"))):
    """Inicia el emparejamiento: devuelve el QR (base64) o el estado actual."""
    channel = get_channel("evolution")
    result = await channel.connect_qr()
    return result


@router.post("/disconnect")
async def disconnect(_admin: User = Depends(require_role("admin"))):
    """Cierra la sesión de WhatsApp (logout de la instancia de Evolution)."""
    channel = get_channel("evolution")
    try:
        result = await channel.disconnect()
    except Exception as exc:
        logger.exception("Fallo el logout de la instancia de WhatsApp")
        raise HTTPException(
            status_code=502, detail="No se pudo desconectar WhatsApp"
        ) from exc
    message = ((result or {}).get("response") or {}).get("message")
    return {"status": "ok", "detail": message or "Instancia desconectada"}


@router.post("/test-send")
async def test_send(
    body: TestSendRequest,
    _admin: User = Depends(require_role("admin")),
):
    """Envía un mensaje de prueba a un número (verificación del canal)."""
    channel = get_channel("evolution")
    try:
        await channel.send_text(body.number, body.text)
    except Exception as exc:
        logger.exception("Fallo el envío de prueba")
        raise HTTPException(status_code=502, detail="No se pudo enviar por WhatsApp") from exc
    return {"status": "ok"}
