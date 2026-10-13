"""Tests del CRUD de clientes (contactos de WhatsApp) del panel."""

import uuid
from datetime import UTC, datetime
from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models import Contact, Conversation, Message, Tenant, User


@pytest.fixture
def auth_headers(admin_user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def contact(db_session: AsyncSession, tenant: Tenant) -> Contact:
    contact = Contact(
        tenant_id=tenant.id,
        wa_id="573001112233",
        name="María Pérez",
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


@pytest.fixture
async def contact_with_history(
    db_session: AsyncSession, tenant: Tenant, contact: Contact
) -> tuple[Contact, Message]:
    """Contacto con conversación y un mensaje entrante."""
    conversation = Conversation(
        tenant_id=tenant.id,
        contact_id=contact.id,
        status="open",
        last_message_at=datetime.now(UTC),
    )
    db_session.add(conversation)
    await db_session.flush()

    message = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction="in",
        type="text",
        content="Necesito una cotización para mi apartamento",
        whatsapp_message_id="wamid-test-1",
        status="received",
    )
    db_session.add(message)
    await db_session.commit()
    return contact, message


@pytest.mark.asyncio
async def test_list_contacts_empty(client: AsyncClient, auth_headers: dict[str, str]):
    """Sin clientes, la lista es vacía pero válida."""
    resp = await client.get("/api/v1/contacts", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_shows_contact_with_interaction(
    client: AsyncClient,
    auth_headers: dict[str, str],
    contact_with_history: tuple[Contact, Message],
):
    """La lista trae el cliente con su última interacción y conteo de mensajes."""
    contact, _ = contact_with_history
    resp = await client.get("/api/v1/contacts", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["id"] == str(contact.id)
    assert item["name"] == "María Pérez"
    assert item["messages_count"] == 1
    assert item["last_interaction_at"] is not None


@pytest.mark.asyncio
async def test_search_by_name(
    client: AsyncClient, auth_headers: dict[str, str], contact: Contact
):
    """La búsqueda por nombre filtra la lista."""
    resp = await client.get(
        "/api/v1/contacts", params={"search": "María"}, headers=auth_headers
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["total"] == 1

    resp = await client.get(
        "/api/v1/contacts", params={"search": "Nadie"}, headers=auth_headers
    )
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_get_contact_detail_with_messages(
    client: AsyncClient,
    auth_headers: dict[str, str],
    contact_with_history: tuple[Contact, Message],
):
    """La ficha del cliente incluye sus mensajes recientes."""
    contact, message = contact_with_history
    resp = await client.get(f"/api/v1/contacts/{contact.id}", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()
    assert data["id"] == str(contact.id)
    assert len(data["recent_messages"]) == 1
    assert data["recent_messages"][0]["id"] == str(message.id)
    assert data["recent_messages"][0]["content"].startswith("Necesito")


@pytest.mark.asyncio
async def test_update_contact_notes_and_name(
    client: AsyncClient, auth_headers: dict[str, str], contact: Contact
):
    """El admin puede editar nombre y notas del cliente."""
    resp = await client.put(
        f"/api/v1/contacts/{contact.id}",
        json={"name": "María P. Gómez", "notes": "Cliente frecuente de Laureles"},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()
    assert data["name"] == "María P. Gómez"
    assert data["notes"] == "Cliente frecuente de Laureles"


@pytest.mark.asyncio
async def test_soft_delete_hides_contact_by_default(
    client: AsyncClient, auth_headers: dict[str, str], contact: Contact
):
    """DELETE retira al cliente (soft) sin perder su historial."""
    resp = await client.delete(f"/api/v1/contacts/{contact.id}", headers=auth_headers)
    assert resp.status_code == HTTPStatus.NO_CONTENT

    # Por defecto no aparece en la lista
    resp = await client.get("/api/v1/contacts", headers=auth_headers)
    assert resp.json()["total"] == 0

    # Su ficha sigue accesible con is_active=False
    resp = await client.get(f"/api/v1/contacts/{contact.id}", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["is_active"] is False

    # Con active_only=False vuelve a aparecer
    resp = await client.get(
        "/api/v1/contacts", params={"active_only": False}, headers=auth_headers
    )
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_contacts_isolated_by_tenant(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
):
    """Un cliente de otro tenant es invisible: lista, ficha, edición y borrado."""
    other_tenant = Tenant(
        id=uuid.uuid4(),
        name="Otro negocio",
        slug="otro",
        bot_name="Beta",
        is_active=True,
    )
    db_session.add(other_tenant)
    await db_session.flush()

    other_contact = Contact(
        tenant_id=other_tenant.id,
        wa_id="573009998877",
        name="Foráneo",
    )
    db_session.add(other_contact)
    await db_session.commit()

    resp = await client.get("/api/v1/contacts", headers=auth_headers)
    assert resp.json()["total"] == 0

    resp = await client.get(f"/api/v1/contacts/{other_contact.id}", headers=auth_headers)
    assert resp.status_code == HTTPStatus.NOT_FOUND

    resp = await client.put(
        f"/api/v1/contacts/{other_contact.id}",
        json={"name": "Hack"},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND

    resp = await client.delete(f"/api/v1/contacts/{other_contact.id}", headers=auth_headers)
    assert resp.status_code == HTTPStatus.NOT_FOUND
