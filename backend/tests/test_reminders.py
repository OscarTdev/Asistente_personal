"""Tests de la agenda de recordatorios del panel.

El flujo por chat ya estaba cubierto (F8); aquí se prueba la
contraparte del panel: programar, listar pendientes (vencidos
primero), cerrar (hecho/cancelado) y el aislamiento por tenant.
"""

from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from uuid import uuid4

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
async def test_create_and_list_pending(client: AsyncClient, auth_headers: dict[str, str]):
    """Programar desde el panel; pendientes ordenados por hora (vencidos primero)."""
    past = datetime.now(UTC) - timedelta(hours=1)
    future = datetime.now(UTC) + timedelta(days=2)

    r1 = await client.post(
        "/api/v1/reminders",
        json={"content": "Llamar a Juliana", "remind_at": past.isoformat()},
        headers=auth_headers,
    )
    assert r1.status_code == HTTPStatus.CREATED
    r2 = await client.post(
        "/api/v1/reminders",
        json={"content": "Revisar tablero", "remind_at": future.isoformat()},
        headers=auth_headers,
    )
    assert r2.status_code == HTTPStatus.CREATED

    listing = await client.get(
        "/api/v1/reminders?status=pending", headers=auth_headers
    )
    assert listing.status_code == HTTPStatus.OK
    items = listing.json()
    assert len(items) == 2
    # El vencido va primero: es lo más urgente
    assert items[0]["content"] == "Llamar a Juliana"
    assert items[1]["content"] == "Revisar tablero"


@pytest.mark.asyncio
async def test_close_reminder_done_then_not_found(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Cerrar como hecho; un recordatorio ya cerrado no se vuelve a cerrar."""
    future = datetime.now(UTC) + timedelta(days=1)
    created = await client.post(
        "/api/v1/reminders",
        json={"content": "Comprar breakers", "remind_at": future.isoformat()},
        headers=auth_headers,
    )
    reminder_id = created.json()["id"]

    done = await client.put(
        f"/api/v1/reminders/{reminder_id}",
        json={"status": "done"},
        headers=auth_headers,
    )
    assert done.status_code == HTTPStatus.OK
    assert done.json()["status"] == "done"
    assert done.json()["sent_at"] is not None

    again = await client.put(
        f"/api/v1/reminders/{reminder_id}",
        json={"status": "done"},
        headers=auth_headers,
    )
    assert again.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_cancel_reminder(client: AsyncClient, auth_headers: dict[str, str]):
    """Cancelar saca el recordatorio de pendientes sin marcarlo hecho."""
    future = datetime.now(UTC) + timedelta(days=1)
    created = await client.post(
        "/api/v1/reminders",
        json={"content": "Visitar obra", "remind_at": future.isoformat()},
        headers=auth_headers,
    )
    reminder_id = created.json()["id"]

    cancelled = await client.put(
        f"/api/v1/reminders/{reminder_id}",
        json={"status": "cancelled"},
        headers=auth_headers,
    )
    assert cancelled.status_code == HTTPStatus.OK
    assert cancelled.json()["status"] == "cancelled"

    pending = await client.get(
        "/api/v1/reminders?status=pending", headers=auth_headers
    )
    assert pending.json() == []


@pytest.mark.asyncio
async def test_reminders_isolated_by_tenant(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Los recordatorios de un tenant no se ven ni se cierran desde otro."""
    future = datetime.now(UTC) + timedelta(days=1)
    created = await client.post(
        "/api/v1/reminders",
        json={"content": "Secreto del tenant A", "remind_at": future.isoformat()},
        headers=auth_headers,
    )
    reminder_id = created.json()["id"]

    other_tenant = Tenant(
        id=uuid4(), name="Otro", slug="otro-agenda", bot_name="Aura", is_active=True
    )
    db_session.add(other_tenant)
    await db_session.flush()
    other_admin = User(
        tenant_id=other_tenant.id,
        email="otro-agenda@example.com",
        password_hash="x",
        role="admin",
        is_active=True,
    )
    db_session.add(other_admin)
    await db_session.commit()

    other_token = create_access_token(
        user_id=other_admin.id,
        tenant_id=other_admin.tenant_id,
        role=other_admin.role,
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}

    listing = await client.get("/api/v1/reminders", headers=other_headers)
    assert listing.status_code == HTTPStatus.OK
    assert listing.json() == []

    intrusion = await client.put(
        f"/api/v1/reminders/{reminder_id}",
        json={"status": "cancelled"},
        headers=other_headers,
    )
    assert intrusion.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_reminders_require_auth(client: AsyncClient):
    """Sin token no hay agenda."""
    resp = await client.get("/api/v1/reminders")
    assert resp.status_code == HTTPStatus.UNAUTHORIZED
