from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models import Tenant, User
from app.schemas.auth import LoginRequest, LoginResponse, UserPublic

router = APIRouter()


class SetPasswordRequest(BaseModel):
    """Creación de contraseña con el enlace de un solo uso del onboarding.

    La contraseña JAMÁS viaja por WhatsApp (D7): llega por esta página.
    """
    token: str
    password: str = Field(min_length=8, max_length=100)


@router.post("/set-password", status_code=status.HTTP_201_CREATED)
async def set_password(
    body: SetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Crea la contraseña del panel con el token del onboarding.

    El token es un JWT de un solo uso con caducidad corta, generado al
    completar el registro por chat. Si es válido, crea el usuario admin
    del tenant nuevo con la contraseña recibida.
    """
    try:
        payload = decode_access_token(body.token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Enlace expirado o inválido. Solicita uno nuevo escribiendo al bot.",
        ) from None

    if payload.get("role") != "onboarding":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no válido para crear contraseña",
        )

    tenant_id = UUID(payload["tenant_id"])

    # ¿Ya existe un usuario para este tenant? No duplicar
    existing = (
        await db.execute(
            select(User).where(User.tenant_id == tenant_id)
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario para esta cuenta",
        )

    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada"
        )

    user = User(
        tenant_id=tenant_id,
        email=f"owner@{tenant.slug}.local",  # placeholder: el dueño lo cambia en el panel
        password_hash=hash_password(body.password),
        full_name=tenant.name,
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()

    return {
        "status": "created",
        "tenant": tenant.slug,
        "message": "Contraseña creada. Ya puedes iniciar sesión en el panel.",
    }


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Autentica un usuario y devuelve un access token.

    - Email inexistente o password incorrecta: 401 (mismo mensaje, sin
      revelar cuál falló).
    - Email en varios tenants: 400 (supuesto documentado de F1; sin header
      de tenant en el login).
    """
    result = await db.execute(select(User).where(User.email == request.email))
    users = result.scalars().all()

    if len(users) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo pertenece a varios tenants",
        )

    user = users[0] if users else None
    if (
        user is None
        or not user.is_active
        or not verify_password(request.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
    )

    return LoginResponse(
        access_token=access_token,
        user=UserPublic(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            tenant_id=user.tenant_id,
            bot_name=tenant.bot_name,
            is_platform_admin=user.is_platform_admin,
        ),
    )
