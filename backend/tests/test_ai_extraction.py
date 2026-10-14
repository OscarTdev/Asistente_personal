import json
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models import CatalogItem, LlmUsage, User


@pytest.fixture
def auth_headers(admin_user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=admin_user.id,
        tenant_id=admin_user.tenant_id,
        role=admin_user.role,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_extract_items_empty_when_no_api_key(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Sin API key configurada devuelve lista vacía sin error 500."""
    with patch("app.services.ai_extraction.get_settings") as mock_settings:
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_base_url = "https://openrouter.ai/api/v1"
        mock_settings.return_value.llm_model = "meta-llama/llama-3.1-70b-instruct"

        resp = await client.post(
            "/api/v1/quotes/extract",
            json={"text": "Necesito 2 breakers de 30 amperios"},
            headers=auth_headers,
        )
        assert resp.status_code == HTTPStatus.OK
        data = resp.json()
        assert data["suggestions"] == []
        assert data["raw_extraction"] == []


@pytest.mark.asyncio
async def test_extract_items_with_mock_llm_and_catalog_match(
    client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user: User,
    db_session: AsyncSession,
):
    """Simula respuesta de OpenRouter/NVIDIA, matchea con catálogo
    y registra consumo en llm_usage."""
    # 1. Crear ítem en catálogo previo
    cat_item = CatalogItem(
        tenant_id=admin_user.tenant_id,
        name="Breaker 30A Schneider",
        description="Termomagnético 30 amperios",
        unit="und",
        unit_price=35000.00,
        is_active=True,
    )
    db_session.add(cat_item)
    await db_session.commit()
    await db_session.refresh(cat_item)

    # 2. Configurar mock de OpenAI AsyncOpenAI
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps([
        {"descripcion": "Breaker 30A", "cantidad": 2},
        {"descripcion": "Tubo conduit 1/2 pulgada", "cantidad": 5},
    ])
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 45
    mock_usage.completion_tokens = 30

    mock_completion_resp = MagicMock()
    mock_completion_resp.choices = [mock_choice]
    mock_completion_resp.usage = mock_usage

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_completion_resp)

    with patch("app.services.ai_extraction.get_settings") as mock_settings, \
         patch("app.services.ai_extraction.AsyncOpenAI", return_value=mock_client_instance):
        mock_settings.return_value.llm_api_key = "test-sk-key"
        mock_settings.return_value.llm_base_url = "https://openrouter.ai/api/v1"
        mock_settings.return_value.llm_model = "meta-llama/llama-3.1-70b-instruct"
        mock_settings.return_value.catalog_similarity_threshold = 0.30
        mock_settings.return_value.catalog_ambiguity_gap = 0.05

        resp = await client.post(
            "/api/v1/quotes/extract",
            json={"text": "Para el trabajo van 2 breakers 30A y 5 tubos conduit de media"},
            headers=auth_headers,
        )
        assert resp.status_code == HTTPStatus.OK
        data = resp.json()
        assert len(data["suggestions"]) == 2

        # Primer ítem: debe haber hecho match con "Breaker 30A Schneider"
        item1 = data["suggestions"][0]
        assert item1["description"] == "Breaker 30A"
        assert float(item1["quantity"]) == 2
        assert item1["matched"] is True
        assert item1["catalog_name"] == "Breaker 30A Schneider"
        assert float(item1["unit_price"]) == 35000.00

        # Segundo ítem: no está en catálogo
        item2 = data["suggestions"][1]
        assert item2["matched"] is False
        assert item2["catalog_item_id"] is None

        # Verificar registro en llm_usage
        usage_res = await db_session.execute(
            select(LlmUsage).where(LlmUsage.tenant_id == admin_user.tenant_id)
        )
        usages = usage_res.scalars().all()
        assert len(usages) >= 1
        assert usages[0].input_tokens == 45
        assert usages[0].output_tokens == 30
