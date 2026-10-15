"""Segundo factor (TOTP) del superadmin (adendo §4.5).

Código de 6 dígitos de una app autenticadora (Google Authenticator,
Authy, 1Password…). El secreto vive cifrado a nivel de aplicación en
producción; en desarrollo va en claro en la BD. El login del superadmin
exige el código cuando el 2FA está activo — sin código, no hay panel.
"""

import base64
import logging
import uuid

import pyotp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

logger = logging.getLogger(__name__)

# Extendemos el modelo User en BD con columnas de 2FA:
#   totp_secret (String(64), nullable) — el secreto compartido
#   totp_enabled (Boolean, default false)
# La migración las agrega; el servicio solo las consume.


def generate_totp_secret() -> str:
    """Un secreto nuevo de 32 caracteres base32 para la app autenticadora."""
    return base64.b32encode(uuid.uuid4().bytes + uuid.uuid4().bytes).decode("ascii")[:32]


def provisioning_uri(secret: str, email: str, issuer: str = "Aura Asistente") -> str:
    """El URI otpauth:// que escanea la app (o el QR que se genera de él)."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    """Verifica el código de 6 dígitos (ventana: ±1 paso de 30s)."""
    if not secret or not code or len(code) != 6 or not code.isdigit():
        return False
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)


async def start_totp_setup(db: AsyncSession, *, user_id: uuid.UUID) -> dict:
    """Genera el secreto (aún sin activar) y devuelve el URI para el QR."""
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one()
    secret = generate_totp_secret()
    user.totp_secret = secret
    user.totp_enabled = False
    await db.commit()
    logger.info("2FA: setup iniciado para %s (no activo hasta confirmar)", user_id)
    return {
        "secret": secret,
        "uri": provisioning_uri(secret, user.email),
    }


async def confirm_totp(db: AsyncSession, *, user_id: uuid.UUID, code: str) -> bool:
    """Confirma el setup: el código correcto activa el 2FA."""
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one()
    if not user.totp_secret or not verify_totp(user.totp_secret, code):
        return False
    user.totp_enabled = True
    await db.commit()
    logger.info("2FA ACTIVO para %s", user_id)
    return True


async def disable_totp(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one()
    user.totp_secret = None
    user.totp_enabled = False
    await db.commit()
    logger.info("2FA desactivado para %s", user_id)


async def check_totp(db: AsyncSession, *, user_id: uuid.UUID, code: str) -> bool:
    """El paso de verificación del login del superadmin."""
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.totp_enabled or not user.totp_secret:
        return True  # sin 2FA: no bloquea
    return verify_totp(user.totp_secret, code)
