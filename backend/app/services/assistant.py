"""Router de intenciones del asistente del dueño.

El dueño le habla al asistente (auto-chat o su número registrado) y esta
piez decide QUÉ quiere que haga: enviarle un mensaje a un contacto, armar
una cotización o conversar. Un LLM clasifica con JSON estructurado; ante
cualquier falla la intención por defecto es conversar (nunca revienta).
"""

import json
import logging

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.models import Tenant
from app.schemas.assistant import AssistantIntent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Eres el enrutador de intenciones de {bot_name}, el asistente de WhatsApp de {tenant_name}. El dueño del negocio te escribe y tú decides qué hacer con el mensaje.

INTENCIONES:
- "send_message": el dueño quiere que le escribas a UNO DE SUS CONTACTOS.
  Ejemplos: "mandale un mensaje de buenos dias a juliana", "escribile a Pedro deseandole feliz cumpleaños", "dale un saludo a doña Mary".
- "quote": el dueño pide armar una cotización de materiales o servicios (solo cotizar, no escribir a nadie).
  Ejemplos: "cotizame 3 tomacorrientes y 20 metros de cable", "cotización para Juliana: dos breakers de 30A".
- "chat": todo lo demás: preguntas, charla, pedidos que aún no existen como acción.

Responde SOLO un JSON válido, sin texto adicional:
{{"intention": "send_message", "contact_name": "Juliana", "message_text": "¡Buenos días, Juliana! 🌞 Que tengas un excelente día."}}
{{"intention": "quote", "contact_name": "Juliana"}}
{{"intention": "chat"}}

REGLAS:
- "contact_name": el nombre tal como lo menciona el dueño (null si no aplica).
- "message_text": el mensaje listo para enviar, cálido, corto y en español (solo para send_message). Si el dueño dio texto literal entre comillas, úsalo tal cual.
- Si la orden pide cotizar y menciona un cliente ("cotizale a Juliana..."), usa "quote" con el contact_name del cliente.
- Ante la duda, "chat"."""


def _parse_intent(raw: str) -> AssistantIntent:
    """Extrae el JSON de la respuesta del LLM (tolera fences y texto extra)."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("La respuesta del router no contiene JSON")
    payload = json.loads(raw[start : end + 1])
    return AssistantIntent.model_validate(payload)


async def detect_intent(*, tenant: Tenant, text: str) -> AssistantIntent:
    """Clasifica el mensaje del dueño en una intención accionable."""
    settings = get_settings()
    if not settings.llm_api_key:
        return AssistantIntent(intention="chat")

    try:
        client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=15,
        )
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": _SYSTEM_PROMPT.format(
                        bot_name=tenant.bot_name, tenant_name=tenant.name
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=300,
        )
        raw = (response.choices[0].message.content or "").strip()
        return _parse_intent(raw)
    except Exception:
        logger.exception("El router de intenciones falló; se asume 'chat'")
        return AssistantIntent(intention="chat")
