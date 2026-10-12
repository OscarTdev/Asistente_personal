import io
import uuid
from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models import Tenant, User


@pytest.fixture
def auth_headers(admin_user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_catalog_crud_lifecycle(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Ciclo de vida completo de un ítem del catálogo: crear, listar, editar y soft-delete."""
    # 1. Crear
    create_resp = await client.post(
        "/api/v1/catalog",
        json={
            "name": "Breaker monopolar 20A",
            "description": "Interruptor termomagnético 20A Square D",
            "unit": "und",
            "unit_price": "28500.00",
            "is_active": True,
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == HTTPStatus.CREATED
    item = create_resp.json()
    item_id = item["id"]
    assert item["name"] == "Breaker monopolar 20A"
    assert float(item["unit_price"]) == 28500.00

    # 2. Obtener por ID
    get_resp = await client.get(f"/api/v1/catalog/{item_id}", headers=auth_headers)
    assert get_resp.status_code == HTTPStatus.OK
    assert get_resp.json()["id"] == item_id

    # 3. Listar con filtro de búsqueda
    list_resp = await client.get("/api/v1/catalog?search=Breaker", headers=auth_headers)
    assert list_resp.status_code == HTTPStatus.OK
    list_data = list_resp.json()
    assert list_data["total"] == 1
    assert list_data["items"][0]["id"] == item_id

    # 4. Actualizar
    update_resp = await client.put(
        f"/api/v1/catalog/{item_id}",
        json={"unit_price": "31000.00", "description": "Actualizado"},
        headers=auth_headers,
    )
    assert update_resp.status_code == HTTPStatus.OK
    assert float(update_resp.json()["unit_price"]) == 31000.00

    # 5. Soft-delete
    del_resp = await client.delete(f"/api/v1/catalog/{item_id}", headers=auth_headers)
    assert del_resp.status_code == HTTPStatus.NO_CONTENT

    # 6. Al listar active_only=true ya no aparece
    list_after_del = await client.get("/api/v1/catalog?active_only=true", headers=auth_headers)
    assert list_after_del.json()["total"] == 0

    # Pero con active_only=false sí aparece
    list_all = await client.get("/api/v1/catalog?active_only=false", headers=auth_headers)
    assert list_all.json()["total"] == 1
    assert list_all.json()["items"][0]["is_active"] is False


@pytest.mark.asyncio
async def test_catalog_multi_tenant_isolation(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Verifica que un tenant no pueda acceder ni modificar ítems de otro tenant."""
    # Tenant 1 crea un ítem
    create_resp = await client.post(
        "/api/v1/catalog",
        json={"name": "Cable 10 AWG", "unit_price": "4500.00"},
        headers=auth_headers,
    )
    item_id = create_resp.json()["id"]

    # Crear Tenant 2 con su propio usuario
    tenant2 = Tenant(
        id=uuid.uuid4(),
        name="Empresa B",
        slug="empresa-b",
        bot_name="Bot B",
        is_active=True,
    )
    user2 = User(
        id=uuid.uuid4(),
        tenant_id=tenant2.id,
        email="admin@empresa-b.com",
        password_hash="fake",
        role="admin",
        is_active=True,
    )
    db_session.add_all([tenant2, user2])
    await db_session.commit()

    token2 = create_access_token(user_id=user2.id, tenant_id=tenant2.id, role="admin")
    headers2 = {"Authorization": f"Bearer {token2}"}

    # Tenant 2 no ve el ítem al listar
    list2 = await client.get("/api/v1/catalog", headers=headers2)
    assert list2.json()["total"] == 0

    # Tenant 2 recibe 404 al intentar obtenerlo directamente
    get2 = await client.get(f"/api/v1/catalog/{item_id}", headers=headers2)
    assert get2.status_code == HTTPStatus.NOT_FOUND

    # Tenant 2 no puede actualizarlo
    put2 = await client.put(
        f"/api/v1/catalog/{item_id}",
        json={"unit_price": "1.00"},
        headers=headers2,
    )
    assert put2.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_catalog_import_csv(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Importación de catálogo desde CSV con soporte para upsert y manejo de errores."""
    csv_content = (
        "nombre,descripcion,unidad,precio_unitario\n"
        "Caja 4x4 galvanizada,Caja eléctrica,und,6500.00\n"
        "Toma doble leviton,Toma con polo a tierra,und,12000.00\n"
        ",Fila sin nombre,und,5000\n"
        "Cinta aislante,3M negra,rollo,invalido\n"
    ).encode()

    files = {"file": ("catalogo.csv", io.BytesIO(csv_content), "text/csv")}
    resp = await client.post("/api/v1/catalog/import-csv", files=files, headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()
    assert data["created"] == 2
    assert len(data["errors"]) == 2  # fila sin nombre y precio inválido

    # Reimportar con precio actualizado (upsert)
    csv_update = (
        "nombre,descripcion,unidad,precio_unitario\n"
        "Caja 4x4 galvanizada,Caja eléctrica mejorada,und,7000.00\n"
    ).encode()
    files2 = {"file": ("catalogo.csv", io.BytesIO(csv_update), "text/csv")}
    resp2 = await client.post("/api/v1/catalog/import-csv", files=files2, headers=auth_headers)
    assert resp2.status_code == HTTPStatus.OK
    data2 = resp2.json()
    assert data2["created"] == 0
    assert data2["updated"] == 1
