"""Tests de los handlers CRM por chat: edit, delete, list, view contact."""

import uuid

from sqlalchemy import select

from app.models import Contact, Conversation
from app.schemas.assistant import AssistantIntent
from app.services.orchestrator import (
    _handle_delete_contact,
    _handle_edit_contact,
    _handle_list_contacts,
    _handle_view_contact,
)


class _CaptureChannel:
    """Canal que no envía nada: solo captura los textos salientes."""

    name = "capture"

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, to: str, text: str) -> str | None:
        self.sent.append((to, text))
        return None


async def _owner_fixture(db_session, tenant):
    """Contacto del dueño + conversación donde chatea con el bot."""
    owner = Contact(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        wa_id="573001112244",
        name="Oscar",
    )
    db_session.add(owner)
    await db_session.flush()
    conv = Conversation(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        contact_id=owner.id,
        status="open",
    )
    db_session.add(conv)
    await db_session.commit()
    return owner, conv


async def _seeded_contacts(db_session, tenant, owner):
    """Crea dos contactos de prueba en el tenant."""
    juliana = Contact(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        wa_id="573001234567",
        name="Juliana",
        email="juliana@test.com",
        notes="cliente frecuente",
        tags=["vip"],
        is_active=True,
    )
    pedro = Contact(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        wa_id="573009876543",
        name="Pedro",
        is_active=True,
    )
    db_session.add_all([juliana, pedro])
    await db_session.commit()
    return juliana, pedro


# ── edit_contact ──────────────────────────────────────────────────────────────


async def test_edit_contact_changes_name(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)
    juliana, _ = await _seeded_contacts(db_session, tenant, owner)
    channel = _CaptureChannel()

    await _handle_edit_contact(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(
            intention="edit_contact",
            contact_name="Juliana",
            description="Juliana Pérez",  # nuevo nombre según contrato LLM
        ),
        text="edita a Juliana a Juliana Pérez",
    )

    updated = (
        await db_session.execute(
            select(Contact).where(Contact.id == juliana.id)
        )
    ).scalar_one()
    assert updated.name == "Juliana Pérez"
    assert any("Juliana Pérez" in text for _, text in channel.sent)
    assert any("nombre" in text for _, text in channel.sent)


async def test_edit_contact_changes_phone(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)
    juliana, _ = await _seeded_contacts(db_session, tenant, owner)
    channel = _CaptureChannel()

    await _handle_edit_contact(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(
            intention="edit_contact",
            contact_name="Juliana",
            contact_phone="3109876543",  # LLM extrae dígitos
        ),
        text="cambia el teléfono de Juliana a 3109876543",
    )

    updated = (
        await db_session.execute(
            select(Contact).where(Contact.id == juliana.id)
        )
    ).scalar_one()
    assert updated.wa_id == "573109876543"
    assert any("teléfono" in text for _, text in channel.sent)


async def test_edit_contact_adds_email(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)
    pedro = (
        await _seeded_contacts(db_session, tenant, owner)
    )[1]  # Pedro no tiene email
    channel = _CaptureChannel()

    await _handle_edit_contact(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(
            intention="edit_contact",
            contact_name="Pedro",
            description="pedro.nuevo@email.com",  # email en description
        ),
        text="ponle email a Pedro: pedro.nuevo@email.com",
    )

    updated = (
        await db_session.execute(
            select(Contact).where(Contact.id == pedro.id)
        )
    ).scalar_one()
    assert updated.email == "pedro.nuevo@email.com"
    assert any("email" in text for _, text in channel.sent)


async def test_edit_contact_adds_note(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)
    juliana, _ = await _seeded_contacts(db_session, tenant, owner)
    channel = _CaptureChannel()

    await _handle_edit_contact(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(
            intention="edit_contact",
            contact_name="Juliana",
            description="cliente VIP obra centro",
        ),
        text="agrega nota a Juliana: cliente VIP obra centro",
    )

    updated = (
        await db_session.execute(
            select(Contact).where(Contact.id == juliana.id)
        )
    ).scalar_one()
    assert "cliente VIP obra centro" in updated.notes
    assert any("nota" in text for _, text in channel.sent)


async def test_edit_contact_rejects_duplicate_phone(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)
    juliana, pedro = await _seeded_contacts(db_session, tenant, owner)
    channel = _CaptureChannel()

    # Intentar cambiar Juliana al número de Pedro
    await _handle_edit_contact(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(
            intention="edit_contact",
            contact_name="Juliana",
            contact_phone=pedro.wa_id,
        ),
        text="cambia el teléfono de Juliana al de Pedro",
    )

    # No debe cambiarse y avisar
    updated = (
        await db_session.execute(
            select(Contact).where(Contact.id == juliana.id)
        )
    ).scalar_one()
    assert updated.wa_id == juliana.wa_id  # sin cambio
    assert any("otro contacto" in text for _, text in channel.sent)


# ── delete_contact ────────────────────────────────────────────────────────────


async def test_delete_contact_soft_deletes(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)
    juliana, _ = await _seeded_contacts(db_session, tenant, owner)
    channel = _CaptureChannel()

    await _handle_delete_contact(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(
            intention="delete_contact",
            contact_name="Juliana",
        ),
        text="borra a Juliana",
    )

    deleted = (
        await db_session.execute(
            select(Contact).where(Contact.id == juliana.id)
        )
    ).scalar_one()
    assert deleted.is_active is False
    assert any("retirado" in text for _, text in channel.sent)


async def test_delete_contact_not_found(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)
    channel = _CaptureChannel()

    await _handle_delete_contact(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(
            intention="delete_contact",
            contact_name="Inexistente",
        ),
        text="borra a Inexistente",
    )

    assert any("No encontré" in text for _, text in channel.sent)


# ── list_contacts ─────────────────────────────────────────────────────────────


async def test_list_contacts_shows_active(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)
    await _seeded_contacts(db_session, tenant, owner)
    channel = _CaptureChannel()

    await _handle_list_contacts(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(intention="list_contacts"),
        text="mis contactos",
    )

    assert len(channel.sent) == 1
    _, text = channel.sent[0]
    assert "Juliana" in text
    assert "Pedro" in text
    assert "573001234567" in text
    assert "573009876543" in text


async def test_list_contacts_empty(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)
    channel = _CaptureChannel()

    await _handle_list_contacts(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(intention="list_contacts"),
        text="mis contactos",
    )

    _, text = channel.sent[0]
    assert "No tienes contactos" in text


# ── view_contact ──────────────────────────────────────────────────────────────


async def test_view_contact_shows_detail(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)
    juliana, _ = await _seeded_contacts(db_session, tenant, owner)
    channel = _CaptureChannel()

    await _handle_view_contact(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(
            intention="view_contact",
            contact_name="Juliana",
        ),
        text="contacto Juliana",
    )

    _, text = channel.sent[0]
    assert "Juliana" in text
    assert "573001234567" in text
    assert "juliana@test.com" in text
    assert "cliente frecuente" in text
    assert "vip" in text


async def test_view_contact_not_found(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)
    channel = _CaptureChannel()

    await _handle_view_contact(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(
            intention="view_contact",
            contact_name="Inexistente",
        ),
        text="contacto Inexistente",
    )

    _, text = channel.sent[0]
    assert "No encontré" in text