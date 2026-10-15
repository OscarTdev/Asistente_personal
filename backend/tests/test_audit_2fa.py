"""Tests de auditoría y 2FA del superadmin (adendo §4.3–§4.6)."""

import uuid
from http import HTTPStatus

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models import Tenant, User


@pytest.fixture
async def super_admin(db_session: AsyncSession, tenant: Tenant) -> User:
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="2fa@example.com",
        password_hash=hash_password("Secreta123!"),
        role="admin",
        is_active=True,
        is_platform_admin=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def super_headers(super_admin: User) -> dict[str, str]:
    token = create_access_token(
        user_id=super_admin.id,
        tenant_id=super_admin.tenant_id,
        role=super_admin.role,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_conversations_require_reason(
    client, super_headers, tenant, db_session
):
    """Leer conversaciones sin motivo → 422. Con motivo → 200 y audit_log."""
    resp = await client.get(
        f"/api/v1/admin/tenants/{tenant.id}/conversations",
        headers=super_headers,
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    resp = await client.get(
        f"/api/v1/admin/tenants/{tenant.id}/conversations",
        headers=super_headers,
        params={"motivo": "El cliente reportó un problema con su cotización"},
    )
    assert resp.status_code == HTTPStatus.OK

    # La entrada quedó en auditoría
    from sqlalchemy import select

    from app.models import AuditLog

    entries = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "read_conversations")
        )
    ).scalars().all()
    assert len(entries) >= 1
    assert "problema con su cotización" in entries[-1].reason
    assert str(entries[-1].tenant_id) == str(tenant.id)


@pytest.mark.asyncio
async def test_change_plan_is_audited(client, super_headers, tenant, db_session):
    """Cambiar el plan deja registro en audit_log (adendo §4.6)."""
    resp = await client.patch(
        f"/api/v1/admin/tenants/{tenant.id}/plan",
        json={"plan": "premium"},
        headers=super_headers,
    )
    assert resp.status_code == HTTPStatus.OK

    from sqlalchemy import select

    from app.models import AuditLog

    entry = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == "change_plan")
            .order_by(AuditLog.created_at.desc())
        )
    ).scalars().first()
    assert entry is not None
    assert "plan:premium" in entry.object_ref


@pytest.mark.asyncio
async def test_audit_log_endpoint(client, super_headers):
    """El superadmin consulta su bitácora; un dueño no (403)."""
    resp = await client.get("/api/v1/admin/audit-log", headers=super_headers)
    assert resp.status_code == HTTPStatus.OK
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_totp_2fa_full_flow(
    client, super_headers, super_admin, tenant, db_session
):
    """Setup → confirmar → el login exige código → código inválido 401."""
    import pyotp

    # 1) Setup: devuelve secreto y URI
    resp = await client.post("/api/v1/admin/me/2fa/setup", headers=super_headers)
    assert resp.status_code == HTTPStatus.OK
    secret = resp.json()["secret"]
    assert resp.json()["uri"].startswith("otpauth://totp/")

    # 2) Confirmar con el código correcto
    code = pyotp.TOTP(secret).now()
    resp = await client.post(
        "/api/v1/admin/me/2fa/confirm",
        json={"code": code},
        headers=super_headers,
    )
    assert resp.status_code == HTTPStatus.OK

    # 3) Login SIN código → 401 aunque la contraseña sea correcta
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": super_admin.email, "password": "Secreta123!"},
    )
    assert resp.status_code == HTTPStatus.UNAUTHORIZED
    assert "Código de verificación" in resp.json()["detail"]

    # 4) Login CON código correcto → 200
    code = pyotp.TOTP(secret).now()
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": super_admin.email,
            "password": "Secreta123!",
            "totp_code": code,
        },
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["user"]["is_platform_admin"] is True

    # 5) Un dueño SIN 2FA sigue entrando normal (sin totp_code)
    owner = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="owner@example.com",
        password_hash=hash_password("Owner1234!"),
        role="admin",
        is_active=True,
        is_platform_admin=False,
    )
    db_session.add(owner)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "Owner1234!"},
    )
    assert resp.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_2fa_requires_platform_admin(client, db_session, tenant):
    """Un dueño no puede activar el 2FA (es del superadmin)."""
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="plain@example.com",
        password_hash=hash_password("Plain123!"),
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    headers = {
        "Authorization": f"Bearer {create_access_token(user.id, user.tenant_id, user.role)}"
    }
    resp = await client.post("/api/v1/admin/me/2fa/setup", headers=headers)
    assert resp.status_code == HTTPStatus.FORBIDDEN
