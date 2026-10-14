import hmac
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import Tenant, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validate the access token and return the current user.
    """
    try:
        payload = decode_access_token(token)
        user_id = UUID(payload["sub"])
        tenant_id = UUID(payload["tenant_id"])
        role = payload["role"]
    except (ValueError, KeyError, jwt.InvalidTokenError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Get user from database
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no válido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check tenant matches
    if user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no válido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check role matches (optional, but good practice)
    if user.role != role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no válido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no válido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_role(*roles: str):
    """
    Dependency to check if the current user has one of the required roles.
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permisos insuficientes",
            )
        return current_user
    return role_checker


async def verify_webhook_secret(
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> None:
    """Secreto compartido con Evolution (fail-closed): sin él, el webhook es 401.

    Cualquiera que alcance la URL podría inyectar mensajes, gastar IA y
    hacer escribir al bot — por eso no existe modo "sin secretos".
    """
    expected = get_settings().webhook_secret
    if (
        not expected
        or x_webhook_secret is None
        or not hmac.compare_digest(x_webhook_secret, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No autorizado"
        )


async def require_platform_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Solo administradores de la plataforma (gestionan todos los tenants)."""
    if not current_user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere administrador de la plataforma",
        )
    return current_user


async def get_platform_tenant(db: AsyncSession = Depends(get_db)) -> Tenant:
    """El tenant de plataforma: la puerta de los desconocidos.

    Con UN número compartido (Enmienda A) no existe X-Tenant-Slug: quien
    no está registrado cae aquí (onboarding y soporte), y sus datos nunca
    se mezclan con los de un negocio. Se crea perezosamente si falta
    (fila de sistema).
    """
    from sqlalchemy.exc import IntegrityError

    slug = get_settings().platform_tenant_slug
    tenant = (
        await db.execute(select(Tenant).where(Tenant.slug == slug))
    ).scalar_one_or_none()
    if tenant is not None:
        return tenant

    tenant = Tenant(name="Plataforma", slug=slug, bot_name="Aura", is_platform=True)
    db.add(tenant)
    try:
        await db.commit()
    except IntegrityError:
        # Carrera: otro request lo creó primero
        await db.rollback()
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one()
    return tenant