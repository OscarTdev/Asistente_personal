import uuid
from http import HTTPStatus

import pytest
from httpx import AsyncClient

from app.core.security import decode_access_token
from app.models import Tenant, User


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, admin_user: User, tenant: Tenant):
    """Login correcto → 200 con token y datos del usuario (bot_name "Aura")."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "Admin1234!"},
    )
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["token_type"] == "bearer"
    assert "access_token" in data
    claims = decode_access_token(data["access_token"])
    assert claims["sub"] == str(admin_user.id)
    assert claims["tenant_id"] == str(tenant.id)
    assert claims["role"] == "admin"
    user_data = data["user"]
    assert user_data["id"] == str(admin_user.id)
    assert user_data["email"] == admin_user.email
    assert user_data["full_name"] is None
    assert user_data["role"] == admin_user.role
    assert user_data["tenant_id"] == str(admin_user.tenant_id)
    assert user_data["bot_name"] == tenant.bot_name == "Aura"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, admin_user: User):
    """Password incorrecta → 401."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "WrongPassword"},
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json()["detail"] == "Credenciales inválidas"


@pytest.mark.asyncio
async def test_login_nonexistent_email(client: AsyncClient):
    """Email inexistente → 401 con el MISMO mensaje (sin revelar cuál falló)."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "anything"},
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json()["detail"] == "Credenciales inválidas"


@pytest.mark.asyncio
async def test_login_email_in_multiple_tenants(client: AsyncClient, db_session, admin_user):
    """Email en varios tenants → 400."""
    from app.core.security import hash_password
    from app.models import Tenant as TenantModel
    from app.models import User as UserModel

    tenant2 = TenantModel(
        id=uuid.uuid4(),
        name="Other",
        slug="other",
        bot_name="OtherBot",
        is_active=True,
    )
    user2 = UserModel(
        id=uuid.uuid4(),
        tenant_id=tenant2.id,
        email=admin_user.email,  # mismo email que admin_user
        password_hash=hash_password("Admin1234!"),
        full_name=None,
        role="admin",
        is_active=True,
    )
    db_session.add_all([tenant2, user2])
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "Admin1234!"},
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"] == "El correo pertenece a varios tenants"
