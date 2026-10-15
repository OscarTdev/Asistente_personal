"""Router de módulos del tenant.

GET    /api/v1/modules          → lista módulos disponibles con su estado para el tenant
POST   /api/v1/modules          → crea un nuevo módulo personalizado para el tenant
PUT    /api/v1/modules/{key}    → activa/desactiva o edita un módulo (solo admin)
DELETE /api/v1/modules/{key}    → elimina un módulo del tenant (solo admin)
"""

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.database import get_db
from app.core.modules_registry import (
    AVAILABLE_MODULES,
    module_dev_status,
    module_parent,
    module_workspace,
)
from app.models import Tenant, TenantModule, User
from app.schemas.modules import ModuleCreate, ModuleInfo, ModuleToggle, ModuleUpdate
from app.services.entitlements import module_allowed

router = APIRouter()
_require_admin = require_role("admin")


def _slugify(text: str) -> str:
    clean = re.sub(r"[^\w\s-]", "", text.lower().strip())
    slug = re.sub(r"[\s-]+", "_", clean)
    return slug[:50]


async def _ensure_initialized(db: AsyncSession, tenant_id: UUID) -> None:
    """Si el tenant no tiene ningún módulo registrado, inicializa los por defecto."""
    count_stmt = (
        select(func.count())
        .select_from(TenantModule)
        .where(TenantModule.tenant_id == tenant_id)
    )
    count = (await db.execute(count_stmt)).scalar_one()
    if count == 0:
        for m in AVAILABLE_MODULES:
            db.add(
                TenantModule(
                    tenant_id=tenant_id,
                    module_key=m["key"],
                    name=m["name"],
                    description=m["description"],
                    category=m["category"],
                    is_enabled=(m["key"] == "quoter"),
                    is_custom=False,
                )
            )
        await db.commit()


@router.get("", response_model=list[ModuleInfo])
async def list_modules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ModuleInfo]:
    """Devuelve todos los módulos configurados para el tenant del usuario."""
    await _ensure_initialized(db, current_user.tenant_id)

    result = await db.execute(
        select(TenantModule)
        .where(TenantModule.tenant_id == current_user.tenant_id)
        .order_by(TenantModule.category, TenantModule.name)
    )
    rows = result.scalars().all()
    return [
        ModuleInfo(
            key=row.module_key,
            name=row.name,
            description=row.description,
            category=row.category,
            is_enabled=row.is_enabled,
            is_custom=row.is_custom,
            dev_status=module_dev_status(row.module_key),
            workspace=module_workspace(row.module_key),
            parent=module_parent(row.module_key),
        )
        for row in rows
    ]


@router.post("", response_model=ModuleInfo, status_code=status.HTTP_201_CREATED)
async def create_module(
    body: ModuleCreate,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> ModuleInfo:
    """Crea un nuevo módulo personalizado para el tenant."""
    key = body.key.strip() if body.key else _slugify(body.name)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Identificador de módulo (key) inválido",
        )

    # Verificar unicidad dentro del tenant
    existing = await db.execute(
        select(TenantModule)
        .where(TenantModule.tenant_id == current_user.tenant_id)
        .where(TenantModule.module_key == key)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un módulo con la clave '{key}'",
        )

    module = TenantModule(
        tenant_id=current_user.tenant_id,
        module_key=key,
        name=body.name.strip(),
        description=body.description.strip() if body.description else None,
        category=body.category.strip() if body.category else "personalizado",
        is_enabled=True,
        is_custom=True,
    )
    db.add(module)
    await db.commit()
    await db.refresh(module)

    return ModuleInfo(
        key=module.module_key,
        name=module.name,
        description=module.description,
        category=module.category,
        is_enabled=module.is_enabled,
        is_custom=module.is_custom,
        dev_status=module_dev_status(module.module_key),
        workspace=module_workspace(module.module_key),
        parent=module_parent(module.module_key),
    )


@router.put("/{module_key}", response_model=ModuleInfo)
async def update_module(
    module_key: str,
    body: ModuleUpdate | ModuleToggle,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> ModuleInfo:
    """Actualiza o activa/desactiva un módulo para el tenant."""
    result = await db.execute(
        select(TenantModule)
        .where(TenantModule.tenant_id == current_user.tenant_id)
        .where(TenantModule.module_key == module_key)
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Módulo '{module_key}' no encontrado",
        )

    # Contrato de planes: nadie enciende un servicio que su plan no autoriza
    # (la matriz la define el super admin; defaults en modules_registry).
    if body.is_enabled:
        tenant = (
            await db.execute(
                select(Tenant).where(Tenant.id == current_user.tenant_id)
            )
        ).scalar_one()
        if not await module_allowed(db, plan=tenant.plan, module_key=module_key):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Tu plan actual no incluye este servicio. "
                    "Actualiza tu suscripción para activarlo."
                ),
            )

    if isinstance(body, ModuleUpdate):
        if body.name is not None:
            module.name = body.name.strip()
        if body.description is not None:
            module.description = body.description.strip()
        if body.category is not None:
            module.category = body.category.strip()
        if body.is_enabled is not None:
            module.is_enabled = body.is_enabled
    elif isinstance(body, ModuleToggle):
        module.is_enabled = body.is_enabled

    await db.commit()
    await db.refresh(module)

    return ModuleInfo(
        key=module.module_key,
        name=module.name,
        description=module.description,
        category=module.category,
        is_enabled=module.is_enabled,
        is_custom=module.is_custom,
        dev_status=module_dev_status(module.module_key),
        workspace=module_workspace(module.module_key),
        parent=module_parent(module.module_key),
    )


@router.delete("/{module_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_key: str,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Elimina un módulo para el tenant."""
    result = await db.execute(
        select(TenantModule)
        .where(TenantModule.tenant_id == current_user.tenant_id)
        .where(TenantModule.module_key == module_key)
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Módulo '{module_key}' no encontrado",
        )

    await db.delete(module)
    await db.commit()
