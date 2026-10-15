import uuid
from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models import Tenant, User


@pytest.fixture
def auth_headers(admin_user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def member_user(db_session: AsyncSession, tenant: Tenant) -> User:
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="member@example.com",
        password_hash=hash_password("Member1234!"),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_list_modules_initializes_defaults(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """El primer GET /api/v1/modules inicializa los módulos por defecto."""
    resp = await client.get("/api/v1/modules", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()
    assert len(data) >= 10
    keys = [m["key"] for m in data]
    assert "quoter" in keys
    assert "follow_up" in keys

    quoter = next(m for m in data if m["key"] == "quoter")
    assert quoter["is_enabled"] is True


@pytest.mark.asyncio
async def test_modules_order_sub_services_and_workspaces(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """El orden de la lista: sub-servicios marcados con padre y servicios
    activos con su workspace (el botón Entrar del panel)."""
    await client.get("/api/v1/modules", headers=auth_headers)
    resp = await client.get("/api/v1/modules", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    data = {m["key"]: m for m in resp.json()}

    # El seguimiento es un sub-servicio del cotizador, no una carta propia
    assert data["follow_up"]["parent"] == "quoter"
    # Los demás servicios no tienen padre
    assert data["quoter"]["parent"] is None
    assert data["reminders"]["parent"] is None
    assert data["crm"]["parent"] is None

    # Servicios construidos con su workspace (botón Entrar)
    assert data["quoter"]["dev_status"] == "active"
    assert data["quoter"]["workspace"] == "/servicios/quoter"
    assert data["crm"]["dev_status"] == "active"
    assert data["crm"]["workspace"] == "/servicios/crm"
    assert data["reminders"]["dev_status"] == "active"
    assert data["reminders"]["workspace"] == "/servicios/reminders"

    # Un sub-servicio activo no tiene workspace propio: vive dentro del padre
    assert data["follow_up"]["dev_status"] == "active"
    assert data["follow_up"]["workspace"] is None

    # Un servicio sin construir sigue en desarrollo y sin workspace
    assert data["collections"]["dev_status"] == "development"
    assert data["collections"]["workspace"] is None


@pytest.mark.asyncio
async def test_toggle_module_state(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Admin puede activar o desactivar un módulo."""
    # Listar primero para inicializar
    await client.get("/api/v1/modules", headers=auth_headers)

    # Desactivar quoter
    resp = await client.put(
        "/api/v1/modules/quoter",
        json={"is_enabled": False},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["is_enabled"] is False

    # Activar quoter de nuevo
    resp = await client.put(
        "/api/v1/modules/quoter",
        json={"is_enabled": True},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["is_enabled"] is True


@pytest.mark.asyncio
async def test_create_and_delete_custom_module(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Admin puede crear un módulo personalizado y luego eliminarlo."""
    await client.get("/api/v1/modules", headers=auth_headers)

    # Crear
    resp = await client.post(
        "/api/v1/modules",
        json={
            "name": "Facturación Electrónica DIAN",
            "key": "facturacion_dian",
            "description": "Emite facturas electrónicas a la DIAN",
            "category": "financiero",
        },
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.CREATED
    body = resp.json()
    assert body["key"] == "facturacion_dian"
    assert body["name"] == "Facturación Electrónica DIAN"
    assert body["is_custom"] is True
    assert body["is_enabled"] is True

    # Reintento con misma clave falla 409
    dup_resp = await client.post(
        "/api/v1/modules",
        json={
            "name": "Otra Facturación",
            "key": "facturacion_dian",
        },
        headers=auth_headers,
    )
    assert dup_resp.status_code == HTTPStatus.CONFLICT

    # Eliminar
    del_resp = await client.delete("/api/v1/modules/facturacion_dian", headers=auth_headers)
    assert del_resp.status_code == HTTPStatus.NO_CONTENT

    # Verificar que ya no está
    list_resp = await client.get("/api/v1/modules", headers=auth_headers)
    keys = [m["key"] for m in list_resp.json()]
    assert "facturacion_dian" not in keys


@pytest.mark.asyncio
async def test_non_admin_cannot_modify_modules(
    client: AsyncClient, member_user: User
):
    """Usuarios no admin pueden ver módulos pero no crear, modificar ni borrar."""
    token = create_access_token(
        user_id=member_user.id,
        tenant_id=member_user.tenant_id,
        role=member_user.role,
    )
    headers = {"Authorization": f"Bearer {token}"}

    # GET es permitido
    resp = await client.get("/api/v1/modules", headers=headers)
    assert resp.status_code == HTTPStatus.OK

    # POST denegado (403)
    post_resp = await client.post(
        "/api/v1/modules",
        json={"name": "Test", "key": "test"},
        headers=headers,
    )
    assert post_resp.status_code == HTTPStatus.FORBIDDEN

    # PUT denegado (403)
    put_resp = await client.put(
        "/api/v1/modules/quoter",
        json={"is_enabled": False},
        headers=headers,
    )
    assert put_resp.status_code == HTTPStatus.FORBIDDEN

    # DELETE denegado (403)
    del_resp = await client.delete("/api/v1/modules/quoter", headers=headers)
    assert del_resp.status_code == HTTPStatus.FORBIDDEN
