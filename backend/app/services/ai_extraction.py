"""Servicio de extracción de ítems con IA (OpenRouter / NVIDIA NIM).

El LLM extrae descripciones y cantidades del texto libre del técnico.
NUNCA inventa precios: los precios salen siempre del catálogo.

Flujo:
1. Llamar al LLM con un system prompt estructurado → lista JSON de {descripcion, cantidad}.
2. Para cada ítem extraído, buscar en el catálogo del tenant (ILIKE por nombre).
3. Registrar el consumo de tokens en llm_usage.
4. Devolver sugerencias con precio del catálogo si hay match.
"""

import json
import logging
from decimal import Decimal
from uuid import UUID

from openai import APIError as OpenAIAPIError
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import CatalogItem, LlmUsage
from app.schemas.quotes import ExtractedItemSuggestion, ExtractResponse

logger = logging.getLogger(__name__)


def _escape_like(text: str) -> str:
    """Escapa los comodines de ILIKE.

    Un '%' o '_' en el texto de la IA (o del cliente) no puede casar con
    todo el catálogo y robar el precio de otro ítem.
    """
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def _match_catalog_item(
    db: AsyncSession, *, tenant_id: UUID, description: str
) -> CatalogItem | None:
    """Busca el ítem del catálogo por nombre parecido (ILIKE escapado).

    Sprint 0: escape de comodines y orden determinista. Sprint 1: pg_trgm
    con umbral de similitud para tolerar variantes ("30 A" vs "30A").
    """
    pattern = f"%{_escape_like(description[:50])}%"
    result = await db.execute(
        select(CatalogItem)
        .where(CatalogItem.tenant_id == tenant_id)
        .where(CatalogItem.is_active.is_(True))
        .where(CatalogItem.name.ilike(pattern))
        .order_by(CatalogItem.name)
        .limit(1)
    )
    return result.scalar_one_or_none()

_SYSTEM_PROMPT = """Eres un asistente técnico especializado en extracción de información.
Tu única tarea es leer el texto de un técnico y extraer los materiales
o servicios mencionados.

REGLAS:
- Devuelve SOLO un JSON array, sin texto adicional.
- Cada elemento tiene: "descripcion" (string) y "cantidad" (número positivo).
- Si no hay cantidad explícita, usa 1.
- No inventes precios, marcas ni especificaciones no mencionadas.
- Normaliza descripciones a español técnico conciso.

Ejemplo de salida:
[
  {"descripcion": "Breaker bipolar 30A", "cantidad": 2},
  {"descripcion": "Cable THHN calibre 12", "cantidad": 15}
]"""


async def extract_items_from_text(
    db: AsyncSession,
    tenant_id: UUID,
    text: str,
) -> ExtractResponse:
    """Extrae ítems del texto libre y los intenta matchear contra el catálogo."""
    settings = get_settings()

    if not settings.llm_api_key:
        logger.warning("LLM_API_KEY no configurada; devolviendo extracción vacía")
        return ExtractResponse(suggestions=[], raw_extraction=[])

    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )

    # Llamada al LLM
    raw_items: list[dict] = []
    prompt_tokens = 0
    completion_tokens = 0
    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        content = response.choices[0].message.content or "[]"
        prompt_tokens = response.usage.prompt_tokens if response.usage else 0
        completion_tokens = response.usage.completion_tokens if response.usage else 0

        # Limpiar posibles fences de markdown (```json ... ```)
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        raw_items = json.loads(content)
        if not isinstance(raw_items, list):
            raw_items = []
    except OpenAIAPIError as exc:
        logger.error("Error llamando al LLM: %s", exc)
        return ExtractResponse(suggestions=[], raw_extraction=[])
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("LLM devolvió JSON inválido: %s", exc)
        raw_items = []
    finally:
        # Registrar consumo incluso si hubo error parcial
        if prompt_tokens or completion_tokens:
            db.add(LlmUsage(
                tenant_id=tenant_id,
                model=settings.llm_model,
                purpose="quote_item_extraction",
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
            ))
            await db.commit()

    # Matching contra catálogo
    suggestions: list[ExtractedItemSuggestion] = []
    for raw in raw_items:
        desc = str(raw.get("descripcion") or raw.get("description") or "").strip()
        if not desc:
            continue
        try:
            qty = Decimal(str(raw.get("cantidad") or raw.get("quantity") or 1))
        except Exception:
            qty = Decimal("1")

        # Buscar en catálogo por similitud de nombre (ILIKE escapado)
        catalog_match = await _match_catalog_item(
            db, tenant_id=tenant_id, description=desc
        )

        suggestions.append(ExtractedItemSuggestion(
            description=desc,
            quantity=qty,
            catalog_item_id=catalog_match.id if catalog_match else None,
            catalog_name=catalog_match.name if catalog_match else None,
            unit_price=catalog_match.unit_price if catalog_match else None,
            unit=catalog_match.unit if catalog_match else None,
            matched=catalog_match is not None,
        ))

    return ExtractResponse(suggestions=suggestions, raw_extraction=raw_items)
