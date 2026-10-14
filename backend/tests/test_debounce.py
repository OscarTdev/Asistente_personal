"""Tests de la agrupación de mensajes (spec §7) y del seguimiento endurecido.

- Tres mensajes seguidos → UNA respuesta (el lote se une).
- El tope de espera decide cuándo procesar (tabla de decisión).
- Dos conversaciones no se bloquean entre sí (candado por conversación).
- El seguimiento reclama antes de enviar (dos corridas = un envío) y
  respeta el horario de Colombia (8:00–19:00).
"""

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Contact, Conversation, FollowUp, Message, Quote, Tenant
from app.services import debounce
from app.services.followup import (
    _parse_hours,
    _within_allowed_hours,
    run_followups,
)


class FakeChannel:
    name = "fake"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, to: str, text: str) -> str | None:
        self.sent.append((to, text))
        return None


# ── Tabla de decisión del debounce (spec §7) ───────────────────────────────


def test_debounce_decision_table():
    """Silencio de 5 s procesa; el tope de 20 s procesa; en tránsito espera."""
    D, W = 5.0, 20.0
    # Tres mensajes en 3 segundos (quiet=2 < 5, waited=3 < 20) → esperar
    assert not debounce._should_process(2.0, 3.0, D, W)
    # Silencio de 5 s → procesar
    assert debounce._should_process(5.0, 6.0, D, W)
    # Alguien escribiendo sin parar: esperó 20 s aunque no haya silencio
    assert debounce._should_process(1.0, 20.0, D, W)
    assert debounce._should_process(0.5, 25.0, D, W)


def test_merge_messages():
    """El lote se une en orden; el audio sin transcribir queda marcado."""
    base = {"tenant_id": uuid.uuid4(), "conversation_id": uuid.uuid4()}

    def _msg(direction: str, type_: str, content: str | None) -> Message:
        return Message(
            **base,
            direction=direction,
            type=type_,
            content=content,
            whatsapp_message_id=f"m-{uuid.uuid4()}",
            status="received",
        )

    merged = debounce._merge_messages(
        [
            _msg("in", "text", "necesito"),
            _msg("in", "text", "3 tomacorrientes"),
            _msg("in", "audio", None),
        ]
    )
    assert merged == "necesito\n3 tomacorrientes\n[audio]"


# ── Integración: lote real con Redis real ──────────────────────────────────


@pytest.fixture
async def owner_chat(db_session: AsyncSession, tenant: Tenant, test_engine):
    """Dueño con quoter encendido y un chat listo para el cerebro."""
    from app.models import TenantModule

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

    messages = []
    for content in ("necesito", "3 tomacorrientes", "dobles por favor"):
        message = Message(
            tenant_id=tenant.id,
            conversation_id=conversation.id,
            direction="in",
            type="text",
            content=content,
            whatsapp_message_id=f"in-{uuid.uuid4()}",
            status="received",
        )
        db_session.add(message)
        messages.append(message)
    await db_session.commit()

    return {
        "contact": contact,
        "conversation": conversation,
        "messages": messages,
    }


def _wire_debounce_to_test_db(
    monkeypatch: pytest.MonkeyPatch, test_engine, channel
) -> None:
    """El lote corre con sesiones del motor de tests y el canal falso."""
    monkeypatch.setattr(
        debounce, "SessionFactory", async_sessionmaker(test_engine, expire_on_commit=False)
    )
    monkeypatch.setattr(debounce, "get_channel", lambda name="evolution": channel)
    monkeypatch.setattr(
        "app.services.orchestrator.assistant_service.detect_intent",
        _fake_intent,
    )
    # Tests deterministas: sin auto-agenda; solo process_now explícito
    monkeypatch.setattr(debounce, "_schedule", lambda *args, **kwargs: None)


async def _fake_intent(*, tenant, text):
    from app.schemas.assistant import AssistantIntent

    return AssistantIntent(intention="chat")


@pytest.fixture
def bot_settings(monkeypatch: pytest.MonkeyPatch):
    """Settings del cerebro sin tocar el .env real."""
    from app.core.config import get_settings

    real = get_settings()
    stub = SimpleNamespace(
        evolution_api_key="test-key",
        llm_api_key=real.llm_api_key,
        llm_base_url=real.llm_base_url,
        llm_model=real.llm_model,
        redis_url=real.redis_url,
        debounce_seconds=0.2,
        debounce_max_wait=0.6,
    )
    monkeypatch.setattr("app.services.orchestrator.get_settings", lambda: stub)
    monkeypatch.setattr("app.services.debounce.get_settings", lambda: stub)


async def test_debounce_batches_three_messages_into_one_reply(
    db_session: AsyncSession,
    tenant: Tenant,
    owner_chat: dict,
    test_engine,
    bot_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Tres mensajes seguidos → el cerebro los procesa como UNO."""
    channel = FakeChannel()
    _wire_debounce_to_test_db(monkeypatch, test_engine, channel)

    # LLM del chat con respuesta fija
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="¡Listo!"))]
    )

    class _FakeCompletions:
        async def create(self, **kwargs):
            return fake_response

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    from app.services import orchestrator

    monkeypatch.setattr(orchestrator, "AsyncOpenAI", lambda **kwargs: _FakeClient())

    conversation = owner_chat["conversation"]
    for message in owner_chat["messages"]:
        await debounce.register_message(
            tenant_id=tenant.id,
            conversation_id=conversation.id,
            message_id=message.id,
        )

    processed = await debounce.process_now(conversation.id)
    assert processed == 3

    # Una sola respuesta al lote unificado
    assert len(channel.sent) == 1
    assert channel.sent[0][0] == "573005550000"


async def test_debounce_lock_isolates_conversations(
    db_session: AsyncSession,
    tenant: Tenant,
    owner_chat: dict,
    test_engine,
    bot_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Dos conversaciones: cada lote se procesa por separado, sin bloquearse."""
    channel = FakeChannel()
    _wire_debounce_to_test_db(monkeypatch, test_engine, channel)

    # Segunda conversación del mismo dueño
    other = Conversation(
        tenant_id=tenant.id, contact_id=owner_chat["contact"].id, status="open"
    )
    db_session.add(other)
    await db_session.flush()
    other_message = Message(
        tenant_id=tenant.id,
        conversation_id=other.id,
        direction="in",
        type="text",
        content="otro tema",
        whatsapp_message_id=f"in-{uuid.uuid4()}",
        status="received",
    )
    db_session.add(other_message)
    await db_session.commit()

    first = owner_chat["conversation"]
    await debounce.register_message(
        tenant_id=tenant.id,
        conversation_id=first.id,
        message_id=owner_chat["messages"][0].id,
    )
    await debounce.register_message(
        tenant_id=tenant.id, conversation_id=other.id, message_id=other_message.id
    )

    # Procesar la primera NO consume el lote de la segunda
    taken_first = await debounce.process_now(first.id)
    taken_second = await debounce.process_now(other.id)
    assert taken_first == 1
    assert taken_second == 1


# ── Seguimiento: reclamar antes de enviar + horario (B9) ───────────────────


def test_followup_hours_parsing():
    assert _parse_hours("8,19") == (8, 19)
    assert _parse_hours("basura") == (8, 19)
    assert _parse_hours("10,9") == (8, 19)  # inicio >= fin → default


def test_within_allowed_hours_colombia():
    """Colombia es UTC-5 fijo: 14:00 UTC = 9:00 en Bogotá (dentro)."""
    # 14:00 UTC → 09:00 Colombia: dentro
    assert _within_allowed_hours(datetime(2026, 10, 14, 14, 0, tzinfo=UTC))
    # 10:00 UTC → 05:00 Colombia: de madrugada, fuera
    assert not _within_allowed_hours(datetime(2026, 10, 14, 10, 0, tzinfo=UTC))
    # 23:30 UTC → 18:30 Colombia: dentro
    assert _within_allowed_hours(datetime(2026, 10, 14, 23, 30, tzinfo=UTC))
    # 00:30 UTC → 19:30 Colombia: fuera (pasó las 19:00)
    assert not _within_allowed_hours(datetime(2026, 10, 15, 0, 30, tzinfo=UTC))


async def test_followup_skips_outside_allowed_hours(
    db_session: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
):
    """Fuera del horario la ronda no envía nada (ni reclama rondas)."""
    async def _never(*args, **kwargs):
        return False

    monkeypatch.setattr("app.services.followup._within_allowed_hours", _never)

    result = await run_followups(db_session, channel=FakeChannel())
    assert result.round1_sent == 0
    assert result.round2_sent == 0
    assert result.errors == 0


async def test_followup_claims_before_send_no_duplicates(
    db_session: AsyncSession,
    tenant: Tenant,
    test_engine,
    bot_settings,
):
    """Dos corridas concurrentes sobre la misma cotización → UN solo envío."""
    from datetime import timedelta as td

    from app.models import TenantModule
    from app.services.followup import run_followups as run

    # El reloj no decide el test: siempre dentro del horario permitido
    async def _always(*args, **kwargs):
        return True

    monkeypatch_hours = pytest.MonkeyPatch()
    monkeypatch_hours.setattr(
        "app.services.followup._within_allowed_hours", _always
    )

    # El servicio de seguimiento encendido para el tenant
    db_session.add(
        TenantModule(
            tenant_id=tenant.id,
            module_key="follow_up",
            name="Seguimiento",
            description="",
            category="oficios",
            is_enabled=True,
        )
    )

    # Cotización enviada hace 8 días con contacto, sin respuesta
    contact = Contact(tenant_id=tenant.id, wa_id="573001112233", name="Juliana")
    db_session.add(contact)
    await db_session.flush()
    conversation = Conversation(
        tenant_id=tenant.id, contact_id=contact.id, status="open"
    )
    db_session.add(conversation)
    await db_session.flush()
    db_session.add(
        Quote(
            tenant_id=tenant.id,
            contact_id=contact.id,
            conversation_id=conversation.id,
            status="sent",
            total=45000,
            created_at=datetime.now(UTC) - td(days=8),
        )
    )
    await db_session.commit()

    channel_a = FakeChannel()
    channel_b = FakeChannel()

    # Dos sesiones independientes como dos workers distintos
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session_a, factory() as session_b:
        await asyncio.gather(
            run(session_a, channel=channel_a),
            run(session_b, channel=channel_b),
        )

    total_sent = len(channel_a.sent) + len(channel_b.sent)
    assert total_sent == 1, "dos workers no deben duplicar el seguimiento"

    rows = (
        await db_session.execute(select(FollowUp))
    ).scalars().all()
    assert len(rows) == 1  # el reclamo es único
    monkeypatch_hours.undo()
