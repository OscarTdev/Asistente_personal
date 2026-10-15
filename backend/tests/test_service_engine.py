"""Tests del motor de servicios (adendo §5).

Orden: interruptor global → excepción por cliente → plan.
El bot responde con mensaje claro cuando el servicio está bloqueado.
"""

import uuid
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tenant, User


@pytest.fixture
def platform_admin_headers(admin_user: User) -> dict[str, str]:
    from app.core.security import create_access_token

    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def platform_super_admin(db_session: AsyncSession, tenant: Tenant) -> User:
    from app.core.security import hash_password

    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="engine@example.com",
        password_hash=hash_password("Secreta123!"),
        role="admin",
        is_active=True,
        is_platform_admin=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def super_admin_headers(platform_super_admin: User) -> dict[str, str]:
    from app.core.security import create_access_token

    token = create_access_token(
        user_id=platform_super_admin.id,
        tenant_id=platform_super_admin.tenant_id,
        role=platform_super_admin.role,
    )
    return {"Authorization": f"Bearer {token}"}


async def _available(db, tenant, key):
    from app.services.service_engine import service_available

    return await service_available(db, tenant_id=tenant.id, plan=tenant.plan, service_key=key)


@pytest.mark.asyncio
async def test_default_is_operational(db_session: AsyncSession, tenant: Tenant):
    """Sin fila de estado: todo disponible según el plan."""
    ok, why = await _available(db_session, tenant, "quoter")
    assert ok is True and why is None


@pytest.mark.asyncio
async def test_global_maintenance_blocks(
    db_session: AsyncSession, tenant: Tenant, super_admin_headers
):
    """Interruptor global en mantenimiento → nadie lo usa; con mensaje propio."""
    from app.services.service_engine import set_status

    await set_status(
        db_session,
        service_key="quoter",
        status="maintenance",
        message="Estamos actualizando el cotizador",
    )

    ok, why = await _available(db_session, tenant, "quoter")
    assert ok is False
    assert "actualizando el cotizador" in why


@pytest.mark.asyncio
async def test_degraded_still_works(db_session: AsyncSession, tenant: Tenant):
    """Degradado = funciona (peor), no bloquea."""
    from app.services.service_engine import set_status

    await set_status(db_session, service_key="quoter", status="degraded")
    ok, _ = await _available(db_session, tenant, "quoter")
    assert ok is True


@pytest.mark.asyncio
async def test_override_beats_plan(
    db_session: AsyncSession, tenant: Tenant, platform_super_admin: User
):
    """Excepción con motivo: dar un servicio que el plan no incluye."""
    from app.services.service_engine import set_override

    # trial no incluye collections
    ok, _ = await _available(db_session, tenant, "collections")
    assert ok is False

    await set_override(
        db_session,
        tenant_id=tenant.id,
        service_key="collections",
        allowed=True,
        reason="Cliente especial: prueba del cobro por 15 días",
        expires_at=datetime.now(UTC) + timedelta(days=15),
        created_by=platform_super_admin.id,
    )
    ok, _ = await _available(db_session, tenant, "collections")
    assert ok is True


@pytest.mark.asyncio
async def test_expired_override_stops_counting(
    db_session: AsyncSession, tenant: Tenant
):
    """Vencida la excepción, el plan vuelve a mandar."""
    from app.services.service_engine import set_override

    await set_override(
        db_session,
        tenant_id=tenant.id,
        service_key="collections",
        allowed=True,
        reason="Regalo temporal",
        expires_at=datetime.now(UTC) - timedelta(hours=1),  # ya venció
    )
    ok, _ = await _available(db_session, tenant, "collections")
    assert ok is False


@pytest.mark.asyncio
async def test_override_requires_reason(db_session: AsyncSession, tenant: Tenant):
    """Motivo obligatorio (adendo §4): sin él, ValueError."""
    from app.services.service_engine import set_override

    with pytest.raises(ValueError):
        await set_override(
            db_session,
            tenant_id=tenant.id,
            service_key="collections",
            allowed=True,
            reason="   ",
        )


@pytest.mark.asyncio
async def test_platform_status_endpoints(
    client, super_admin_headers, platform_admin_headers
):
    """El superadmin gestiona el estado global; un admin de negocio recibe 403."""
    # Sin permiso
    resp = await client.get("/api/v1/admin/service-status", headers=platform_admin_headers)
    assert resp.status_code == HTTPStatus.FORBIDDEN

    # Estado inicial: vacío (operativos)
    resp = await client.get("/api/v1/admin/service-status", headers=super_admin_headers)
    assert resp.status_code == HTTPStatus.OK
    assert resp.json() == []

    # Poner el cotizador en mantenimiento
    resp = await client.put(
        "/api/v1/admin/service-status/quoter",
        json={"status": "maintenance", "message": "Actualizando"},
        headers=super_admin_headers,
    )
    assert resp.status_code == HTTPStatus.OK

    resp = await client.get("/api/v1/admin/service-status", headers=super_admin_headers)
    statuses = {s["service_key"]: s for s in resp.json()}
    assert statuses["quoter"]["status"] == "maintenance"
    assert "Actualizando" in statuses["quoter"]["message"]

    # Estado inválido → 422
    resp = await client.put(
        "/api/v1/admin/service-status/quoter",
        json={"status": "exploded"},
        headers=super_admin_headers,
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_tenant_override_endpoints(
    client, super_admin_headers, tenant, platform_super_admin
):
    """CRUD de excepciones con motivo obligatorio."""
    # Sin motivo → 422
    resp = await client.put(
        f"/api/v1/admin/tenants/{tenant.id}/service-overrides",
        json={"service_key": "collections", "allowed": True, "reason": "no"},
        headers=super_admin_headers,
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    # Crear
    resp = await client.put(
        f"/api/v1/admin/tenants/{tenant.id}/service-overrides",
        json={
            "service_key": "collections",
            "allowed": True,
            "reason": "Prueba del cobro de cartera por 15 días",
        },
        headers=super_admin_headers,
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["allowed"] is True

    # Listar
    resp = await client.get(
        f"/api/v1/admin/tenants/{tenant.id}/service-overrides",
        headers=super_admin_headers,
    )
    assert resp.status_code == HTTPStatus.OK
    assert len(resp.json()) == 1

    # Borrar
    resp = await client.delete(
        f"/api/v1/admin/tenants/{tenant.id}/service-overrides/collections",
        headers=super_admin_headers,
    )
    assert resp.status_code == HTTPStatus.NO_CONTENT

    resp = await client.get(
        f"/api/v1/admin/tenants/{tenant.id}/service-overrides",
        headers=super_admin_headers,
    )
    assert resp.json() == []
