from types import SimpleNamespace

import pytest

from app.models import User
from app.services import onboarding, orchestrator


@pytest.mark.parametrize(
    "text",
    [
        "dame el enlace del admin",
        "quiero entrar a mi panel",
        "pásame el link de la plataforma",
        "como entro al administrador",
    ],
)
def test_panel_access_phrases_are_detected(text: str):
    assert orchestrator._requests_panel_access(text)


@pytest.mark.parametrize(
    "text",
    ["conectar google", "quiero vincular mi Gmail", "autoriza mi calendario de Google"],
)
def test_google_connection_phrases_are_detected(text: str):
    assert orchestrator._requests_google_connection(text)


@pytest.mark.asyncio
async def test_existing_owner_gets_personalized_login_link(
    db_session, tenant, monkeypatch: pytest.MonkeyPatch
):
    tenant.bot_name = "Nora"
    db_session.add(
        User(
            tenant_id=tenant.id,
            email="dueno@example.com",
            password_hash="stored-hash",
            full_name="Dueño",
            role="admin",
        )
    )
    await db_session.commit()
    monkeypatch.setattr(
        onboarding,
        "get_settings",
        lambda: SimpleNamespace(panel_base_url="https://panel.example.com"),
    )

    message = await onboarding.panel_access_message(db_session, tenant=tenant)

    assert "Nora" in message
    assert "https://panel.example.com/login?tenant=personal&bot=Nora" in message
    assert "dueno@example.com" in message
    assert "stored-hash" not in message


@pytest.mark.asyncio
async def test_owner_without_user_gets_password_setup_link(
    db_session, tenant, monkeypatch: pytest.MonkeyPatch
):
    tenant.bot_name = "Mi Asistente"
    monkeypatch.setattr(
        onboarding,
        "get_settings",
        lambda: SimpleNamespace(panel_base_url="https://panel.example.com"),
    )
    monkeypatch.setattr(onboarding, "_generate_panel_token", lambda _tenant_id: "short-token")

    message = await onboarding.panel_access_message(db_session, tenant=tenant)

    assert "https://panel.example.com/crear-contrasena?token=short-token" in message
    assert "bot=Mi%20Asistente" in message
    assert "30 minutos" in message
