"""Tests de la Fase 8: notas y recordatorios por chat."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Note, Reminder, Tenant
from app.services import notes as notes_service
from app.services import orchestrator
from app.services.notes import detect_note_action


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


@pytest.fixture
def bot_settings(monkeypatch: pytest.MonkeyPatch):
    stub = SimpleNamespace(evolution_api_key="test-key")
    monkeypatch.setattr("app.services.orchestrator.get_settings", lambda: stub)


async def _seed_owner(db_session, tenant):
    from app.models import Contact, Conversation, Message, TenantModule

    db_session.add(
        TenantModule(
            tenant_id=tenant.id,
            module_key="quoter",
            name="Cotizador",
            description="",
            category="oficios",
            is_enabled=True,
        )
    )
    tenant.wa_id = "573005550000"
    contact = Contact(tenant_id=tenant.id, wa_id="573005550000", name="Dueño")
    db_session.add(contact)
    await db_session.flush()
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
        content="",
        whatsapp_message_id=f"in-{uuid.uuid4()}",
        status="received",
    )
    db_session.add(message)
    await db_session.commit()
    return {"contact": contact, "conversation": conversation, "message": message}


async def _say(
    db_session, tenant, chat, channel, monkeypatch,
    text, intention="note", **intent_kwargs
):
    from app.schemas.assistant import AssistantIntent
    from app.schemas.quotes import ExtractResponse

    async def fake_intent(*, tenant, text):
        return AssistantIntent(intention=intention, **intent_kwargs)

    async def fake_extract(db, *, tenant_id, text):
        return ExtractResponse(suggestions=[], raw_extraction=[])

    monkeypatch.setattr(
        orchestrator.assistant_service, "detect_intent", fake_intent
    )
    monkeypatch.setattr(
        orchestrator.ai_service, "extract_items_from_text", fake_extract
    )
    chat["message"].content = text
    await db_session.commit()
    await orchestrator.handle_incoming(
        db_session, tenant=tenant, channel=channel,
        message=chat["message"], contact=chat["contact"],
        conversation=chat["conversation"],
    )


# ── Detección de acción ────────────────────────────────────────────────────


def test_detect_note_action():
    assert detect_note_action("guarda una nota: comprar cable") == "save"
    assert detect_note_action("qué notas tengo") == "list"
    assert detect_note_action("busca la nota del cable") == "search"
    assert detect_note_action("borra la nota del cable") == "delete"
    assert detect_note_action("apunta que debo 20 mil") == "save"


# ── Notas por chat ─────────────────────────────────────────────────────────


async def test_save_note_by_chat(
    db_session: AsyncSession, tenant: Tenant, bot_settings, monkeypatch
):
    channel = FakeChannel()
    chat = await _seed_owner(db_session, tenant)

    await _say(
        db_session, tenant, chat, channel, monkeypatch,
        "guarda una nota: comprar 20 metros de cable THHN",
    )

    note = (
        await db_session.execute(select(Note))
    ).scalars().one()
    assert "comprar 20 metros de cable" in note.content
    assert note.tenant_id == tenant.id
    assert note.is_active is True
    assert "Anotado" in channel.sent[-1][1]


async def test_list_notes_by_chat(
    db_session: AsyncSession, tenant: Tenant, bot_settings, monkeypatch
):
    channel = FakeChannel()
    chat = await _seed_owner(db_session, tenant)

    # Crear notas
    await notes_service.save_note(db_session, tenant_id=tenant.id, content="Comprar cable")
    await notes_service.save_note(db_session, tenant_id=tenant.id, content="Llamar a Juliana")

    await _say(
        db_session, tenant, chat, channel, monkeypatch,
        "qué notas tengo",
    )

    assert "Comprar cable" in channel.sent[-1][1]
    assert "Llamar a Juliana" in channel.sent[-1][1]


async def test_search_notes_by_chat(
    db_session: AsyncSession, tenant: Tenant, bot_settings, monkeypatch
):
    channel = FakeChannel()
    chat = await _seed_owner(db_session, tenant)

    await notes_service.save_note(
        db_session, tenant_id=tenant.id, content="Comprar 20m cable THHN #12"
    )
    await notes_service.save_note(
        db_session, tenant_id=tenant.id,
        content="Llamar a Juliana sobre el presupuesto",
    )

    await _say(
        db_session, tenant, chat, channel, monkeypatch,
        "busca la nota del cable",
    )

    assert "cable" in channel.sent[-1][1].lower()
    assert "Juliana" not in channel.sent[-1][1]  # no debe mostrar la otra nota


async def test_delete_note_by_chat(
    db_session: AsyncSession, tenant: Tenant, bot_settings, monkeypatch
):
    channel = FakeChannel()
    chat = await _seed_owner(db_session, tenant)

    await notes_service.save_note(db_session, tenant_id=tenant.id, content="Comprar cable ya")
    await notes_service.save_note(db_session, tenant_id=tenant.id, content="Llamar a Juliana")

    await _say(
        db_session, tenant, chat, channel, monkeypatch,
        "borra la nota del cable",
    )

    # La nota del cable está inactiva (borrado lógico)
    notes = (
        await db_session.execute(
            select(Note).where(Note.is_active.is_(True))
        )
    ).scalars().all()
    assert len(notes) == 1
    assert "Juliana" in notes[0].content  # la otra sigue viva
    assert "Borré" in channel.sent[-1][1]


# ── Recordatorios ──────────────────────────────────────────────────────────


async def test_create_reminder_by_chat(
    db_session: AsyncSession, tenant: Tenant, bot_settings, monkeypatch
):
    channel = FakeChannel()
    chat = await _seed_owner(db_session, tenant)

    await _say(
        db_session, tenant, chat, channel, monkeypatch,
        "recuérdame llamar a Juliana el jueves",
        intention="reminder",
        message_text="Llamar a Juliana",
        remind_at="2026-10-16T13:00:00+00:00",
    )

    reminder = (
        await db_session.execute(select(Reminder))
    ).scalar_one()
    assert reminder.tenant_id == tenant.id
    assert "Llamar a Juliana" in reminder.content
    assert reminder.status == "pending"
    assert reminder.remind_at is not None
    assert "Recordaré" in channel.sent[-1][1] or "recordaré" in channel.sent[-1][1]


async def test_due_reminders_query(
    db_session: AsyncSession, tenant: Tenant
):
    # Recordatorio vencido (hace 1 hora)
    await notes_service.save_reminder(
        db_session, tenant_id=tenant.id,
        content="Ya es la hora",
        remind_at=datetime.now(UTC) - timedelta(hours=1),
    )
    # Recordatorio futuro (mañana)
    await notes_service.save_reminder(
        db_session, tenant_id=tenant.id,
        content="Mañana temprano",
        remind_at=datetime.now(UTC) + timedelta(days=1),
    )

    due = await notes_service.due_reminders(db_session)
    assert len(due) == 1
    # due_reminders retorna tuplas (reminder, notif_type): el principal
    # vencido llega como ("Ya es la hora", "main").
    assert due[0][1] == "main"
    assert "Ya es la hora" in due[0][0].content


async def test_due_reminders_pre_notifications(
    db_session: AsyncSession, tenant: Tenant
):
    """Pre-notificaciones: un recordatorio a 2h aparece como '2h' y
    uno a 30min como '30m'; uno a 3 horas no aparece todavía."""
    now = datetime.now(UTC)
    await notes_service.save_reminder(
        db_session, tenant_id=tenant.id,
        content="En dos horas exactas",
        remind_at=now + timedelta(hours=2),
    )
    await notes_service.save_reminder(
        db_session, tenant_id=tenant.id,
        content="En media hora exacta",
        remind_at=now + timedelta(minutes=30),
    )
    await notes_service.save_reminder(
        db_session, tenant_id=tenant.id,
        content="En tres horas",
        remind_at=now + timedelta(hours=3),
    )

    due = await notes_service.due_reminders(db_session)
    types = {r.content: t for r, t in due}
    assert types.get("En dos horas exactas") == "2h"
    assert types.get("En media hora exacta") == "30m"
    assert "En tres horas" not in types

    # Tras marcar la pre-notificación 2h como enviada, no vuelve a salir
    two_hours_reminder = next(r for r, _ in due if _ == "2h")
    await notes_service.mark_reminder_sent(
        db_session, two_hours_reminder, notification_type="2h"
    )
    due_again = await notes_service.due_reminders(db_session)
    assert all(
        not (r.content == "En dos horas exactas" and t == "2h")
        for r, t in due_again
    )
