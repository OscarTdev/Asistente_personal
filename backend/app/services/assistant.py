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
- "invoice": el dueño pide generar una CUENTA DE COBRO (para cobrar un trabajo ya hecho).
  Ejemplos: "cuenta de cobro para Juliana por 500 mil", "generame una cuenta de cobro por la instalación".
- "note": el dueño quiere guardar, ver, buscar o borrar UNA NOTA.
  Ejemplos: "guarda una nota: comprar 20 metros de cable", "qué notas tengo", "busca la nota del cable", "borra la nota del cable".
- "reminder": el dueño pide que le RECUERDES algo en una fecha.
  Ejemplos: "recuérdame llamar a Juliana el jueves", "recuérdame comprar cable mañana a las 3", "no olvides revisar el tablero el viernes".
  Para "reminder", extrae la fecha/hora como ISO 8601 en "remind_at" y pon el qué recordar en "message_text".
- "confirm": el dueño responde a una pregunta del asistente (SÍ/NO, enviar/no enviar).
  Ejemplos: "sí envíala", "dale", "ok", "claro", "no", "después", "envíala".
- "collection": el dueño quiere COBRARLE a uno de sus clientes un monto por un trabajo ya hecho.
  Ejemplos: "cobrale a Juliana 450 mil por la instalación", "genera un cobro para Pedro por 800 mil del tablero".
  Para "collection", extrae el monto como número en "amount", el contacto en "contact_name" y el concepto en "description".
- "visit_report": el dueño pide generar un INFORME DE VISITA TECNICA (hallazgos y recomendaciones).
  Ejemplos: "informe de visita para Juliana: revisé el tablero, cambié 2 breakers", "genera un informe de la visita técnica a la obra de Pedro".
  Extrae el contacto en "contact_name", los hallazgos en "description" y el monto si lo menciona en "amount".
- "maintenance": el dueño registra o consulta un MANTENIMIENTO PREVENTIVO (avisos periódicos a un cliente).
  Ejemplos: "programa mantenimiento de aire acondicionado para Juliana cada 6 meses", "qué mantenimientos tengo", "agenda revisión del tablero para Pedro en 3 meses".
  Para programar: "contact_name" (cliente), "message_text" (qué mantener), "remind_at" (fecha ISO del próximo).
  Para consultar: sin campos adicionales.
- "warranty": el dueño REGISTRA o CONSULTA una GARANTÍA (qué instaló y hasta cuándo cubre).
  Ejemplos: "registra garantía para Juliana: breaker 30A, 1 año", "qué garantías tengo", "garantías vigentes de Pedro".
  Para registrar: "contact_name" (cliente), "description" (qué se instaló), "amount" NO aplica, usa "remind_at" como fecha de vencimiento ISO.
  Para consultar: sin campos adicionales.
- "expense": el dueño registra un GASTO o consulta cuánto ha gastado.
  Para registrar: "gasté 45 mil en cable", "compré gasolina por 30 mil", "almuerzo 15 mil".
  Extrae el monto en "amount", la descripción en "description".
  Para consultar: "cuánto he gastado este mes", "resumen de gastos", "mis gastos" → sin campos.
- "inventory": el dueño registra, consulta o descuenta MATERIALES de su inventario.
  Para agregar: "tengo 20 metros de cable", "compré 5 breakers 30A" → "amount" = cantidad, "description" = material.
  Para consultar: "qué inventario tengo", "mis materiales" → sin campos.
  Para descontar: "usé 15 metros de cable", "gasté 2 breakers" → "amount" = cantidad usada, "description" = material.
- "chat": todo lo demás: preguntas, charla, pedidos que aún no existen como acción.

Responde SOLO un JSON válido, sin texto adicional:
{{"intention": "send_message", "contact_name": "Juliana", "message_text": "¡Buenos días, Juliana! 🌞 Que tengas un excelente día."}}
{{"intention": "quote", "contact_name": "Juliana"}}
{{"intention": "invoice", "contact_name": "Juliana", "amount": 500000, "description": "Instalación de 5 tomacorrientes"}}
{{"intention": "confirm", "message_text": "sí"}}
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
