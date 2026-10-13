"""Tests de la capa de suscripciones: planes, entitlements, routing y pagos MP."""

import hashlib
import hmac
import time
import uuid
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.modules_registry import AVAILABLE_MODULES, plan_allows
from app.core.security import create_access_token
from app.models import (
    Contact,
    Conversation,
    Message,
    PaymentMethod,
    Subscription,
    Tenant,
    TenantModule,
    User,
)
from app.services.entitlements import apply_plan


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id, tenant_id=user.tenant_id, role=user.role
    )
    return {"Authorization": f"Bearer {token}"}


async def _module_flags(db_session: AsyncSession, tenant_id) -> dict[str, bool]:
    return {
        tm.module_key: tm.is_enabled
        for tm in (
            await db_session.execute(
                select(TenantModule).where(TenantModule.tenant_id == tenant_id)
            )
        ).scalars()
    }


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
async def chat_seed(db_session: AsyncSession, tenant: Tenant) -> dict:
    """Un chat entre el bot y un cliente del tenant principal."""
    from datetime import timedelta

    now = datetime.now(UTC)
    contact = Contact(tenant_id=tenant.id, wa_id="573001112233", name="Juliana")
    db_session.add(contact)
    await db_session.flush()

    conversation = Conversation(
        tenant_id=tenant.id, contact_id=contact.id, status="open"
    )
    db_session.add(conversation)
    await db_session.flush()

    messages = [
        Message(
            tenant_id=tenant.id,
            conversation_id=conversation.id,
            direction="in",
            type="text",
            content="Hola, ¿me cotizas 3 tomacorrientes?",
            whatsapp_message_id=f"in-{uuid.uuid4()}",
            status="received",
            created_at=now - timedelta(minutes=2),
        ),
        Message(
            tenant_id=tenant.id,
            conversation_id=conversation.id,
            direction="out",
            type="text",
            content="Claro, con gusto. Te la envío en un momento.",
            whatsapp_message_id=f"out-{uuid.uuid4()}",
            status="sent",
            created_at=now - timedelta(minutes=1),
        ),
    ]
    db_session.add_all(messages)
    await db_session.commit()
    return {"contact": contact, "conversation": conversation, "messages": messages}


def _whatsapp_payload(wa_id: str, text: str) -> dict:
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


# ── Entitlements (registro) ─────────────────────────────────────────────────


def test_plan_entitlements_registry():
    """El contrato de planes: qué autoriza cada nivel."""
    assert plan_allows("trial", "quoter")
    assert not plan_allows("trial", "reminders")
    assert not plan_allows("trial", "follow_up")

    assert plan_allows("freemium", "quoter")
    assert plan_allows("freemium", "reminders")
    assert not plan_allows("freemium", "follow_up")

    # Premium: todos los servicios del registro
    for module in AVAILABLE_MODULES:
        assert plan_allows("premium", module["key"])

    # Plan desconocido → conservador como trial
    assert not plan_allows("otra-cosa", "reminders")


# ── apply_plan (servicio) ───────────────────────────────────────────────────


async def test_apply_plan_freemium_enables_entitled_modules(
    db_session: AsyncSession, tenant: Tenant
):
    """Trial → freemium: quoter y reminders encendidos, el resto apagados."""
    await apply_plan(db_session, tenant_id=tenant.id, plan="freemium")

    await db_session.refresh(tenant)
    assert tenant.plan == "freemium"

    modules = await _module_flags(db_session, tenant.id)
    assert modules["quoter"] is True
    assert modules["reminders"] is True
    assert modules["follow_up"] is False
    assert modules["collections"] is False

    sub = (
        await db_session.execute(
            select(Subscription).where(Subscription.tenant_id == tenant.id)
        )
    ).scalar_one()
    assert sub.plan_key == "freemium"
    assert sub.status == "freemium"


async def test_apply_plan_premium_then_trial_downgrade(
    db_session: AsyncSession, tenant: Tenant
):
    """Premium enciende todo; volver a trial apaga lo que no incluye."""
    await apply_plan(db_session, tenant_id=tenant.id, plan="premium")
    modules = await _module_flags(db_session, tenant.id)
    assert all(modules.values())

    await apply_plan(db_session, tenant_id=tenant.id, plan="trial")
    modules = await _module_flags(db_session, tenant.id)
    assert modules["quoter"] is True
    assert not modules["reminders"]
    assert not modules["follow_up"]


async def test_apply_plan_unknown_raises(db_session: AsyncSession, tenant: Tenant):
    with pytest.raises(ValueError, match="Plan desconocido"):
        await apply_plan(db_session, tenant_id=tenant.id, plan="gold")


# ── API admin (autorización) ────────────────────────────────────────────────


async def test_admin_endpoints_require_platform_admin(
    client: AsyncClient, admin_user: User
):
    """Un admin de tenant NO es admin de la plataforma: 403."""
    response = await client.get("/api/v1/admin/tenants", headers=_headers(admin_user))
    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_list_tenants(
    client: AsyncClient, platform_admin: User, tenant: Tenant, tenant2: Tenant
):
    response = await client.get(
        "/api/v1/admin/tenants", headers=_headers(platform_admin)
    )
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    slugs = {t["slug"] for t in data}
    assert slugs == {"personal", "taller-gomez"}
    by_slug = {t["slug"]: t for t in data}
    assert by_slug["personal"]["plan"] == "trial"
    assert by_slug["personal"]["plan_label"] == "Prueba"
    assert by_slug["personal"]["plan_price_cop"] == 0
    assert by_slug["taller-gomez"]["total_modules"] == len(AVAILABLE_MODULES)


# ── Cambio de plan y métodos de pago ────────────────────────────────────────


async def test_change_plan_endpoint_syncs_modules(
    client: AsyncClient, platform_admin: User, tenant: Tenant
):
    response = await client.patch(
        f"/api/v1/admin/tenants/{tenant.id}/plan",
        headers=_headers(platform_admin),
        json={"plan": "premium"},
    )
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["plan"] == "premium"
    assert data["subscription"]["status"] == "active"
    assert data["subscription"]["current_period_end"] is not None
    # Todos los módulos quedan autorizados y encendidos
    assert all(m["entitled"] for m in data["modules"])
    assert all(m["is_enabled"] for m in data["modules"])


async def test_change_plan_invalid_value(
    client: AsyncClient, platform_admin: User, tenant: Tenant
):
    response = await client.patch(
        f"/api/v1/admin/tenants/{tenant.id}/plan",
        headers=_headers(platform_admin),
        json={"plan": "gold"},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_payment_method_activates_freemium(
    client: AsyncClient, platform_admin: User, tenant: Tenant
):
    """Registrar el método de pago de un trial → freemium automático."""
    response = await client.post(
        f"/api/v1/admin/tenants/{tenant.id}/payment-method",
        headers=_headers(platform_admin),
        json={"brand": "Visa", "last4": "4242", "exp_month": 12, "exp_year": 2030},
    )
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["plan"] == "freemium"

    assert len(data["payment_methods"]) == 1
    pm = data["payment_methods"][0]
    assert pm["brand"] == "Visa"
    assert pm["last4"] == "4242"
    # PCI: el token nunca viaja al panel
    assert "provider_token" not in pm


async def test_delete_last_payment_method_downgrades_to_trial(
    client: AsyncClient, platform_admin: User, tenant: Tenant
):
    add = await client.post(
        f"/api/v1/admin/tenants/{tenant.id}/payment-method",
        headers=_headers(platform_admin),
        json={"brand": "Visa", "last4": "4242"},
    )
    assert add.json()["plan"] == "freemium"
    pm_id = add.json()["payment_methods"][0]["id"]

    response = await client.delete(
        f"/api/v1/admin/tenants/{tenant.id}/payment-methods/{pm_id}",
        headers=_headers(platform_admin),
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()["plan"] == "trial"


async def test_payment_method_invalid_last4(
    client: AsyncClient, platform_admin: User, tenant: Tenant
):
    response = await client.post(
        f"/api/v1/admin/tenants/{tenant.id}/payment-method",
        headers=_headers(platform_admin),
        json={"brand": "Visa", "last4": "42x2"},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


# ── Servicios por tenant (contrato de entitlements) ─────────────────────────


async def test_toggle_module_respects_plan(
    client: AsyncClient,
    platform_admin: User,
    tenant: Tenant,
    db_session: AsyncSession,
):
    """Nadie enciende un servicio que el plan del cliente no incluye."""
    # Sin filas de módulos aún → 404 (primero se aplica un plan)
    response = await client.put(
        f"/api/v1/admin/tenants/{tenant.id}/modules/reminders",
        headers=_headers(platform_admin),
        json={"is_enabled": True},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND

    # Inicializa el tenant en trial
    await apply_plan(db_session, tenant_id=tenant.id, plan="trial")

    # Encender reminders en trial → 422 (fuera del plan)
    response = await client.put(
        f"/api/v1/admin/tenants/{tenant.id}/modules/reminders",
        headers=_headers(platform_admin),
        json={"is_enabled": True},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    # Apagar quoter en trial → permitido (está dentro del plan)
    response = await client.put(
        f"/api/v1/admin/tenants/{tenant.id}/modules/quoter",
        headers=_headers(platform_admin),
        json={"is_enabled": False},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()["is_enabled"] is False

    # Con premium, reminders ya se puede encender
    await client.patch(
        f"/api/v1/admin/tenants/{tenant.id}/plan",
        headers=_headers(platform_admin),
        json={"plan": "premium"},
    )
    response = await client.put(
        f"/api/v1/admin/tenants/{tenant.id}/modules/reminders",
        headers=_headers(platform_admin),
        json={"is_enabled": True},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()["is_enabled"] is True


# ── Historial de chat (aislado por tenant) ─────────────────────────────────


async def test_chat_history_listing(
    client: AsyncClient, platform_admin: User, tenant: Tenant, chat_seed: dict
):
    response = await client.get(
        f"/api/v1/admin/tenants/{tenant.id}/conversations",
        headers=_headers(platform_admin),
    )
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["contact_name"] == "Juliana"
    assert item["contact_wa_id"] == "573001112233"
    assert item["messages_count"] == 2

    response = await client.get(
        f"/api/v1/admin/tenants/{tenant.id}/conversations"
        f"/{chat_seed['conversation'].id}/messages",
        headers=_headers(platform_admin),
    )
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["total"] == 2
    directions = [m["direction"] for m in data["items"]]
    assert directions == ["in", "out"]  # orden cronológico


async def test_chat_history_isolated_between_tenants(
    client: AsyncClient,
    platform_admin: User,
    tenant: Tenant,
    tenant2: Tenant,
    chat_seed: dict,
):
    """El chat de un tenant no se ve desde el otro — ni listado ni por id."""
    response = await client.get(
        f"/api/v1/admin/tenants/{tenant2.id}/conversations",
        headers=_headers(platform_admin),
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()["total"] == 0

    # Pedir los mensajes de la conversación de OTRO tenant → 404
    response = await client.get(
        f"/api/v1/admin/tenants/{tenant2.id}/conversations"
        f"/{chat_seed['conversation'].id}/messages",
        headers=_headers(platform_admin),
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


# ── WhatsApp del dueño (llave de enrutamiento) ──────────────────────────────


async def test_set_tenant_whatsapp_and_clash(
    client: AsyncClient, platform_admin: User, tenant: Tenant, tenant2: Tenant
):
    response = await client.put(
        f"/api/v1/admin/tenants/{tenant2.id}/whatsapp",
        headers=_headers(platform_admin),
        json={"wa_id": "573005551111"},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()["wa_id"] == "573005551111"

    # Un número no puede pertenecer a dos tenants
    response = await client.put(
        f"/api/v1/admin/tenants/{tenant.id}/whatsapp",
        headers=_headers(platform_admin),
        json={"wa_id": "573005551111"},
    )
    assert response.status_code == HTTPStatus.CONFLICT

    # Formato inválido → 422
    response = await client.put(
        f"/api/v1/admin/tenants/{tenant.id}/whatsapp",
        headers=_headers(platform_admin),
        json={"wa_id": "abc123"},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_whatsapp_routes_registered_technician_to_their_tenant(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant: Tenant,
    tenant2: Tenant,
    webhook_headers: dict,
):
    """Un número compartido: el técnico registrado cae en SU tenant."""
    tenant2.wa_id = "573005551111"
    await db_session.commit()

    response = await client.post(
        "/api/v1/webhooks/whatsapp",
        # slug del OTRO tenant a propósito: el routing por wa_id gana
        headers={"X-Tenant-Slug": tenant.slug, **webhook_headers},
        json=_whatsapp_payload("573005551111", "Cotízame 3 tomacorrientes"),
    )
    assert response.status_code == HTTPStatus.OK

    message = (
        await db_session.execute(select(Message))
    ).scalars().one()
    assert message.tenant_id == tenant2.id


async def test_whatsapp_unknown_sender_falls_back_to_slug_tenant(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant: Tenant,
    webhook_headers: dict,
):
    """Número no registrado → behavior original: tenant del slug."""
    response = await client.post(
        "/api/v1/webhooks/whatsapp",
        headers={"X-Tenant-Slug": tenant.slug, **webhook_headers},
        json=_whatsapp_payload("573007778888", "Hola"),
    )
    assert response.status_code == HTTPStatus.OK

    message = (
        await db_session.execute(select(Message))
    ).scalars().one()
    assert message.tenant_id == tenant.id


# ── Webhook de MercadoPago ─────────────────────────────────────────────────


def _mp_settings_stub(monkeypatch: pytest.MonkeyPatch, *, secret: str, token: str):
    """Parcha los settings que usa el endpoint del webhook de MP."""
    from types import SimpleNamespace

    from app.core.config import Settings  # noqa: F401  (tipo de referencia)

    stub = SimpleNamespace(
        mercadopago_webhook_secret=secret,
        mercadopago_access_token=token,
    )
    monkeypatch.setattr("app.api.v1.webhooks.get_settings", lambda: stub)


def _mp_signature(secret: str, *, ts: str, request_id: str, data_id: str) -> str:
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    digest = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={digest}"


async def test_mp_webhook_without_secret_is_ignored(client: AsyncClient):
    """Fase manual: sin MERCADOPAGO_WEBHOOK_SECRET la notificación se acusa y sale."""
    response = await client.post(
        "/api/v1/webhooks/payments/mercadopago",
        json={"type": "payment", "data": {"id": "123456"}},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ignored"}


async def test_mp_webhook_rejects_bad_signature(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _mp_settings_stub(monkeypatch, secret="test-secret", token="")

    response = await client.post(
        "/api/v1/webhooks/payments/mercadopago",
        headers={"x-signature": "ts=123,v1=deadbeef", "x-request-id": "req-1"},
        json={"type": "payment", "data": {"id": "123456"}},
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_mp_webhook_valid_signature_accepted(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """Firma válida y fresca (sin access token: queda pendiente de la fase 2) → 200 ok."""
    _mp_settings_stub(monkeypatch, secret="test-secret", token="")

    ts = str(int(time.time()))
    signature = _mp_signature(
        "test-secret", ts=ts, request_id="req-1", data_id="123456"
    )
    response = await client.post(
        "/api/v1/webhooks/payments/mercadopago",
        headers={"x-signature": signature, "x-request-id": "req-1"},
        json={"type": "payment", "data": {"id": "123456"}},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}


async def test_mp_payment_updates_only_the_paying_tenant(
    db_session: AsyncSession,
    tenant: Tenant,
    tenant2: Tenant,
    monkeypatch: pytest.MonkeyPatch,
):
    """El pago aprobado activa premium SOLO en el tenant que pagó."""
    tenant2.wa_id = "573005551111"
    await db_session.commit()

    async def fake_fetch(*, payment_id: str, access_token: str) -> dict:
        return {
            "status": "approved",
            "external_reference": str(tenant2.id),
            "transaction_amount": 29000,
            "currency_id": "COP",
            "metadata": {"plan": "premium"},
        }

    monkeypatch.setattr("app.services.mercadopago.fetch_payment", fake_fetch)

    from app.services.mercadopago import process_payment_notification

    updated = await process_payment_notification(
        db_session, payment_id="mp-999", access_token="TEST-AT"
    )
    assert updated is not None
    assert updated.id == tenant2.id
    assert updated.plan == "premium"

    # El otro tenant no se movió
    await db_session.refresh(tenant)
    assert tenant.plan == "trial"

    # Historial con proveedor mercadopago
    sub = (
        await db_session.execute(
            select(Subscription).where(Subscription.tenant_id == tenant2.id)
        )
    ).scalar_one()
    assert sub.provider == "mercadopago"
    assert sub.provider_ref == "mp:mp-999"


async def test_mp_payment_not_approved_changes_nothing(
    db_session: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
):
    async def fake_fetch(*, payment_id: str, access_token: str) -> dict:
        return {
            "status": "pending",
            "external_reference": str(tenant.id),
            "transaction_amount": 29000,
            "currency_id": "COP",
            "metadata": {"plan": "premium"},
        }

    monkeypatch.setattr("app.services.mercadopago.fetch_payment", fake_fetch)

    from app.services.mercadopago import process_payment_notification

    updated = await process_payment_notification(
        db_session, payment_id="mp-998", access_token="TEST-AT"
    )
    assert updated is None
    await db_session.refresh(tenant)
    assert tenant.plan == "trial"


# ── Pagos: idempotencia, montos, renovación y vencimiento (auditoría A2) ────


def _mp_payment(tenant_id, **overrides) -> dict:
    payment = {
        "status": "approved",
        "external_reference": str(tenant_id),
        "transaction_amount": 29000,
        "currency_id": "COP",
        "metadata": {"plan": "premium"},
    }
    payment.update(overrides)
    return payment


async def test_mp_duplicate_payment_is_idempotent(
    db_session: AsyncSession, tenant2: Tenant, monkeypatch: pytest.MonkeyPatch
):
    """MercadoPago reenvía notificaciones: el mismo pago no se procesa dos veces."""
    payments = {"mp-dup": _mp_payment(tenant2.id)}

    async def fake_fetch(*, payment_id: str, access_token: str) -> dict:
        return payments[payment_id]

    monkeypatch.setattr("app.services.mercadopago.fetch_payment", fake_fetch)
    from app.services.mercadopago import process_payment_notification

    first = await process_payment_notification(
        db_session, payment_id="mp-dup", access_token="AT"
    )
    assert first is not None
    assert first.plan == "premium"

    # Reenvío de la misma notificación
    second = await process_payment_notification(
        db_session, payment_id="mp-dup", access_token="AT"
    )
    assert second is not None
    assert second.id == tenant2.id

    # Una sola fila para ese pago — sin duplicar filas ni extender periodo
    rows = (
        await db_session.execute(
            select(Subscription).where(Subscription.provider == "mercadopago")
        )
    ).scalars().all()
    assert len(rows) == 1


async def test_mp_renewal_extends_from_period_end(
    db_session: AsyncSession, tenant2: Tenant, monkeypatch: pytest.MonkeyPatch
):
    """Pagar con periodo vigente extiende DESDE el fin actual, no desde hoy."""
    payments = {
        "mp-r1": _mp_payment(tenant2.id),
        "mp-r2": _mp_payment(tenant2.id),
    }

    async def fake_fetch(*, payment_id: str, access_token: str) -> dict:
        return payments[payment_id]

    monkeypatch.setattr("app.services.mercadopago.fetch_payment", fake_fetch)
    from app.services.mercadopago import process_payment_notification

    await process_payment_notification(
        db_session, payment_id="mp-r1", access_token="AT"
    )
    first_end = (
        await db_session.execute(
            select(Subscription)
            .where(Subscription.tenant_id == tenant2.id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one().current_period_end
    assert first_end is not None

    await process_payment_notification(
        db_session, payment_id="mp-r2", access_token="AT"
    )
    second_end = (
        await db_session.execute(
            select(Subscription)
            .where(Subscription.tenant_id == tenant2.id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one().current_period_end

    # El nuevo periodo nace del fin del anterior (+30 días), no de hoy
    assert (second_end - first_end).days >= 29


async def test_mp_wrong_amount_changes_nothing(
    db_session: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
):
    """Nadie compra premium con $1.000 manipulando una preferencia."""
    async def fake_fetch(*, payment_id: str, access_token: str) -> dict:
        return _mp_payment(tenant.id, transaction_amount=1000)

    monkeypatch.setattr("app.services.mercadopago.fetch_payment", fake_fetch)
    from app.services.mercadopago import process_payment_notification

    result = await process_payment_notification(
        db_session, payment_id="mp-cheap", access_token="AT"
    )
    assert result is None
    await db_session.refresh(tenant)
    assert tenant.plan == "trial"
    rows = (
        await db_session.execute(
            select(Subscription).where(Subscription.tenant_id == tenant.id)
        )
    ).scalars().all()
    assert rows == []


async def test_mp_wrong_currency_rejected(
    db_session: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
):
    async def fake_fetch(*, payment_id: str, access_token: str) -> dict:
        return _mp_payment(tenant.id, currency_id="USD")

    monkeypatch.setattr("app.services.mercadopago.fetch_payment", fake_fetch)
    from app.services.mercadopago import process_payment_notification

    result = await process_payment_notification(
        db_session, payment_id="mp-usd", access_token="AT"
    )
    assert result is None
    await db_session.refresh(tenant)
    assert tenant.plan == "trial"


def test_mp_signature_freshness():
    """Una firma vieja reenviada no vale: ventana temporal de 5 minutos."""
    from app.services.mercadopago import PaymentSignatureError, verify_signature

    def _sign(data_id: str, ts: str) -> str:
        manifest = f"id:{data_id};request-id:req-1;ts:{ts};"
        digest = hmac.new(
            b"test-secret", manifest.encode(), hashlib.sha256
        ).hexdigest()
        return f"ts={ts},v1={digest}"

    # Fresca: pasa
    fresh_ts = str(int(time.time()))
    verify_signature(
        secret="test-secret",
        x_signature=_sign("123456", fresh_ts),
        x_request_id="req-1",
        data_id="123456",
    )

    # De hace una hora: rechazada
    old_ts = str(int(time.time()) - 3600)
    with pytest.raises(PaymentSignatureError):
        verify_signature(
            secret="test-secret",
            x_signature=_sign("123456", old_ts),
            x_request_id="req-1",
            data_id="123456",
        )


async def test_expiry_job_downgrades_to_trial_without_method(
    db_session: AsyncSession, tenant: Tenant
):
    """Venció y sin método de pago → trial; la fila queda 'past_due'."""
    await apply_plan(db_session, tenant_id=tenant.id, plan="premium")

    sub = (
        await db_session.execute(
            select(Subscription)
            .where(Subscription.tenant_id == tenant.id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one()
    sub.current_period_end = datetime.now(UTC) - timedelta(hours=1)
    await db_session.commit()

    from app.services.entitlements import expire_subscriptions

    expired = await expire_subscriptions(db_session)
    assert expired == 1
    await db_session.refresh(tenant)
    assert tenant.plan == "trial"

    statuses = [
        s.status
        for s in (
            await db_session.execute(
                select(Subscription).where(Subscription.tenant_id == tenant.id)
            )
        ).scalars()
    ]
    assert "past_due" in statuses


async def test_expiry_job_downgrades_to_freemium_with_method(
    db_session: AsyncSession, tenant: Tenant
):
    """Venció con método de pago en archivo → freemium."""
    db_session.add(
        PaymentMethod(
            tenant_id=tenant.id,
            provider="manual",
            provider_token="tok",
            brand="Visa",
            last4="4242",
        )
    )
    await db_session.commit()
    await apply_plan(db_session, tenant_id=tenant.id, plan="premium")

    sub = (
        await db_session.execute(
            select(Subscription)
            .where(Subscription.tenant_id == tenant.id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one()
    sub.current_period_end = datetime.now(UTC) - timedelta(hours=1)
    await db_session.commit()

    from app.services.entitlements import expire_subscriptions

    expired = await expire_subscriptions(db_session)
    assert expired == 1
    await db_session.refresh(tenant)
    assert tenant.plan == "freemium"


async def test_expiry_job_ignores_active_period(
    db_session: AsyncSession, tenant: Tenant
):
    """Periodo vigente → nadie toca al tenant."""
    await apply_plan(db_session, tenant_id=tenant.id, plan="premium")

    from app.services.entitlements import expire_subscriptions

    expired = await expire_subscriptions(db_session)
    assert expired == 0
    await db_session.refresh(tenant)
    assert tenant.plan == "premium"


# ── Link de pago (Checkout Pro) ────────────────────────────────────────────


class FakeChannel:
    """Canal que registra envíos en vez de llamar a Evolution."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, to: str, text: str) -> None:
        self.sent.append((to, text))


def _mp_admin_settings(monkeypatch: pytest.MonkeyPatch, token: str = "TEST-AT"):
    from types import SimpleNamespace

    stub = SimpleNamespace(
        mercadopago_access_token=token,
        mercadopago_notification_url="",
    )
    monkeypatch.setattr("app.api.v1.admin.get_settings", lambda: stub)


async def test_checkout_link_requires_access_token(
    client: AsyncClient, platform_admin: User, tenant: Tenant
):
    """Sin MERCADOPAGO_ACCESS_TOKEN → 503 (fase manual: plan desde el panel)."""
    response = await client.post(
        f"/api/v1/admin/tenants/{tenant.id}/checkout-link",
        headers=_headers(platform_admin),
    )
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE


async def test_checkout_link_created(
    client: AsyncClient,
    platform_admin: User,
    tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
):
    """Genera la preferencia y devuelve el init_point del link de pago."""
    _mp_admin_settings(monkeypatch)

    async def fake_create_link(
        *, tenant, plan, access_token, notification_url=None
    ):
        assert plan == "premium"
        assert access_token == "TEST-AT"
        assert tenant.id is not None
        return {"id": "pref-123", "init_point": "https://mp.test/pay"}

    monkeypatch.setattr(
        "app.api.v1.admin.create_checkout_link", fake_create_link
    )

    response = await client.post(
        f"/api/v1/admin/tenants/{tenant.id}/checkout-link",
        headers=_headers(platform_admin),
    )
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["init_point"] == "https://mp.test/pay"
    assert data["preference_id"] == "pref-123"
    assert data["price_cop"] == 29_000
    assert data["whatsapp_sent"] is False


async def test_checkout_link_sent_by_whatsapp(
    client: AsyncClient,
    platform_admin: User,
    tenant: Tenant,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """El link llega al chat del técnico registrado — el flujo completo."""
    tenant.wa_id = "573005551111"
    await db_session.commit()
    _mp_admin_settings(monkeypatch)

    async def fake_create_link(**kwargs):
        return {"id": "pref-123", "init_point": "https://mp.test/pay"}

    monkeypatch.setattr(
        "app.api.v1.admin.create_checkout_link", fake_create_link
    )

    fake_channel = FakeChannel()
    monkeypatch.setattr(
        "app.api.v1.admin.get_channel", lambda name="evolution": fake_channel
    )

    response = await client.post(
        f"/api/v1/admin/tenants/{tenant.id}/checkout-link",
        headers=_headers(platform_admin),
        json={"send_to_whatsapp": True},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()["whatsapp_sent"] is True

    to, text = fake_channel.sent[0]
    assert to == "573005551111"
    assert "https://mp.test/pay" in text


async def test_checkout_link_whatsapp_requires_registered_number(
    client: AsyncClient,
    platform_admin: User,
    tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
):
    """WhatsApp sin número registrado → 422 antes de crear la preferencia."""
    _mp_admin_settings(monkeypatch)

    response = await client.post(
        f"/api/v1/admin/tenants/{tenant.id}/checkout-link",
        headers=_headers(platform_admin),
        json={"send_to_whatsapp": True},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
