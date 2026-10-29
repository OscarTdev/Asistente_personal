"""API: configuración dinámica de IA (super admin, nivel plataforma).

GET    /platform/ai-config        -> lista completa con metadatos
PATCH  /platform/ai-config/{key}  -> actualiza una clave
"""
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_platform_admin
from app.models import User
from app.services import platform_ai as svc

router = APIRouter(prefix="/platform/ai-config", tags=["platform-ai-config"])


class AIConfigItem(BaseModel):
    value: str
    label: str | None = None
    description: str | None = None
    is_secret: bool = False
    value_type: str = "string"


class AIConfigUpdate(BaseModel):
    value: str


@router.get("", response_model=dict[str, AIConfigItem])
async def list_ai_config(
    _admin: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """Devuelve toda la configuración de IA con metadatos para el panel."""
    return await svc.get_all_ai_config(db)


@router.patch("/{key}", response_model=AIConfigItem)
async def update_ai_config(
    key: str = Path(..., pattern=r"^(LLM_|STT_|TTS_)"),
    body: AIConfigUpdate = ...,
    _admin: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """Actualiza un valor (upsert). Invalida caché automáticamente."""
    row = await svc.set_ai_config(db, key, body.value)
    return AIConfigItem(
        value=row.value,
        label=row.label,
        description=row.description,
        is_secret=row.is_secret,
        value_type=row.value_type,
    )