"""Tests de identidades por canal: el núcleo no depende de la puerta.

Un mismo humano por WhatsApp, Telegram o la app es el mismo contacto con
el mismo historial. La resolución perezosa mantiene el legado de WhatsApp
y el onboarding limpia las identidades de prospecto al completarse.
"""

import uuid
from http import HTTPStatus

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChannelIdentity, Contact, Tenant, User
from app.services.identity import (
    KIND_CONTACT,
    link_identity,
    resolve_identity,
)


def _headers(user: User) -> dict[str, str]:
    from app.core.security import create_access_token

    token = create_access_token(
        user_id=user.id, tenant_id=user.tenant_id, role=user.role
    )
    return {"Authorization": f"Bearer {token}"}


def _whatsapp_payload(wa_id: str, text: str = "Hola") -> dict:
    return {
        "event": "messages.upsert",
        "instance": "aura",
        "data": {
            "key": {
                "id": uuid.uuid4().hex[:16].upper(),
                "remoteJid": f"{wa_id}@s.whatsapp.net",
                "fromMe": False,
            },
            "pushName": "Técnico",
            "message": {"conversation": text},
        },
    }


@pytest.fixture
async def tenant2(db_session: AsyncSession) -> Tenant:
    t = Tenant(
        id=uuid.uuid4(),
        name="Taller Gómez",
        slug="taller-gomez",
        bot_name="Aura",
        is_active=True,
    )
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest.fixture
async def platform_admin(db_session: AsyncSession, tenant: Tenant) -> User:
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="platform@example.com",
        password_hash="x",
        role="admin",
        is_active=True,
        is_platform_admin=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def juliana(db_session: AsyncSession, tenant: Tenant) -> Contact:
    contact = Contact(tenant_id=tenant.id, wa_id="573009990001", name="Juliana")
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


# ── Resolución: la misma persona por cualquier puerta ─────────────────────


async def test_same_human_same_core_across_channels(
    db_session: AsyncSession, tenant: Tenant, juliana: Contact
):
    """Juliana por Telegram es la misma Juliana: mismo contacto y tenant."""
    await link_identity(
        db_session,
        tenant=tenant,
        contact=juliana,
        kind=KIND_CONTACT,
        channel="telegram",
        external_id="@jgomez",
    )
    await db_session.commit()

    resolved = await resolve_identity(
        db_session,
        channel="telegram",
        external_id="@jgomez",
        fallback_tenant=tenant,
    )
    assert resolved.contact.id == juliana.id
    assert resolved.tenant.id == tenant.id
    assert resolved.is_owner is False
    # Su historial no se duplica: es exactamente el mismo contacto
    assert resolved.created is False


async def test_lazy_whatsapp_owner_identity(
    db_session: AsyncSession, tenant: Tenant, tenant2: Tenant
):
    """El legado (tenants.wa_id) crea la identidad del dueño perezosamente."""
    tenant2.wa_id = "573005551111"
    await db_session.commit()

    first = await resolve_identity(
        db_session,
        channel="whatsapp",
        external_id="573005551111",
        fallback_tenant=tenant,
    )
    assert first.is_owner is True
    assert first.tenant.id == tenant2.id
    assert first.created is True  # su contacto se creó en SU tenant

    # Segunda vuelta: la identidad ya existe y no se duplica
    second = await resolve_identity(
        db_session,
        channel="whatsapp",
        external_id="573005551111",
        fallback_tenant=tenant,
    )
    assert second.is_owner is True
    assert second.contact.id == first.contact.id

    count = (
        await db_session.execute(
            select(ChannelIdentity).where(
                ChannelIdentity.external_id == "573005551111"
            )
        )
    ).scalars().all()
    assert len(count) == 1


async def test_lazy_whatsapp_known_contact(
    db_session: AsyncSession, tenant: Tenant, tenant2: Tenant, juliana: Contact
):
    """Un cliente conocido (contacts.wa_id) resuelve a su propio tenant."""
    resolved = await resolve_identity(
        db_session,
        channel="whatsapp",
        external_id="573009990001",
        fallback_tenant=tenant2,  # fallback DISTINTO: la identidad debe ganar
    )
    assert resolved.contact.id == juliana.id
    assert resolved.tenant.id == tenant.id
    assert resolved.is_owner is False


async def test_unknown_number_is_a_prospect(
    db_session: AsyncSession, tenant: Tenant
):
    """Desconocido → contacto nuevo en el tenant fallback (el embudo decide)."""
    resolved = await resolve_identity(
        db_session,
        channel="whatsapp",
        external_id="573007778888",
        fallback_tenant=tenant,
        display_name="Push",
    )
    assert resolved.created is True
    assert resolved.tenant.id == tenant.id
    assert resolved.is_owner is False
    assert resolved.contact.name == "Push"


# ── Ingesta: el webhook pasa por identidades ──────────────────────────────


async def test_webhook_creates_identity(
    client, db_session: AsyncSession, tenant: Tenant, webhook_headers: dict
):
    """Un mensaje entrante deja su identidad registrada."""
    response = await client.post(
        "/api/v1/webhooks/whatsapp",
        headers={"X-Tenant-Slug": tenant.slug, **webhook_headers},
        json=_whatsapp_payload("573006667777"),
    )
    assert response.status_code == HTTPStatus.OK

    identity = (
        await db_session.execute(
            select(ChannelIdentity).where(
                ChannelIdentity.channel == "whatsapp",
                ChannelIdentity.external_id == "573006667777",
            )
        )
    ).scalar_one()
    assert identity.tenant_id == tenant.id
    assert identity.kind == KIND_CONTACT


async def test_webhook_routes_via_registered_identity(
    client, db_session: AsyncSession, tenant: Tenant, tenant2: Tenant,
    juliana: Contact, webhook_headers: dict,
):
    """La identidad gana sobre el fallback del slug: el mensaje cae en SU tenant."""
    await link_identity(
        db_session,
        tenant=tenant,
        contact=juliana,
        kind=KIND_CONTACT,
        channel="whatsapp",
        external_id="573009990001",
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/webhooks/whatsapp",
        # slug del tenant2 a propósito: la identidad de Juliana debe ganar
        headers={"X-Tenant-Slug": tenant2.slug, **webhook_headers},
        json=_whatsapp_payload("573009990001"),
    )
    assert response.status_code == HTTPStatus.OK

    from app.models import Message

    message = (
        await db_session.execute(
            select(Message).where(Message.direction == "in")
        )
    ).scalars().one()
    assert message.tenant_id == tenant.id


# ── Onboarding: de prospecto a dueño sin identidades viejas ────────────────


async def test_onboarding_clears_prospect_identity(
    db_session: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
):
    """Al registrarse, su identidad de prospecto desaparece: ya tiene tenant propio."""
    from types import SimpleNamespace

    from app.services import orchestrator

    monkeypatch.setattr(
        "app.services.orchestrator.get_settings",
        lambda: SimpleNamespace(evolution_api_key="test-key"),
    )

    class FakeChannel:
        name = "fake"
        identity_channel = "whatsapp"

        def __init__(self) -> None:
            self.sent: list[tuple[str, str]] = []

        async def parse_incoming(self, payload):
            raise NotImplementedError

        async def send_text(self, to: str, text: str) -> str | None:
            self.sent.append((to, text))
            return None

    channel = FakeChannel()
    contact = Contact(
        tenant_id=tenant.id, wa_id="573009997777", name="Prospecto"
    )
    db_session.add(contact)
    await db_session.flush()

    from app.models import Conversation, Message

    conversation = Conversation(
        tenant_id=tenant.id, contact_id=contact.id, status="open"
    )
    db_session.add(conversation)
    await db_session.flush()

    message = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction="in",
        type="text",
        content="Hola",
        whatsapp_message_id=f"in-{uuid.uuid4()}",
        status="received",
    )
    db_session.add(message)
    await db_session.flush()
    # Identidad perezosa de prospecto (la que crea la ingesta)
    db_session.add(
        ChannelIdentity(
            tenant_id=tenant.id,
            contact_id=contact.id,
            kind=KIND_CONTACT,
            channel="whatsapp",
            external_id="573009997777",
        )
    )
    await db_session.commit()

    # Flujo de onboarding completo: nombre del bot → nombre del dueño
    async def fake_intent(*, tenant, text):
        from app.schemas.assistant import AssistantIntent

        return AssistantIntent(intention="chat")

    monkeypatch.setattr(
        "app.services.assistant.detect_intent", fake_intent
    )
    await orchestrator.handle_incoming(
        db_session, tenant=tenant, channel=channel,  # type: ignore[arg-type]
        message=message, contact=contact, conversation=conversation,
    )
    message.content = "Aura"
    await db_session.commit()
    await orchestrator.handle_incoming(
        db_session, tenant=tenant, channel=channel,  # type: ignore[arg-type]
        message=message, contact=contact, conversation=conversation,
    )
    message.content = "Juan Pérez"
    await db_session.commit()
    await orchestrator.handle_incoming(
        db_session, tenant=tenant, channel=channel,  # type: ignore[arg-type]
        message=message, contact=contact, conversation=conversation,
    )

    # El tenant propio existe y su identidad apunta a él como dueño
    new_tenant = (
        await db_session.execute(
            select(Tenant).where(Tenant.slug == "juan-perez")
        )
    ).scalar_one()
    assert new_tenant.wa_id == "573009997777"

    stale = (
        await db_session.execute(
            select(ChannelIdentity).where(
                ChannelIdentity.external_id == "573009997777",
                ChannelIdentity.tenant_id == tenant.id,
            )
        )
    ).scalar_one_or_none()
    assert stale is None  # la identidad de prospecto se limpió

    # Su próximo mensaje lo resuelve como DUEÑO de su propio tenant
    resolved = await resolve_identity(
        db_session,
        channel="whatsapp",
        external_id="573009997777",
        fallback_tenant=tenant,
    )
    assert resolved.is_owner is True
    assert resolved.tenant.id == new_tenant.id


# ── API admin: vincular puertas de un contacto ─────────────────────────────


async def test_admin_identity_link_list_delete(
    client, db_session: AsyncSession, tenant: Tenant, juliana: Contact,
    platform_admin: User,
):
    """El admin vincula el Telegram de Juliana, lo lista y lo desvincula."""
    base = f"/api/v1/admin/tenants/{tenant.id}/contacts/{juliana.id}/identities"

    created = await client.post(
        base,
        headers=_headers(platform_admin),
        json={"channel": "telegram", "external_id": "@jgomez", "kind": "contact"},
    )
    assert created.status_code == HTTPStatus.CREATED
    identity_id = created.json()["id"]
    assert created.json()["channel"] == "telegram"

    listed = await client.get(base, headers=_headers(platform_admin))
    assert listed.status_code == HTTPStatus.OK
    assert len(listed.json()) == 1
    assert listed.json()[0]["external_id"] == "@jgomez"

    # Duplicado (mismo canal+id externo) → 409
    duplicate = await client.post(
        base,
        headers=_headers(platform_admin),
        json={"channel": "telegram", "external_id": "@jgomez", "kind": "contact"},
    )
    assert duplicate.status_code == HTTPStatus.CONFLICT

    deleted = await client.delete(
        f"/api/v1/admin/tenants/{tenant.id}/identities/{identity_id}",
        headers=_headers(platform_admin),
    )
    assert deleted.status_code == HTTPStatus.NO_CONTENT

    listed = await client.get(base, headers=_headers(platform_admin))
    assert len(listed.json()) == 0


async def test_admin_identity_requires_platform_admin(
    client, admin_user: User, tenant: Tenant, juliana: Contact
):
    response = await client.post(
        f"/api/v1/admin/tenants/{tenant.id}/contacts/{juliana.id}/identities",
        headers=_headers(admin_user),
        json={"channel": "telegram", "external_id": "@x"},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
