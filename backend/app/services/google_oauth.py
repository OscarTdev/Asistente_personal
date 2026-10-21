"""OAuth 2.0 de Google por tenant (spec §15: correo y calendario).

La plataforma tiene UN client OAuth (configurado en .env) y cada dueño
conecta SU cuenta desde el panel. El flujo:

1. POST /google/authorize → JWT `state` (10 min) + URL de consentimiento
2. Google redirige a {panel}/google/callback?code=...&state=...
3. POST /google/callback → se verifica que el state sea del TENANT
   autenticado, se canjea el code y se guardan los tokens en su fila.

Sin client configurado el endpoint lo dice con claridad (422): nunca
falla en silencio. El refresh es transparente: si falla, la conexión
pasa a is_active=False y el dueño reconecta desde el panel.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import GoogleConnection

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Alcances por servicio: el mínimo para cada tarea (principio de menor
# privilegio). Gmail solo lectura + envío; Drive solo archivos creados
# por la app; Sheets/Docs/Forms para exportar e informes.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/forms.body",
]


class GoogleConfigError(Exception):
    """La plataforma no tiene client OAuth configurado (falta .env)."""


class GoogleNotConnected(Exception):
    """El tenant no tiene una cuenta Google conectada."""


class GoogleAuthError(Exception):
    """El refresh falló: el dueño debe reconectar su cuenta."""


def google_configured() -> bool:
    settings = get_settings()
    return bool(settings.google_client_id and settings.google_client_secret)


def redirect_uri() -> str:
    """URI de retorno registrada en Google Cloud Console."""
    settings = get_settings()
    return settings.google_redirect_uri or f"{settings.panel_base_url}/google/callback"


def build_state_token(tenant_id: UUID) -> str:
    """JWT corto que ata el flujo OAuth al tenant que lo inició."""
    payload = {
        "sub": "google-oauth",
        "tenant_id": str(tenant_id),
        "exp": datetime.now(UTC) + timedelta(minutes=10),
    }
    return jwt.encode(
        payload, get_settings().jwt_secret, algorithm=get_settings().jwt_algorithm
    )


def verify_state_token(state: str) -> UUID:
    """Devuelve el tenant_id del state o revienta (token inválido/expirado)."""
    try:
        payload = jwt.decode(
            state,
            get_settings().jwt_secret,
            algorithms=[get_settings().jwt_algorithm],
        )
        if payload.get("sub") != "google-oauth":
            raise ValueError("No es un state de Google")
        return UUID(payload["tenant_id"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise GoogleAuthError("El enlace de conexión expiró; vuelve a conectarlo") from exc


def build_authorization_url(state: str) -> str:
    """URL de consentimiento de Google (offline → refresh token)."""
    settings = get_settings()
    if not settings.google_client_id:
        raise GoogleConfigError(
            "Falta GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET en el servidor"
        )
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",   # pide refresh token
        "prompt": "consent",        # fuerza el refresh aunque ya existiera
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{httpx.QueryParams(params).encode()}"


async def exchange_code(code: str) -> dict:
    """Canjea el code por tokens. Devuelve access/refresh/expira/scope."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri(),
            },
        )
    if resp.status_code != 200:
        logger.warning("Google rechazó el code (HTTP %s)", resp.status_code)
        raise GoogleAuthError("Google rechazó la conexión; inténtalo de nuevo")
    data = resp.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_in": data.get("expires_in", 3600),
        "scope": data.get("scope", ""),
    }


async def fetch_user_email(access_token: str) -> str:
    """El correo de la cuenta Google que acaba de dar consentimiento."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        raise GoogleAuthError("No pude leer el correo de tu cuenta Google")
    return resp.json().get("email", "")


async def get_connection(
    db: AsyncSession, *, tenant_id: UUID
) -> GoogleConnection | None:
    """La conexión ACTIVA del tenant (None si no existe o expiró)."""
    return (
        await db.execute(
            select(GoogleConnection).where(
                GoogleConnection.tenant_id == tenant_id,
                GoogleConnection.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()


async def upsert_connection(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    google_email: str,
    access_token: str,
    refresh_token: str | None,
    expires_in: int,
    scope: str,
) -> GoogleConnection:
    """Guarda la conexión del tenant (reconectar sobreescribe la anterior)."""
    conn = (
        await db.execute(
            select(GoogleConnection).where(GoogleConnection.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    if conn is None:
        conn = GoogleConnection(tenant_id=tenant_id, google_email=google_email)
        db.add(conn)
    conn.google_email = google_email
    conn.access_token = access_token
    # Si Google omite el refresh, se conserva el anterior (sigue válido)
    if refresh_token:
        conn.refresh_token = refresh_token
    conn.token_expires_at = expires_at
    conn.scopes = scope.split() if scope else []
    conn.is_active = True
    await db.commit()
    await db.refresh(conn)
    return conn


async def get_access_token(db: AsyncSession, *, tenant_id: UUID) -> str:
    """Access token vigente, refrescando si vence en menos de 60 s."""
    conn = await get_connection(db, tenant_id=tenant_id)
    if conn is None:
        raise GoogleNotConnected(
            "Aún no has conectado tu cuenta de Google. Hazlo desde el panel: "
            "Mi negocio → Conectar Google."
        )
    if conn.token_expires_at > datetime.now(UTC) + timedelta(seconds=60):
        return conn.access_token
    return await _refresh(db, conn)


async def _refresh(db: AsyncSession, conn: GoogleConnection) -> str:
    settings = get_settings()
    if not conn.refresh_token:
        conn.is_active = False
        await db.commit()
        raise GoogleAuthError(
            "Tu conexión con Google expiró. Reconecta tu cuenta desde el panel."
        )
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": conn.refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if resp.status_code != 200:
        conn.is_active = False
        await db.commit()
        logger.warning("Refresh de Google falló (HTTP %s)", resp.status_code)
        raise GoogleAuthError(
            "Tu conexión con Google expiró. Reconecta tu cuenta desde el panel."
        )
    data = resp.json()
    conn.access_token = data["access_token"]
    conn.token_expires_at = datetime.now(UTC) + timedelta(
        seconds=data.get("expires_in", 3600)
    )
    await db.commit()
    return conn.access_token


async def disconnect(db: AsyncSession, *, tenant_id: UUID) -> bool:
    """Revoca el refresh en Google y borra la fila del tenant."""
    conn = (
        await db.execute(
            select(GoogleConnection).where(GoogleConnection.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if conn is None:
        return False
    # Revocar en Google es best-effort: la fila se borra pase lo que pase
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                GOOGLE_REVOKE_URL, params={"token": conn.refresh_token or conn.access_token}
            )
    except httpx.HTTPError:
        logger.warning("No pude revocar el token en Google; borro la fila igual")
    await db.delete(conn)
    await db.commit()
    return True
