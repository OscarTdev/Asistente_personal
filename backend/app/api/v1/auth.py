from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rate_limit import login_rate_limiter
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

    # El onboarding crea el usuario con el correo real, pero inactivo.
    # El enlace solo puede activar esa cuenta una vez; una cuenta activa
    # requiere el flujo normal de recuperación de contraseña.
    existing = (
        await db.execute(
            select(User).where(User.tenant_id == tenant_id)
        )
    ).scalars().first()
    if existing is not None and existing.is_active:
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

    if existing is not None:
        existing.password_hash = hash_password(body.password)
        existing.is_active = True
        user = existing
        status_text = "updated"
    else:
        user = User(
            tenant_id=tenant_id,
            email=f"owner@{tenant.slug}.local",  # placeholder: el dueño lo cambia en el panel
            password_hash=hash_password(body.password),
            full_name=tenant.name,
            role="admin",
            is_active=True,
        )
        db.add(user)
        status_text = "created"

    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
    )

    return {
        "status": status_text,
        "tenant": tenant.slug,
        "access_token": access_token,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "tenant_id": str(user.tenant_id),
            "bot_name": tenant.bot_name,
            "tenant_name": tenant.name,
            "plan": tenant.plan,
            "is_platform_admin": user.is_platform_admin,
        },
        "message": "Contraseña guardada con éxito.",
    }


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(login_rate_limiter),
):
    """Autentica un usuario y devuelve un access token.

    - Email inexistente o password incorrecta: 401 (mismo mensaje, sin
      revelar cuál falló).
    - Email en varios tenants: 400 (supuesto documentado de F1; sin header
      de tenant en el login).
    - Rate limited: 5 intentos por IP cada 5 minutos.
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

    # Segundo factor del superadmin (adendo §4.5): con 2FA activo, sin
    # código válido no hay token — aunque la contraseña sea correcta.
    if user.is_platform_admin and user.totp_enabled:
        from app.services.totp import verify_totp

        if not user.totp_secret or not verify_totp(
            user.totp_secret, request.totp_code or ""
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Código de verificación requerido o inválido",
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
            tenant_name=tenant.name,
            plan=tenant.plan,
            is_platform_admin=user.is_platform_admin,
            is_impersonating=False,
        ),
    )


@router.get("/me", response_model=UserPublic)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Devuelve los datos del usuario en sesión, incluyendo tenant actual y plan."""
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one_or_none()

    is_impersonating = getattr(current_user, "is_impersonating", False)
    bot_name = getattr(current_user, "bot_name", tenant.bot_name if tenant else "Aura")
    tenant_name = getattr(
        current_user, "target_tenant_name", tenant.name if tenant else None
    )
    plan = getattr(
        current_user, "target_tenant_plan", tenant.plan if tenant else None
    )

    return UserPublic(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        tenant_id=current_user.tenant_id,
        bot_name=bot_name,
        tenant_name=tenant_name,
        plan=plan,
        is_platform_admin=current_user.is_platform_admin,
        is_impersonating=is_impersonating,
    )
