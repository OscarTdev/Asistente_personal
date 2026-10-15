"""Branding del negocio: logo que aparece en los PDFs del panel.

El logo se guarda en la BD (BYTEA) normalizado con Pillow: PNG, ancho
máximo de 800px. El dueño del tenant lo sube desde el panel; sin logo,
los documentos usan el encabezado solo con texto.
"""

import base64
import io
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import TenantBranding, User

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB crudos antes de normalizar
MAX_WIDTH_PX = 800
ALLOWED_MIMETYPES = {"image/png", "image/jpeg", "image/webp"}


async def _get_or_create_branding(
    db: AsyncSession, tenant_id: Any
) -> TenantBranding:
    branding = (
        await db.execute(
            select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if branding is None:
        branding = TenantBranding(tenant_id=tenant_id)
        db.add(branding)
        await db.flush()
    return branding


def _normalize_logo(raw: bytes) -> bytes:
    """Valida y normaliza el logo: PNG RGBA, ancho máximo 800px.

    Lanza HTTPException(415) si el archivo no es una imagen soportada.
    """
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="El archivo no es una imagen válida (PNG, JPEG o WebP)",
        ) from exc

    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")

    if img.width > MAX_WIDTH_PX:
        ratio = MAX_WIDTH_PX / img.width
        img = img.resize(
            (MAX_WIDTH_PX, max(1, round(img.height * ratio))),
            Image.LANCZOS,
        )

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _branding_out(branding: TenantBranding | None) -> dict:
    """Resumen del branding para el panel (logo como data URL)."""
    out: dict = {"has_logo": False, "logo_data_url": None}
    if branding is not None and branding.logo_bytes:
        mimetype = branding.logo_mimetype or "image/png"
        encoded = base64.b64encode(branding.logo_bytes).decode("ascii")
        out["has_logo"] = True
        out["logo_data_url"] = f"data:{mimetype};base64,{encoded}"
    return out


@router.get("")
async def get_branding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Branding del tenant del usuario (logo como data URL para el panel)."""
    branding = (
        await db.execute(
            select(TenantBranding).where(
                TenantBranding.tenant_id == current_user.tenant_id
            )
        )
    ).scalar_one_or_none()
    return _branding_out(branding)


@router.put("/logo")
async def upload_logo(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sube o reemplaza el logo del negocio (PNG/JPEG/WebP, máx 2 MB)."""
    if (file.content_type or "") not in ALLOWED_MIMETYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Formato no soportado: usa PNG, JPEG o WebP",
        )

    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo vacío"
        )
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El logo supera los 2 MB",
        )

    logo_bytes = _normalize_logo(raw)
    branding = await _get_or_create_branding(db, current_user.tenant_id)
    branding.logo_bytes = logo_bytes
    branding.logo_mimetype = "image/png"
    await db.commit()
    logger.info("Logo actualizado para el tenant %s", current_user.tenant_id)

    return {"has_logo": True, "logo_mimetype": "image/png"}


@router.delete("/logo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_logo(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Quita el logo: los PDFs vuelven al encabezado solo con texto."""
    branding = (
        await db.execute(
            select(TenantBranding).where(
                TenantBranding.tenant_id == current_user.tenant_id
            )
        )
    ).scalar_one_or_none()
    if branding is not None and branding.logo_bytes is not None:
        branding.logo_bytes = None
        branding.logo_mimetype = None
        await db.commit()
    return None
