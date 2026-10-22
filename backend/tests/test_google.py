"""Tests de la integración con Google Workspace (OAuth por tenant).

Cubre: el flujo OAuth (authorize/callback/disconnect con state JWT),
los endpoints de uso con Google mockeado (Gmail, Sheets) y los
handlers del orquestador (resumen de correo, borrador con confirmación,
agenda, exportar a hoja, informe en Docs).
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.core.security import create_access_token
from app.models import (
    Contact,
    Conversation,
    Expense,
    GoogleConnection,
    PendingAction,
    Tenant,
    User,
)
from app.schemas.assistant import AssistantIntent
from app.services import google_oauth, orchestrator


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id, tenant_id=user.tenant_id, role=user.role
    )
    return {"Authorization": f"Bearer {token}"}


class FakeChannel(Channel):
    """Canal de prueba: registra envíos en lugar de llamar a Evolution."""

    name = "fake"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def parse_incoming(self, payload):
        raise NotImplementedError

    async def send_text(self, to: str, text: str) -> str | None:
        self.sent.append((to, text))
        return None

    async def send_document(
        self, to: str, file_name: str, content_base64: str, mimetype: str
    ) -> str | None:
        return None


async def _seed_owner_chat(
    db_session: AsyncSession, tenant: Tenant
) -> dict[str, Any]:
    """Contacto + conversación del dueño para llamar handlers directo."""
    contact = Contact(tenant_id=tenant.id, wa_id="573005550000", name="El Dueño")
    db_session.add(contact)
    await db_session.flush()
    conversation = Conversation(
        tenant_id=tenant.id, contact_id=contact.id, status="open"
    )
    db_session.add(conversation)
    await db_session.commit()
    return {"contact": contact, "conversation": conversation}


async def _add_connection(
    db_session: AsyncSession,
    tenant: Tenant,
    *,
    expired: bool = False,
    refresh_token: str | None = "rt-test",
) -> GoogleConnection:
    conn = GoogleConnection(
        tenant_id=tenant.id,
        google_email="duño@gmail.com",
        access_token="at-test",
        refresh_token=refresh_token,
        token_expires_at=(
            datetime.now(UTC) - timedelta(hours=1)
            if expired
            else datetime.now(UTC) + timedelta(hours=1)
        ),
        scopes=["email"],
    )
    db_session.add(conn)
    await db_session.commit()
    await db_session.refresh(conn)
    return conn


# ── API: conexión OAuth ──────────────────────────────────────────────────────


async def test_status_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/google/status")
    assert response.status_code == 401


async def test_status_disconnected(
    client: AsyncClient, admin_user: User
):
    response = await client.get("/api/v1/google/status", headers=_headers(admin_user))
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is False
    assert data["google_email"] is None


async def test_authorize_without_config_returns_422(
    client: AsyncClient, admin_user: User
):
    """Sin GOOGLE_CLIENT_ID el endpoint lo dice con claridad (nunca 500)."""
    response = await client.post("/api/v1/google/authorize", headers=_headers(admin_user))
    assert response.status_code == 422
    assert "GOOGLE_CLIENT_ID" in response.json()["detail"]


async def test_authorize_returns_google_url_with_state(
    client: AsyncClient, admin_user: User, monkeypatch: pytest.MonkeyPatch
):
    stub = SimpleNamespace(
        google_client_id="test-client-id.apps.googleusercontent.com",
        google_client_secret="test-secret",
        google_redirect_uri="",
        panel_base_url="http://localhost:5173",
        jwt_secret="x" * 40,
        jwt_algorithm="HS256",
    )
    monkeypatch.setattr("app.services.google_oauth.get_settings", lambda: stub)

    response = await client.post("/api/v1/google/authorize", headers=_headers(admin_user))
    assert response.status_code == 200
    url = response.json()["authorization_url"]
    assert "accounts.google.com/o/oauth2/v2/auth" in url
    assert "client_id=test-client-id" in url
    assert "access_type=offline" in url
    assert "state=" in url
    assert "google%2Fcallback" in url  # redirect_uri por defecto = panel/callback


async def test_callback_rejects_garbage_state(
    client: AsyncClient, admin_user: User
):
    response = await client.post(
        "/api/v1/google/callback",
        json={"code": "a" * 20, "state": "x" * 40},  # largo válido, JWT falso
        headers=_headers(admin_user),
    )
    assert response.status_code == 401


async def test_callback_rejects_other_tenant_state(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    tenant: Tenant,
):
    """El state de OTRO negocio no puede conectar esta cuenta (cross-tenant)."""
    other = Tenant(name="Otro", slug="otro", bot_name="Aura")
    db_session.add(other)
    await db_session.commit()

    state = google_oauth.build_state_token(other.id)
    response = await client.post(
        "/api/v1/google/callback",
        json={"code": "a" * 20, "state": state},
        headers=_headers(admin_user),
    )
    assert response.status_code == 403


async def test_callback_success_saves_connection(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    tenant: Tenant,
):
    async def fake_exchange(code: str) -> dict:
        return {
            "access_token": "at-123",
            "refresh_token": "rt-123",
            "expires_in": 3600,
            "scope": "email https://www.googleapis.com/auth/gmail.readonly",
        }

    async def fake_email(token: str) -> str:
        return "oscar@gmail.com"

    state = google_oauth.build_state_token(tenant.id)
    # El router usa los atributos del módulo → parchear ahí
    from app.services import google_oauth as oauth_module

    monkeypatched_exchange = oauth_module.exchange_code
    monkeypatched_email = oauth_module.fetch_user_email
    oauth_module.exchange_code = fake_exchange  # type: ignore[assignment]
    oauth_module.fetch_user_email = fake_email  # type: ignore[assignment]
    try:
        response = await client.post(
            "/api/v1/google/callback",
            json={"code": "c" * 20, "state": state},
            headers=_headers(admin_user),
        )
    finally:
        oauth_module.exchange_code = monkeypatched_exchange
        oauth_module.fetch_user_email = monkeypatched_email

    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["google_email"] == "oscar@gmail.com"

    conn = (
        await db_session.execute(
            select(GoogleConnection).where(GoogleConnection.tenant_id == tenant.id)
        )
    ).scalar_one()
    assert conn.google_email == "oscar@gmail.com"
    assert conn.is_active is True


async def test_disconnect_removes_connection(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    tenant: Tenant,
):
    await _add_connection(db_session, tenant)
    response = await client.delete(
        "/api/v1/google/disconnect", headers=_headers(admin_user)
    )
    assert response.status_code == 200
    assert response.json()["disconnected"] is True
    remaining = (
        await db_session.execute(
            select(GoogleConnection).where(GoogleConnection.tenant_id == tenant.id)
        )
    ).scalar_one_or_none()
    assert remaining is None


async def test_non_admin_cannot_connect(
    client: AsyncClient, db_session: AsyncSession, tenant: Tenant
):
    member = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="team@example.com",
        password_hash="x",
        role="user",  # roles válidos: 'admin' | 'user' (ck_users_role)
        is_active=True,
    )
    db_session.add(member)
    await db_session.commit()
    response = await client.post("/api/v1/google/authorize", headers=_headers(member))
    assert response.status_code == 403


# ── API: uso de los servicios (Google mockeado) ─────────────────────────────


async def test_sheets_export_creates_sheet(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    tenant: Tenant,
):
    await _add_connection(db_session, tenant)
    # Gasto a mediodía Bogotá del día 1 del mes local: siempre dentro de
    # la ventana (inmune al borde de mes UTC/Colombia)
    now_col = datetime.now(UTC) - timedelta(hours=5)
    safe_date = now_col.replace(day=1, hour=12, minute=0, second=0, microsecond=0)
    db_session.add(
        Expense(
            tenant_id=tenant.id,
            description="20 metros de cable",
            category="materiales",
            amount=Decimal("45000"),
            expense_date=safe_date + timedelta(hours=5),
        )
    )
    await db_session.commit()

    calls: dict[str, Any] = {}

    async def fake_create(token: str, *, title: str) -> dict:
        calls["title"] = title
        return {"spreadsheet_id": "ss-1", "url": "https://sheets/x", "title": title}

    async def fake_write(token: str, *, spreadsheet_id: str, values: list) -> None:
        calls["values"] = values

    from app.services import google_api as api_module

    original_create = api_module.sheets_create_spreadsheet
    original_write = api_module.sheets_write_values
    api_module.sheets_create_spreadsheet = fake_create  # type: ignore[assignment]
    api_module.sheets_write_values = fake_write  # type: ignore[assignment]
    try:
        response = await client.post(
            "/api/v1/google/sheets/export-expenses", headers=_headers(admin_user)
        )
    finally:
        api_module.sheets_create_spreadsheet = original_create
        api_module.sheets_write_values = original_write

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://sheets/x"
    assert data["rows"] == 1
    assert calls["values"][0] == ["Fecha", "Descripción", "Categoría", "Valor (COP)"]
    # COP entero: el total no arrastra ".00" (fix de la auditoría)
    assert calls["values"][-1] == ["", "", "TOTAL", "45000"]


# ── Orquestador: handlers de chat ────────────────────────────────────────────


async def test_email_summary_replies_with_inbox(
    db_session: AsyncSession, tenant: Tenant
):
    chat = await _seed_owner_chat(db_session, tenant)
    fake = FakeChannel()

    async def fake_inbox(db, *, tenant_id, max_results=5):
        return [
            {
                "from": "Juan Pérez <juan@x.com>",
                "subject": "Presupuesto",
                "date": "Wed, 21 Oct 2026",
                "snippet": "Necesito una cotización",
            }
        ]

    from app.services import google_actions as actions_module

    original = actions_module.summarize_inbox
    actions_module.summarize_inbox = fake_inbox  # type: ignore[assignment]
    try:
        await orchestrator._handle_google_email(
            db_session,
            tenant=tenant,
            channel=fake,
            conversation=chat["conversation"],
            wa_id="573005550000",
            intent=AssistantIntent(intention="google_email"),
        )
    finally:
        actions_module.summarize_inbox = original

    assert len(fake.sent) == 1
    assert "📬" in fake.sent[0][1]
    assert "Presupuesto" in fake.sent[0][1]


async def test_email_draft_creates_pending_action(
    db_session: AsyncSession, tenant: Tenant
):
    await _add_connection(db_session, tenant)  # el borrador exige conexión
    chat = await _seed_owner_chat(db_session, tenant)
    target = Contact(
        tenant_id=tenant.id,
        wa_id="573009990001",
        name="Juliana",
        email="juliana@x.com",
    )
    db_session.add(target)
    await db_session.commit()
    fake = FakeChannel()

    await orchestrator._handle_google_email(
        db_session,
        tenant=tenant,
        channel=fake,
        conversation=chat["conversation"],
        wa_id="573005550000",
        intent=AssistantIntent(
            intention="google_email",
            contact_name="Juliana",
            message_text="Hola, llego a las 3 pm.",
        ),
    )

    assert "¿Te lo envío?" in fake.sent[-1][1]
    pending = (
        await db_session.execute(
            select(PendingAction).where(
                PendingAction.conversation_id == chat["conversation"].id
            )
        )
    ).scalar_one()
    assert pending.action_type == "send_email"
    assert pending.payload["to"] == "juliana@x.com"
    assert pending.status == "pending"


async def test_email_without_contact_email_asks_for_it(
    db_session: AsyncSession, tenant: Tenant
):
    await _add_connection(db_session, tenant)  # el borrador exige conexión
    chat = await _seed_owner_chat(db_session, tenant)
    target = Contact(tenant_id=tenant.id, wa_id="573009990002", name="Pedro")
    db_session.add(target)
    await db_session.commit()
    fake = FakeChannel()

    await orchestrator._handle_google_email(
        db_session,
        tenant=tenant,
        channel=fake,
        conversation=chat["conversation"],
        wa_id="573005550000",
        intent=AssistantIntent(
            intention="google_email",
            contact_name="Pedro",
            message_text="Hola",
        ),
    )
    assert "correo" in fake.sent[-1][1].lower()


async def test_confirmation_sends_email(
    db_session: AsyncSession, tenant: Tenant
):
    """El dueño dice «sí» → el correo sale desde su cuenta Google."""
    chat = await _seed_owner_chat(db_session, tenant)
    db_session.add(
        PendingAction(
            tenant_id=tenant.id,
            conversation_id=chat["conversation"].id,
            action_type="send_email",
            payload={
                "to": "juliana@x.com",
                "subject": "Mensaje",
                "body": "Hola",
                "contact_id": str(uuid.uuid4()),
            },
        )
    )
    await db_session.commit()
    fake = FakeChannel()

    sent_to: dict[str, str] = {}

    async def fake_send(db, *, tenant_id, to, subject, body):
        sent_to.update({"to": to, "subject": subject})

    from app.services import google_actions as actions_module

    original = actions_module.send_email
    actions_module.send_email = fake_send  # type: ignore[assignment]
    try:
        handled = await orchestrator._handle_confirmation(
            db_session,
            tenant=tenant,
            channel=fake,
            conversation=chat["conversation"],
            wa_id="573005550000",
            text="sí",
        )
    finally:
        actions_module.send_email = original

    assert handled is True
    assert sent_to["to"] == "juliana@x.com"
    assert "✅" in fake.sent[-1][1]


async def test_calendar_lists_events(
    db_session: AsyncSession, tenant: Tenant
):
    chat = await _seed_owner_chat(db_session, tenant)
    fake = FakeChannel()

    async def fake_events(db, *, tenant_id, days=7):
        return [
            {
                "summary": "Visita de revisión",
                "start": {"dateTime": "2026-10-20T20:00:00-05:00"},
                "end": {"dateTime": "2026-10-20T21:00:00-05:00"},
            }
        ]

    from app.services import google_actions as actions_module

    original = actions_module.upcoming_events
    actions_module.upcoming_events = fake_events  # type: ignore[assignment]
    try:
        await orchestrator._handle_google_calendar(
            db_session,
            tenant=tenant,
            channel=fake,
            conversation=chat["conversation"],
            wa_id="573005550000",
            intent=AssistantIntent(
                intention="google_calendar", message_text="qué tengo mañana"
            ),
        )
    finally:
        actions_module.upcoming_events = original

    assert "📅" in fake.sent[-1][1]
    assert "Visita de revisión" in fake.sent[-1][1]


async def test_calendar_create_converts_naive_bogota_time(
    db_session: AsyncSession, tenant: Tenant
):
    """Naive 15:00 = hora Colombia → 20:00 UTC (UTC-5)."""
    chat = await _seed_owner_chat(db_session, tenant)
    fake = FakeChannel()
    captured: dict[str, Any] = {}

    async def fake_create(
        db, *, tenant_id, summary, start_at,
        duration_minutes=60, description=None,
    ):
        captured["summary"] = summary
        captured["start_at"] = start_at
        return {"summary": summary}

    from app.services import google_actions as actions_module

    original = actions_module.create_event
    actions_module.create_event = fake_create  # type: ignore[assignment]
    try:
        await orchestrator._handle_google_calendar(
            db_session,
            tenant=tenant,
            channel=fake,
            conversation=chat["conversation"],
            wa_id="573005550000",
            intent=AssistantIntent(
                intention="google_calendar",
                message_text="Visita de revisión",
                remind_at="2026-10-20T15:00:00",
            ),
        )
    finally:
        actions_module.create_event = original

    assert "✅ Agendado" in fake.sent[-1][1]
    assert captured["summary"] == "Visita de revisión"
    start = captured["start_at"]
    assert start.utcoffset() == timedelta(0)  # viene en UTC
    assert start.hour == 20  # 15:00 Bogotá = 20:00 UTC


async def test_sheets_handler_replies_with_link(
    db_session: AsyncSession, tenant: Tenant
):
    chat = await _seed_owner_chat(db_session, tenant)
    fake = FakeChannel()

    async def fake_export(db, *, tenant):
        return {"url": "https://sheets/gastos", "title": "Gastos octubre", "rows": 3}

    from app.services import google_actions as actions_module

    original = actions_module.export_expenses_sheet
    actions_module.export_expenses_sheet = fake_export  # type: ignore[assignment]
    try:
        await orchestrator._handle_google_sheets(
            db_session,
            tenant=tenant,
            channel=fake,
            conversation=chat["conversation"],
            wa_id="573005550000",
        )
    finally:
        actions_module.export_expenses_sheet = original

    assert "📊" in fake.sent[-1][1]
    assert "https://sheets/gastos" in fake.sent[-1][1]


async def test_docs_handler_replies_with_link(
    db_session: AsyncSession, tenant: Tenant
):
    chat = await _seed_owner_chat(db_session, tenant)
    fake = FakeChannel()

    async def fake_report(db, *, tenant):
        return {"url": "https://docs/informe", "title": "Informe octubre"}

    from app.services import google_actions as actions_module

    original = actions_module.create_month_report_doc
    actions_module.create_month_report_doc = fake_report  # type: ignore[assignment]
    try:
        await orchestrator._handle_google_docs(
            db_session,
            tenant=tenant,
            channel=fake,
            conversation=chat["conversation"],
            wa_id="573005550000",
        )
    finally:
        actions_module.create_month_report_doc = original

    assert "📄" in fake.sent[-1][1]
    assert "https://docs/informe" in fake.sent[-1][1]


async def test_not_connected_tells_owner_to_connect(
    db_session: AsyncSession, tenant: Tenant
):
    """Sin conexión el bot guía al dueño en vez de fallar en silencio."""
    chat = await _seed_owner_chat(db_session, tenant)
    fake = FakeChannel()

    await orchestrator._handle_google_email(
        db_session,
        tenant=tenant,
        channel=fake,
        conversation=chat["conversation"],
        wa_id="573005550000",
        intent=AssistantIntent(intention="google_email"),
    )
    assert "🔗" in fake.sent[-1][1]
    assert "Mi negocio" in fake.sent[-1][1]


# ── google_oauth: tokens y state ─────────────────────────────────────────────


async def test_state_token_roundtrip(db_session: AsyncSession, tenant: Tenant):
    state = google_oauth.build_state_token(tenant.id)
    assert google_oauth.verify_state_token(state) == tenant.id


async def test_state_token_expired_rejects(tenant: Tenant):
    with pytest.raises(google_oauth.GoogleAuthError):
        google_oauth.verify_state_token("no-es-un-jwt")


async def test_get_access_token_without_connection_raises(
    db_session: AsyncSession, tenant: Tenant
):
    with pytest.raises(google_oauth.GoogleNotConnected):
        await google_oauth.get_access_token(db_session, tenant_id=tenant.id)


async def test_expired_token_without_refresh_deactivates_connection(
    db_session: AsyncSession, tenant: Tenant
):
    conn = await _add_connection(db_session, tenant, expired=True, refresh_token=None)
    with pytest.raises(google_oauth.GoogleAuthError):
        await google_oauth.get_access_token(db_session, tenant_id=tenant.id)
    await db_session.refresh(conn)
    assert conn.is_active is False


async def test_valid_token_returned_without_refresh(
    db_session: AsyncSession, tenant: Tenant
):
    await _add_connection(db_session, tenant)
    token = await google_oauth.get_access_token(db_session, tenant_id=tenant.id)
    assert token == "at-test"


# ── Regresión: bugs cazados por la auditoría de agentes (22 oct) ─────────────


async def test_callback_rejects_used_code(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    tenant: Tenant,
):
    """Google rechaza el code (expirado/reusado) → 409, no 500."""
    async def failing_exchange(code: str) -> dict:
        raise google_oauth.GoogleAuthError(
            "Google rechazó la conexión; inténtalo de nuevo"
        )

    state = google_oauth.build_state_token(tenant.id)
    from app.services import google_oauth as oauth_module

    original = oauth_module.exchange_code
    oauth_module.exchange_code = failing_exchange  # type: ignore[assignment]
    try:
        response = await client.post(
            "/api/v1/google/callback",
            json={"code": "c" * 20, "state": state},
            headers=_headers(admin_user),
        )
    finally:
        oauth_module.exchange_code = original

    assert response.status_code == 409
    assert "rechazó" in response.json()["detail"]


async def test_confirmation_send_failure_keeps_pending(
    db_session: AsyncSession, tenant: Tenant
):
    """Si el envío falla, la acción vuelve a 'pending': reintento con «sí»."""
    chat = await _seed_owner_chat(db_session, tenant)
    db_session.add(
        PendingAction(
            tenant_id=tenant.id,
            conversation_id=chat["conversation"].id,
            action_type="send_email",
            payload={
                "to": "juliana@x.com",
                "subject": "Mensaje",
                "body": "Hola",
                "contact_id": str(uuid.uuid4()),
            },
        )
    )
    await db_session.commit()
    fake = FakeChannel()

    async def failing_send(db, *, tenant_id, to, subject, body):
        raise RuntimeError("Google caído")

    from app.services import google_actions as actions_module

    original = actions_module.send_email
    actions_module.send_email = failing_send  # type: ignore[assignment]
    try:
        handled = await orchestrator._handle_confirmation(
            db_session,
            tenant=tenant,
            channel=fake,
            conversation=chat["conversation"],
            wa_id="573005550000",
            text="sí",
        )
    finally:
        actions_module.send_email = original

    assert handled is True
    assert "reintentar" in fake.sent[-1][1].lower()
    pending = (
        await db_session.execute(
            select(PendingAction).where(
                PendingAction.conversation_id == chat["conversation"].id
            )
        )
    ).scalar_one()
    assert pending.status == "pending"  # vuelve a estar disponible


async def test_draft_without_connection_tells_owner(
    db_session: AsyncSession, tenant: Tenant
):
    """Sin cuenta Google no se ofrece el borrador: se guía al dueño."""
    chat = await _seed_owner_chat(db_session, tenant)
    target = Contact(
        tenant_id=tenant.id,
        wa_id="573009990001",
        name="Juliana",
        email="juliana@x.com",
    )
    db_session.add(target)
    await db_session.commit()
    fake = FakeChannel()

    await orchestrator._handle_google_email(
        db_session,
        tenant=tenant,
        channel=fake,
        conversation=chat["conversation"],
        wa_id="573005550000",
        intent=AssistantIntent(
            intention="google_email",
            contact_name="Juliana",
            message_text="Hola",
        ),
    )

    assert "🔗" in fake.sent[-1][1]
    pending = (
        await db_session.execute(
            select(PendingAction).where(
                PendingAction.conversation_id == chat["conversation"].id
            )
        )
    ).scalar_one_or_none()
    assert pending is None  # no se crea borrador imposible de enviar


async def test_month_window_is_colombia_not_utc(
    db_session: AsyncSession, tenant: Tenant
):
    """Un gasto del 31/10 20:00 Bogotá (01:00 UTC nov) es de OCTUBRE."""
    from app.services.expenses import monthly_summary

    # 31 de octubre, 20:00 Bogotá = 01:00 UTC del 1 de noviembre
    expense = Expense(
        tenant_id=tenant.id,
        description="Cable",
        category="materiales",
        amount=Decimal("1000"),
        expense_date=datetime(2026, 11, 1, 1, 0, tzinfo=UTC),
    )
    db_session.add(expense)
    await db_session.commit()

    # "Este mes" a las 31 oct 23:00 HORA COLOMBIA → octubre local:
    # el gasto de hace 3 horas SIGUE dentro del mes
    oct_summary = await monthly_summary(
        db_session,
        tenant_id=tenant.id,
        month=datetime(2026, 10, 31, 23, 0),  # hora Colombia
    )
    assert oct_summary["total"] == Decimal("1000")

    # Ya en noviembre local (1 nov 04:00 Bogotá): el gasto ya no entra
    nov_summary = await monthly_summary(
        db_session,
        tenant_id=tenant.id,
        month=datetime(2026, 11, 1, 4, 0),  # hora Colombia
    )
    assert nov_summary["total"] == Decimal("0")
