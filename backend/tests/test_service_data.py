"""Tests de la API de service-data: inventario, mantenimiento, garantías,
gastos y obra — los listados que el panel consume."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus

import pytest

from app.core.security import create_access_token
from app.models import Contact, User


@pytest.fixture
def auth_headers(admin_user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_inventory_list_and_adjust(
    client, auth_headers, db_session, admin_user
):
    """Listar materiales y ajustar el stock sin quedar bajo 0."""
    from app.models import InventoryItem

    item = InventoryItem(
        tenant_id=admin_user.tenant_id,
        name="Cable THHN #12",
        unit="metros",
        quantity=Decimal("100.00"),
        min_quantity=Decimal("20.00"),
    )
    db_session.add(item)
    await db_session.commit()

    # Listar
    resp = await client.get("/api/v1/service-data/inventory", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "Cable THHN #12"
    assert items[0]["quantity"] == 100.0

    # Ajustar: -30 (sale material para una instalación)
    resp = await client.put(
        f"/api/v1/service-data/inventory/{item.id}/adjust",
        json={"delta": -30, "reason": "Uso en instalación"},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["quantity"] == 70.0

    # Ajustar bajo 0 → 422
    resp = await client.put(
        f"/api/v1/service-data/inventory/{item.id}/adjust",
        json={"delta": -80},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_maintenance_list(client, auth_headers, db_session, admin_user):
    from app.models import Maintenance

    contact = Contact(tenant_id=admin_user.tenant_id, wa_id="573001112233", name="Juliana")
    db_session.add(contact)
    await db_session.flush()

    db_session.add(
        Maintenance(
            tenant_id=admin_user.tenant_id,
            contact_id=contact.id,
            description="Limpieza de aire acondicionado",
            frequency_days=180,
            next_due=datetime.now(UTC) + timedelta(days=30),
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/service-data/maintenance", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    items = resp.json()
    assert len(items) == 1
    assert items[0]["description"] == "Limpieza de aire acondicionado"
    assert items[0]["contact_name"] == "Juliana"


@pytest.mark.asyncio
async def test_warranties_list_and_void(
    client, auth_headers, db_session, admin_user
):
    from app.models import Warranty

    contact = Contact(tenant_id=admin_user.tenant_id, wa_id="573004445566", name="María")
    db_session.add(contact)
    await db_session.flush()

    w = Warranty(
        tenant_id=admin_user.tenant_id,
        contact_id=contact.id,
        item="Aire acondicionado LG 12000 BTU",
        installed_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=365),
    )
    db_session.add(w)
    await db_session.commit()

    resp = await client.get("/api/v1/service-data/warranties", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()[0]["item"] == "Aire acondicionado LG 12000 BTU"
    assert resp.json()[0]["contact_name"] == "María"

    # Anular
    resp = await client.put(
        f"/api/v1/service-data/warranties/{w.id}/status",
        json={"status": "voided"},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["status"] == "voided"

    # Anulada ya no aparece en la lista (solo las activas)
    resp = await client.get("/api/v1/service-data/warranties", headers=auth_headers)
    assert resp.json() == []


@pytest.mark.asyncio
async def test_expenses_list_and_create(
    client, auth_headers, db_session, admin_user
):
    """Gastos: ver y registrar desde el panel (igual que por chat)."""
    from app.models import Expense

    db_session.add(
        Expense(
            tenant_id=admin_user.tenant_id,
            description="Gasolina para la moto",
            category="transporte",
            amount=Decimal("20000"),
            expense_date=datetime.now(UTC),
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/service-data/expenses", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()[0]["description"] == "Gasolina para la moto"
    assert resp.json()[0]["amount"] == 20000.0

    # Crear desde el panel
    resp = await client.post(
        "/api/v1/service-data/expenses",
        json={"description": "Almuerzo", "category": "comida", "amount": 15000},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.CREATED
    assert resp.json()["amount"] == 15000.0


@pytest.mark.asyncio
async def test_site_log_list(client, auth_headers, db_session, admin_user):
    from app.models import SiteLog

    contact = Contact(tenant_id=admin_user.tenant_id, wa_id="573007778899", name="Pedro")
    db_session.add(contact)
    await db_session.flush()

    db_session.add(
        SiteLog(
            tenant_id=admin_user.tenant_id,
            contact_id=contact.id,
            title="Instalación en casa de Pedro",
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/service-data/site-log", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()[0]["title"] == "Instalación en casa de Pedro"
    assert resp.json()[0]["status"] == "open"


@pytest.mark.asyncio
async def test_service_data_isolated_by_tenant(
    client, auth_headers, db_session, admin_user
):
    """Los datos de OTRO tenant no se ven."""
    from app.models import InventoryItem, Tenant

    other = Tenant(
        id=uuid.uuid4(), name="Ajeno", slug="ajeno-sd", bot_name="Aura", is_active=True
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        InventoryItem(
            tenant_id=other.id, name="Cable ajeno", unit="m",
            quantity=Decimal("50"), min_quantity=Decimal("0"),
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/service-data/inventory", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    assert all(i["name"] != "Cable ajeno" for i in resp.json())
