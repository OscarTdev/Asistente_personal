"""Tests del handler add_contact: agregar contactos al CRM por chat."""

import uuid

from sqlalchemy import select

from app.models import Contact, Conversation
from app.schemas.assistant import AssistantIntent
from app.services.assistant import _now_context
from app.services.orchestrator import _handle_add_contact


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


async def test_add_contact_creates_contact_and_conversation(
    db_session, tenant
):
    owner, conv = await _owner_fixture(db_session, tenant)
    channel = _CaptureChannel()

    await _handle_add_contact(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(
            intention="add_contact",
            contact_name="Juliana",
            contact_phone="3001234567",  # 10 dígitos → +57
        ),
    )

    # El contacto quedó creado con el wa_id normalizado
    contact = (
        await db_session.execute(
            select(Contact).where(
                Contact.tenant_id == tenant.id,
                Contact.wa_id == "573001234567",
            )
        )
    ).scalar_one()
    assert contact.name == "Juliana"

    # Y con su conversación abierta
    new_conv = (
        await db_session.execute(
            select(Conversation).where(Conversation.contact_id == contact.id)
        )
    ).scalar_one()
    assert new_conv.status == "open"

    # El bot confirmó
    assert any("Juliana" in text for _, text in channel.sent)


async def test_add_contact_phone_with_country_code(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)

    await _handle_add_contact(
        db_session,
        tenant=tenant,
        channel=_CaptureChannel(),
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(
            intention="add_contact",
            contact_name="Pedro",
            contact_phone="573001239999",
        ),
    )
    contact = (
        await db_session.execute(
            select(Contact).where(
                Contact.wa_id == "573001239999",
            )
        )
    ).scalar_one()
    assert contact.name == "Pedro"


async def test_add_contact_rejects_bad_phone(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)
    channel = _CaptureChannel()

    await _handle_add_contact(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(
            intention="add_contact",
            contact_name="Malo",
            contact_phone="123",  # inválido
        ),
    )
    contacts = (
        await db_session.execute(select(Contact))
    ).scalars().all()
    assert all(c.wa_id != "123" for c in contacts)
    assert any("no me parece un celular válido" in t for _, t in channel.sent)


async def test_add_contact_rejects_duplicate_number(db_session, tenant):
    owner, conv = await _owner_fixture(db_session, tenant)
    existing = Contact(
        tenant_id=tenant.id, wa_id="573001234567", name="Juliana Vieja"
    )
    db_session.add(existing)
    await db_session.commit()
    channel = _CaptureChannel()

    await _handle_add_contact(
        db_session,
        tenant=tenant,
        channel=channel,
        conversation=conv,
        wa_id=owner.wa_id,
        intent=AssistantIntent(
            intention="add_contact",
            contact_name="Juliana Nueva",
            contact_phone="3001234567",  # mismo número normalizado
        ),
    )
    total = len(
        (
            await db_session.execute(
                select(Contact).where(
                    Contact.wa_id == "573001234567"
                )
            )
        ).scalars().all()
    )
    assert total == 1
    assert any("Ya tienes" in t for _, t in channel.sent)


def test_now_context_has_today():
    ctx = _now_context()
    assert "FECHA ACTUAL (Colombia)" in ctx
    assert "UTC-5" in ctx
    # Contiene el año en curso
    from datetime import UTC, datetime

    assert str(datetime.now(UTC).year) in ctx