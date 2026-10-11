import uuid
from http import HTTPStatus

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_by_slug, require_role
from app.core.security import create_access_token
from app.models import Tenant, User


@pytest.mark.asyncio
async def test_get_current_user_valid_token(
    db_session: AsyncSession, admin_user: User, tenant: Tenant
):
    """Token válido → devuelve el usuario."""
    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    user = await get_current_user(token=token, db=db_session)
    assert user.id == admin_user.id


@pytest.mark.asyncio
async def test_get_current_user_invalid_token(db_session: AsyncSession):
    """Token malformado → 401."""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token="no-es-jwt", db=db_session)
    assert exc_info.value.status_code == HTTPStatus.UNAUTHORIZED
    assert "Token inválido o expirado" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_expired_token(db_session: AsyncSession, admin_user: User):
    """Token expirado → 401."""
    from datetime import timedelta

    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=token, db=db_session)
    assert exc_info.value.status_code == HTTPStatus.UNAUTHORIZED
    assert "Token inválido o expirado" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_nonexistent_user(db_session: AsyncSession):
    """Token para un usuario inexistente → 401."""
    token = create_access_token(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="admin"
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=token, db=db_session)
    assert exc_info.value.status_code == HTTPStatus.UNAUTHORIZED
    assert "Usuario no válido" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_wrong_tenant(
    db_session: AsyncSession, admin_user: User
):
    """Token cuyo tenant_id no coincide con el del usuario → 401."""
    token = create_access_token(
        user_id=admin_user.id, tenant_id=uuid.uuid4(), role=admin_user.role
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=token, db=db_session)
    assert exc_info.value.status_code == HTTPStatus.UNAUTHORIZED
    assert "Usuario no válido" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_inactive_user(
    db_session: AsyncSession, admin_user: User
):
    """Usuario inactivo → 401."""
    admin_user.is_active = False
    await db_session.commit()

    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=token, db=db_session)
    assert exc_info.value.status_code == HTTPStatus.UNAUTHORIZED
    assert "Usuario no válido" in exc_info.value.detail


def test_require_role_accepts(admin_user: User):
    """Role permitido → devuelve el usuario."""
    checker = require_role("admin")
    assert checker(current_user=admin_user) is admin_user


@pytest.mark.asyncio
async def test_require_role_rejects(db_session: AsyncSession, tenant: Tenant):
    """Role no permitido → 403."""
    from app.core.security import hash_password

    viewer = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="viewer@example.com",
        password_hash=hash_password("Viewer1234!"),
        full_name=None,
        role="user",
        is_active=True,
    )
    db_session.add(viewer)
    await db_session.commit()

    checker = require_role("admin")
    with pytest.raises(HTTPException) as exc_info:
        checker(current_user=viewer)
    assert exc_info.value.status_code == HTTPStatus.FORBIDDEN
    assert "Permisos insuficientes" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_tenant_by_slug_valid(db_session: AsyncSession, tenant: Tenant):
    """Slug válido → devuelve el tenant activo."""
    result = await get_tenant_by_slug(x_tenant_slug=tenant.slug, db=db_session)
    assert result.id == tenant.id


@pytest.mark.asyncio
async def test_get_tenant_by_slug_invalid_slug(db_session: AsyncSession):
    """Slug desconocido → 404 sin filtrar información."""
    with pytest.raises(HTTPException) as exc_info:
        await get_tenant_by_slug(x_tenant_slug="nonexistent", db=db_session)
    assert exc_info.value.status_code == HTTPStatus.NOT_FOUND
    assert "Tenant no encontrado" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_tenant_by_slug_inactive_tenant(db_session: AsyncSession, tenant: Tenant):
    """Tenant inactivo → 404 igual que slug desconocido."""
    tenant.is_active = False
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_tenant_by_slug(x_tenant_slug=tenant.slug, db=db_session)
    assert exc_info.value.status_code == HTTPStatus.NOT_FOUND
    assert "Tenant no encontrado" in exc_info.value.detail
