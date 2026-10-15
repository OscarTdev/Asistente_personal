"""Tests del branding: logo del negocio en los PDFs.

El logo se sube por el panel (multipart), se normaliza con Pillow
(PNG, ancho máx 800px) y se guarda en la BD. El dueño del tenant lo
gestiona; sin logo, los PDFs usan el encabezado solo con texto.
"""

import io
from http import HTTPStatus

import pytest
from httpx import AsyncClient
from PIL import Image


def _png_bytes(width: int = 200, height: int = 80) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (width, height), (15, 23, 42, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 80), (15, 23, 42)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def auth_headers(admin_user) -> dict[str, str]:
    from app.core.security import create_access_token

    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_branding_without_logo(client: AsyncClient, auth_headers):
    """Sin logo configurado: has_logo False y sin data URL."""
    resp = await client.get("/api/v1/branding", headers=auth_headers)
    assert resp.status_code == HTTPStatus.OK
    body = resp.json()
    assert body["has_logo"] is False
    assert body["logo_data_url"] is None


@pytest.mark.asyncio
async def test_upload_png_logo(client: AsyncClient, auth_headers):
    """PNG válido se guarda normalizado y el branding lo expone como data URL."""
    resp = await client.put(
        "/api/v1/branding/logo",
        files={"file": ("logo.png", _png_bytes(), "image/png")},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["has_logo"] is True

    listing = await client.get("/api/v1/branding", headers=auth_headers)
    body = listing.json()
    assert body["has_logo"] is True
    assert body["logo_data_url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_upload_jpeg_is_normalized_to_png(client: AsyncClient, auth_headers):
    """JPEG aceptado: se re-encodifica a PNG (mime uniforme)."""
    resp = await client.put(
        "/api/v1/branding/logo",
        files={"file": ("logo.jpg", _jpeg_bytes(), "image/jpeg")},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["logo_mimetype"] == "image/png"


@pytest.mark.asyncio
async def test_upload_rejects_non_image(client: AsyncClient, auth_headers):
    """Un .txt con content-type texto no pasa."""
    resp = await client.put(
        "/api/v1/branding/logo",
        files={"file": ("logo.txt", b"esto no es imagen", "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE


@pytest.mark.asyncio
async def test_upload_rejects_oversize(client: AsyncClient, auth_headers):
    """Más de 2 MB → 413 antes de intentar normalizar."""
    big = _png_bytes() + b"\x00" * (3 * 1024 * 1024)
    resp = await client.put(
        "/api/v1/branding/logo",
        files={"file": ("logo.png", big, "image/png")},
        headers=auth_headers,
    )
    assert resp.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


@pytest.mark.asyncio
async def test_delete_logo(client: AsyncClient, auth_headers):
    """Quitar el logo vuelve al estado sin logo."""
    await client.put(
        "/api/v1/branding/logo",
        files={"file": ("logo.png", _png_bytes(), "image/png")},
        headers=auth_headers,
    )
    resp = await client.delete("/api/v1/branding/logo", headers=auth_headers)
    assert resp.status_code == HTTPStatus.NO_CONTENT

    listing = await client.get("/api/v1/branding", headers=auth_headers)
    assert listing.json()["has_logo"] is False


@pytest.mark.asyncio
async def test_branding_requires_auth(client: AsyncClient):
    """Sin token, el branding no es accesible."""
    resp = await client.get("/api/v1/branding")
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_branding_isolated_by_tenant(
    client: AsyncClient, auth_headers: dict[str, str], db_session, tenant
):
    """El logo de un tenant no se ve desde otro (upsert propio)."""
    import uuid

    from app.core.security import create_access_token
    from app.models import Tenant, User

    other_tenant = Tenant(
        id=uuid.uuid4(),
        name="Otro",
        slug="otro-branding",
        bot_name="Aura",
        is_active=True,
    )
    db_session.add(other_tenant)
    await db_session.flush()
    other_admin = User(
        tenant_id=other_tenant.id,
        email="otro@example.com",
        password_hash="x",
        role="admin",
        is_active=True,
    )
    db_session.add(other_admin)
    await db_session.commit()

    other_token = create_access_token(
        user_id=other_admin.id,
        tenant_id=other_admin.tenant_id,
        role=other_admin.role,
    )

    # El primer tenant sube logo
    await client.put(
        "/api/v1/branding/logo",
        files={"file": ("logo.png", _png_bytes(), "image/png")},
        headers=auth_headers,
    )

    # El otro tenant sigue sin logo
    resp = await client.get(
        "/api/v1/branding", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["has_logo"] is False
