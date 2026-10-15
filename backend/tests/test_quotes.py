from http import HTTPStatus

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models import User


@pytest.fixture
def auth_headers(admin_user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    return {"Authorization": f"Bearer {token}"}


# ── Aislamiento (P0 cerrado): UUIDs ajenos nunca cruzan la frontera ─────────


@pytest.mark.asyncio
async def test_create_quote_rejects_foreign_contact(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    tenant,
):
    """Un contacto de OTRO tenant en el payload → 422, nada se crea."""
    import uuid

    from app.models import Contact, Tenant

    other = Tenant(
        id=uuid.uuid4(), name="Ajeno", slug="ajeno-q", bot_name="Aura", is_active=True
    )
    db_session.add(other)
    await db_session.flush()
    foreign_contact = Contact(tenant_id=other.id, wa_id="573009990099")
    db_session.add(foreign_contact)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/quotes",
        json={"contact_id": str(foreign_contact.id), "notes": "intrusión"},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "no encontrado en este negocio" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_quote_rejects_foreign_catalog_item(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    tenant,
):
    """Un ítem de catálogo de OTRO tenant → 422 (aunque el resto sea válido)."""
    import uuid

    from app.models import CatalogItem, Tenant

    other = Tenant(
        id=uuid.uuid4(), name="Ajeno", slug="ajeno-q2", bot_name="Aura", is_active=True
    )
    db_session.add(other)
    await db_session.flush()
    foreign_item = CatalogItem(
        tenant_id=other.id, name="Cable robado", unit="m", unit_price=100
    )
    db_session.add(foreign_item)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/quotes",
        json={
            "notes": "intrusión",
            "items": [
                {
                    "description": "Cable ajeno",
                    "quantity": 1,
                    "unit_price": "100.00",
                    "catalog_item_id": str(foreign_item.id),
                }
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "catálogo no encontrado" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_quote_with_own_contact_works(
    client: AsyncClient, auth_headers: dict[str, str], db_session, tenant, admin_user
):
    """Referencias propias → normal: la cotización se crea."""
    from app.models import Contact

    own_contact = Contact(
        tenant_id=admin_user.tenant_id, wa_id="573001110099", name="Propio"
    )
    db_session.add(own_contact)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/quotes",
        json={"contact_id": str(own_contact.id), "notes": "cotización legítima"},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.CREATED


@pytest.mark.asyncio
async def test_quotes_crud_and_recalculations(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Prueba creación de cotización, cálculo de totales, adición, edición y borrado de ítems."""
    # 1. Crear cotización con 2 ítems
    create_payload = {
        "notes": "Instalación tablero secundario en bodega",
        "items": [
            {
                "description": "Tablero 8 circuitos",
                "quantity": 1,
                "unit_price": "120000.00",
            },
            {
                "description": "Breaker 20A",
                "quantity": 4,
                "unit_price": "25000.00",
            },
        ],
    }
    create_resp = await client.post("/api/v1/quotes", json=create_payload, headers=auth_headers)
    assert create_resp.status_code == HTTPStatus.CREATED
    quote = create_resp.json()
    quote_id = quote["id"]
    # Total esperado: 1 * 120000 + 4 * 25000 = 220000
    assert float(quote["total"]) == 220000.00
    assert len(quote["items"]) == 2
    assert quote["status"] == "draft"

    # 2. Obtener cotización
    get_resp = await client.get(f"/api/v1/quotes/{quote_id}", headers=auth_headers)
    assert get_resp.status_code == HTTPStatus.OK
    assert float(get_resp.json()["total"]) == 220000.00

    # 3. Agregar un ítem extra (mano de obra: 1 x 80000)
    add_item_resp = await client.post(
        f"/api/v1/quotes/{quote_id}/items",
        json={
            "description": "Mano de obra instalación",
            "quantity": 1,
            "unit_price": "80000.00",
        },
        headers=auth_headers,
    )
    assert add_item_resp.status_code == HTTPStatus.CREATED
    new_item_id = add_item_resp.json()["id"]

    # Verificar que el total aumentó a 300000
    quote_after_add = (await client.get(f"/api/v1/quotes/{quote_id}", headers=auth_headers)).json()
    assert float(quote_after_add["total"]) == 300000.00

    # 4. Modificar el ítem agregado (mano de obra a 90000)
    update_item_resp = await client.put(
        f"/api/v1/quotes/{quote_id}/items/{new_item_id}",
        json={"unit_price": "90000.00"},
        headers=auth_headers,
    )
    assert update_item_resp.status_code == HTTPStatus.OK

    quote_after_update = (
        await client.get(f"/api/v1/quotes/{quote_id}", headers=auth_headers)
    ).json()
    assert float(quote_after_update["total"]) == 310000.00

    # 5. Eliminar el ítem agregado
    del_item_resp = await client.delete(
        f"/api/v1/quotes/{quote_id}/items/{new_item_id}",
        headers=auth_headers,
    )
    assert del_item_resp.status_code == HTTPStatus.NO_CONTENT

    # Total vuelve a 220000
    quote_after_del = (await client.get(f"/api/v1/quotes/{quote_id}", headers=auth_headers)).json()
    assert float(quote_after_del["total"]) == 220000.00

    # 6. Actualizar status de la cotización
    update_quote_resp = await client.put(
        f"/api/v1/quotes/{quote_id}",
        json={"status": "sent", "notes": "Enviado al cliente por WhatsApp"},
        headers=auth_headers,
    )
    assert update_quote_resp.status_code == HTTPStatus.OK
    assert update_quote_resp.json()["status"] == "sent"


@pytest.mark.asyncio
async def test_quote_pdf_download(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Descarga exitosa del PDF de cotización generado por ReportLab."""
    # Crear cotización previa
    create_resp = await client.post(
        "/api/v1/quotes",
        json={
            "notes": "Validez de 15 días.",
            "items": [
                {"description": "Servicio de diagnóstico", "quantity": 1, "unit_price": "50000.00"}
            ],
        },
        headers=auth_headers,
    )
    quote_id = create_resp.json()["id"]

    # Descargar PDF
    pdf_resp = await client.get(f"/api/v1/quotes/{quote_id}/pdf", headers=auth_headers)
    assert pdf_resp.status_code == HTTPStatus.OK
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert "attachment" in pdf_resp.headers["content-disposition"]
    # PDF magic bytes
    assert pdf_resp.content.startswith(b"%PDF")
