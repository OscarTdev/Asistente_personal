"""Tests de obras (bitácora): ver, editar y gestionar desde el panel."""

import uuid
from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import Contact, Tenant
from app.models.site_log import SiteLog
from app.models.site_log_entry import SiteLogEntry


@pytest.fixture
def auth_headers(admin_user) -> dict[str, str]:
    from app.core.security import create_access_token

    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    return {"Authorization": f"Bearer {token}"}


async def _make_contact(db_session, tenant: Tenant, wa_id="573001112233", name="Juan"):
    contact = Contact(tenant_id=tenant.id, wa_id=wa_id, name=name)
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


async def _make_other_tenant_site(db_session) -> SiteLog:
    other = Tenant(
        id=uuid.uuid4(), name="Ajeno", slug="ajeno-obras", bot_name="Ajeno", is_active=True
    )
    db_session.add(other)
    await db_session.flush()
    contact = Contact(tenant_id=other.id, wa_id="573009998877", name="Ajeno")
    db_session.add(contact)
    await db_session.flush()
    site = SiteLog(tenant_id=other.id, contact_id=contact.id, title="Obra ajena")
    db_session.add(site)
    await db_session.commit()
    await db_session.refresh(site)
    return site


@pytest.mark.asyncio
async def test_create_and_get_obra(
    client: AsyncClient, auth_headers, db_session, tenant: Tenant
):
    contact = await _make_contact(db_session, tenant)

    resp = await client.post(
        "/api/v1/obras",
        json={"contact_id": str(contact.id), "title": "Iluminación de la casa de Juan"},
        headers=auth_headers,
    )

    assert resp.status_code == HTTPStatus.CREATED
    body = resp.json()
    assert body["title"] == "Iluminación de la casa de Juan"
    assert body["status"] == "open"
    assert body["contact_name"] == "Juan"
    assert body["entries"] == []

    detail = await client.get(f"/api/v1/obras/{body['id']}", headers=auth_headers)
    assert detail.status_code == HTTPStatus.OK
    assert detail.json()["id"] == body["id"]


@pytest.mark.asyncio
async def test_create_obra_with_other_tenant_contact_is_404(
    client: AsyncClient, auth_headers, db_session
):
    foreign = await _make_other_tenant_site(db_session)

    resp = await client.post(
        "/api/v1/obras",
        json={"contact_id": str(foreign.contact_id), "title": "Intento ajeno"},
        headers=auth_headers,
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_create_obra_rejects_blank_title(
    client: AsyncClient, auth_headers, db_session, tenant: Tenant
):
    contact = await _make_contact(db_session, tenant)

    resp = await client.post(
        "/api/v1/obras",
        json={"contact_id": str(contact.id), "title": "   "},
        headers=auth_headers,
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_entries_crud_and_summary(
    client: AsyncClient, auth_headers, db_session, tenant: Tenant
):
    contact = await _make_contact(db_session, tenant)
    obra = (
        await client.post(
            "/api/v1/obras",
            json={"contact_id": str(contact.id), "title": "Tablero nuevo"},
            headers=auth_headers,
        )
    ).json()
    base = f"/api/v1/obras/{obra['id']}"

    first = await client.post(
        f"{base}/entries",
        json={"note": "Se instaló el tablero", "entry_date": "2026-10-01T10:00:00Z"},
        headers=auth_headers,
    )
    second = await client.post(
        f"{base}/entries",
        json={"note": "Falta conectar fase 3", "entry_date": "2026-10-02T10:00:00Z"},
        headers=auth_headers,
    )
    assert first.status_code == second.status_code == HTTPStatus.CREATED

    detail = (await client.get(base, headers=auth_headers)).json()
    assert [e["note"] for e in detail["entries"]] == [
        "Falta conectar fase 3",  # el más reciente arriba
        "Se instaló el tablero",
    ]
    assert detail["entries_count"] == 2

    # Editar un registro
    entry_id = first.json()["id"]
    patched = await client.patch(
        f"{base}/entries/{entry_id}",
        json={"note": "Se instaló el tablero trifásico"},
        headers=auth_headers,
    )
    assert patched.status_code == HTTPStatus.OK
    assert patched.json()["note"] == "Se instaló el tablero trifásico"

    # Borrar un registro
    deleted = await client.delete(f"{base}/entries/{entry_id}", headers=auth_headers)
    assert deleted.status_code == HTTPStatus.NO_CONTENT
    remaining = (await client.get(base, headers=auth_headers)).json()
    assert remaining["entries_count"] == 1


@pytest.mark.asyncio
async def test_update_title_close_and_reopen(
    client: AsyncClient, auth_headers, db_session, tenant: Tenant
):
    contact = await _make_contact(db_session, tenant)
    obra = (
        await client.post(
            "/api/v1/obras",
            json={"contact_id": str(contact.id), "title": "Obra"},
            headers=auth_headers,
        )
    ).json()
    base = f"/api/v1/obras/{obra['id']}"

    renamed = await client.patch(
        base, json={"title": "Obra de la cocina"}, headers=auth_headers
    )
    assert renamed.json()["title"] == "Obra de la cocina"

    closed = (
        await client.patch(base, json={"status": "closed"}, headers=auth_headers)
    ).json()
    assert closed["status"] == "closed"
    assert closed["closed_at"] is not None

    reopened = (
        await client.patch(base, json={"status": "open"}, headers=auth_headers)
    ).json()
    assert reopened["status"] == "open"
    assert reopened["closed_at"] is None


@pytest.mark.asyncio
async def test_list_filters_by_status_and_search(
    client: AsyncClient, auth_headers, db_session, tenant: Tenant
):
    contact = await _make_contact(db_session, tenant)
    for title in ("Cocina de Juan", "Baño de Juan"):
        await client.post(
            "/api/v1/obras",
            json={"contact_id": str(contact.id), "title": title},
            headers=auth_headers,
        )
    listing = (await client.get("/api/v1/obras", headers=auth_headers)).json()
    assert len(listing) == 2

    cocina = [o for o in listing if o["title"] == "Cocina de Juan"][0]
    await client.patch(
        f"/api/v1/obras/{cocina['id']}", json={"status": "closed"}, headers=auth_headers
    )

    open_only = (
        await client.get("/api/v1/obras?estado=open", headers=auth_headers)
    ).json()
    assert [o["title"] for o in open_only] == ["Baño de Juan"]

    found = (await client.get("/api/v1/obras?q=cocina", headers=auth_headers)).json()
    assert [o["title"] for o in found] == ["Cocina de Juan"]


@pytest.mark.asyncio
async def test_other_tenant_obra_is_invisible(
    client: AsyncClient, auth_headers, db_session
):
    foreign = await _make_other_tenant_site(db_session)
    url = f"/api/v1/obras/{foreign.id}"

    assert (await client.get(url, headers=auth_headers)).status_code == HTTPStatus.NOT_FOUND
    assert (
        await client.patch(url, json={"title": "x"}, headers=auth_headers)
    ).status_code == HTTPStatus.NOT_FOUND
    assert (
        await client.post(f"{url}/entries", json={"note": "x"}, headers=auth_headers)
    ).status_code == HTTPStatus.NOT_FOUND
    assert (await client.delete(url, headers=auth_headers)).status_code == HTTPStatus.NOT_FOUND

    # y no aparece en el listado
    listing = (await client.get("/api/v1/obras", headers=auth_headers)).json()
    assert all(o["id"] != str(foreign.id) for o in listing)


@pytest.mark.asyncio
async def test_delete_obra_removes_entries(
    client: AsyncClient, auth_headers, db_session, tenant: Tenant
):
    contact = await _make_contact(db_session, tenant)
    obra = (
        await client.post(
            "/api/v1/obras",
            json={"contact_id": str(contact.id), "title": "Temporal"},
            headers=auth_headers,
        )
    ).json()
    await client.post(
        f"/api/v1/obras/{obra['id']}/entries",
        json={"note": "algo"},
        headers=auth_headers,
    )

    resp = await client.delete(f"/api/v1/obras/{obra['id']}", headers=auth_headers)

    assert resp.status_code == HTTPStatus.NO_CONTENT
    assert (
        await client.get(f"/api/v1/obras/{obra['id']}", headers=auth_headers)
    ).status_code == HTTPStatus.NOT_FOUND
    left = (
        (
            await db_session.execute(
                select(SiteLogEntry).where(SiteLogEntry.site_id == uuid.UUID(obra["id"]))
            )
        )
        .scalars()
        .all()
    )
    assert left == []
