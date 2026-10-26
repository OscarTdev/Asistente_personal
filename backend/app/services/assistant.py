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
  Para CREAR: "recuérdame llamar a Juliana el jueves", "recuérdame comprar cable mañana a las 3", "no olvides revisar el tablero el viernes".
  Extrae la fecha/hora como ISO 8601 en "remind_at" (hora Colombia) y pon el qué recordar en "message_text".
  Para CONSULTAR: "qué recordatorios tengo", "cuándo me recordarás", "mis recordatorios" → intención "reminder" SIN ningún campo extra (no inventes contenido ni fecha).
  Para CANCELAR: "cancela el recordatorio de la cita", "elimina ese recordatorio" → intención "reminder" con "message_text" = qué recordatorio (o "ese" si no lo dice).
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
- "expense": FINANZAS PERSONALES: el dueño registra un GASTO o un INGRESO, o CONSULTA su cartera.
  Para registrar un GASTO: "gasté 45 mil en cable", "compré gasolina por 30 mil" → "amount" = monto, "description" = en qué.
  Para registrar un INGRESO: "cobré 500 mil a Juliana", "me pagó 300 mil Pedro", "recibí 200 mil del trabajo" → "amount" = monto, "description" = concepto/cliente.
  Para CONSULTAR gastos: "cuánto he gastado este mes", "resumen de gastos", "mis gastos" → sin campos adicionales.
  Para CONSULTAR cartera/balance: "cuánto tengo", "mi cartera", "cuál es mi balance", "cuánto dinero tengo" → sin campos adicionales (message_text = la pregunta).
  IMPORTANTE: "cobré", "me pagó", "recibí" = INGRESO (intención "expense", NO es send_message ni chat).
- "inventory": el dueño registra, consulta o descuenta MATERIALES de su inventario.
  Para agregar: "tengo 20 metros de cable", "compré 5 breakers 30A" → "amount" = cantidad, "description" = material.
  Para consultar: "qué inventario tengo", "mis materiales" → sin campos.
  Para descontar: "usé 15 metros de cable", "gasté 2 breakers" → "amount" = cantidad usada, "description" = material.
- "site_log": el dueño gestiona una OBRA (bitácora de avance diario).
  Para abrir: "abre obra para Juliana: instalación de tomacorrientes" → "contact_name" = cliente, "description" = título.
  Para registrar avance: "registro: se instalaron 5 tomacorrientes" → "message_text" = nota del día.
  Para consultar: "qué obras tengo abiertas" → sin campos.
  Para cerrar: "cierra la obra de Juliana" → "contact_name" = cliente.
- "profitability": el dueño pregunta cuánto ganó en un trabajo.
  "rentabilidad del trabajo de Juliana", "cuánto gané con Pedro" → "contact_name" = cliente.
- "google_email": el dueño pide revisar SU correo de Gmail o escribirle un correo a alguien.
  Para resumir: "resumime el correo", "tengo correos nuevos", "qué hay en mi correo" → sin campos.
  Para escribir: "escríbele un correo a Juliana diciendo que llego a las 3" → "contact_name" = destinatario, "message_text" = cuerpo del correo.
- "google_calendar": el dueño consulta SU agenda de Google Calendar o agenda un evento.
  Para consultar: "qué tengo hoy", "qué tengo mañana", "mi agenda de la semana" → sin campos.
  Para agendar: "agenda visita de Juliana el jueves a las 3" → "message_text" = título del evento, "remind_at" = fecha/hora ISO del inicio, "contact_name" si aplica.
- "google_sheets": el dueño quiere pasar SUS datos a una hoja de cálculo de Google Sheets.
  "pasa mis gastos a una hoja", "exporta mis gastos a Excel", "pásame los gastos del mes a Sheets" → sin campos.
- "google_docs": el dueño pide generar un informe o documento en Google Docs.
  "genera un informe del mes", "hazme un documento con el resumen del mes" → sin campos.
- "add_contact": el dueño quiere AGREGAR/GUARDAR un contacto nuevo en su CRM.
  Ejemplos: "agrega a Juliana con número 573001234567", "guarda el contacto de Pedro 3005558899", "añade a María al CRM: 57 310 555 8899", "apúntame este contacto: Juan, 3114445566".
  Extrae el nombre en "contact_name" y el teléfono SOLO DÍGITOS en "contact_phone" (con o sin 57 del país).
  Si el mensaje trae datos extra (dirección, notas), ponlos en "description".
  Solo es "add_contact" cuando da un NÚMERO nuevo; si solo dice "escríbele a X" es "send_message".
- "web_search": el dueño pide BUSCAR INFORMACIÓN EN INTERNET o ABRIR una página web.
  Para buscar: "busca en internet el precio del cobre", "búscame en la web cómo instalar un breaker", "googlea el clima de Medellín", "consulta en internet los horarios de SENA", "busca información sobre normatividad eléctrica".
  Extrae SOLO los términos de búsqueda en "message_text" (ej: para "busca en internet el precio del cobre" → "precio del cobre").
  Para abrir una página: "navega a [URL]", "abre esta página [URL]", "qué hay en esta web [URL]" → "message_text" = la URL.
  IMPORTANTE: cualquier pedido de información que implique internet/web/google ("¿cuánto vale X?", "¿dónde queda Y?" cuando piden datos externos) usa "web_search", NO "chat".
- "support": el dueño quiere contactar al SOPORTE DE LA PLATAFORMA (el admin).
  Ejemplos: "soporte: necesito ayuda con mi cuenta", "ayuda: no me llegan los mensajes", "contactar al equipo de soporte", "quiero hablar con soporte".
  Extrae el motivo en "message_text". El bot reenviará esto al WhatsApp del admin.
- "manage_services": el dueño quiere ACTIVAR, DESACTIVAR o LISTAR sus servicios/módulos.
  Ejemplos: "activa recordatorios", "desactiva cobro de cartera", "qué servicios tengo", "lista mis servicios", "enciende el inventario", "apaga seguimiento de cotizaciones".
  Extrae la acción en "message_text" ("enable", "disable", "list") y el nombre/key del servicio en "contact_name" o "description".
- "sync_contacts": el dueño quiere SINCRONIZAR sus contactos de Google al CRM.
  Ejemplos: "sincroniza contactos de google", "importa mis contactos de google", "trae contactos de gmail", "actualiza contactos desde google".
  Sin campos adicionales.
- "help": el dueño pide la GUÍA de comandos del asistente.
  Ejemplos: "ayuda", "comandos", "qué puedes hacer", "guía", "herramientas", "manual", "lista de comandos".
  Sin campos adicionales. El asistente responde con la guía paso a paso de qué puede hacer.
- "chat": todo lo demás: preguntas, charla, pedidos que aún no existen como acción.
  IMPORTANTE: las preguntas sobre lo que el asistente puede hacer ("qué puedes hacer", "quién eres", "tienes acceso a mis contactos") y las preguntas de capacidad NO son acciones → usa "chat" para que el asistente responda conversando.

Responde SOLO un JSON válido, sin texto adicional:
{{"intention": "send_message", "contact_name": "Juliana", "message_text": "¡Buenos días, Juliana! 🌞 Que tengas un excelente día."}}
{{"intention": "quote", "contact_name": "Juliana"}}
{{"intention": "invoice", "contact_name": "Juliana", "amount": 500000, "description": "Instalación de 5 tomacorrientes"}}
{{"intention": "confirm", "message_text": "sí"}}
{{"intention": "expense", "amount": 45000, "description": "cable THHN"}}
{{"intention": "expense", "amount": 500000, "description": "cobró Juliana instalación"}}
{{"intention": "expense", "message_text": "cuánto tengo en mi cartera"}}
{{"intention": "web_search", "message_text": "precio del cobre hoy"}}
{{"intention": "add_contact", "contact_name": "Juliana", "contact_phone": "573001234567"}}
{{"intention": "chat"}}
{{"intention": "support", "message_text": "Necesito ayuda con mi suscripción, no me llegan los cobros"}}
{{"intention": "manage_services", "message_text": "enable", "description": "recordatorios"}}
{{"intention": "manage_services", "message_text": "disable", "description": "cobro de cartera"}}
{{"intention": "manage_services", "message_text": "list"}}
{{"intention": "sync_contacts"}}
{{"intention": "help"}}

REGLAS:
- "contact_name": el nombre tal como lo menciona el dueño (null si no aplica).
- "message_text": el mensaje listo para enviar, cálido, corto y en español (solo para send_message). Si el dueño dio texto literal entre comillas, úsalo tal cual.
- Si la orden pide cotizar y menciona un cliente ("cotizale a Juliana..."), usa "quote" con el contact_name del cliente.
- "remind_at" SIEMPRE en ISO 8601 con fecha REAL calculada desde la fecha actual de arriba. «mañana» = hoy + 1 día. «el jueves» = el próximo jueves desde hoy. Nunca inventes fechas de otros meses.
- Ante la duda, "chat"."""


def _parse_intent(raw: str) -> AssistantIntent:
    """Extrae el JSON de intención de la respuesta del LLM.

    Tolerante con modelos de razonamiento (Nemotron): pueden anteponer
    su cadena de pensamiento y citar ejemplos. Estrategia: probar cada
    bloque {…} balanceado, del ÚLTIMO al primero (el JSON final es la
    respuesta real); el primero válido gana.
    """
    candidates: list[str] = []
    depth = 0
    block_start = -1
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                block_start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and block_start != -1:
                    candidates.append(raw[block_start : i + 1])

    for candidate in reversed(candidates):
        try:
            payload = json.loads(candidate)
            return AssistantIntent.model_validate(payload)
        except Exception:
            continue
    raise ValueError("La respuesta del router no contiene JSON")


def _now_context() -> str:
    """Fecha/hora actual en Colombia para el prompt (evita alucinar «mañana»)."""
    from app.services.time_window import colombia_now

    now = colombia_now()
    dias = ("lunes", "martes", "miércoles", "jueves", "viernes",
            "sábado", "domingo")
    return (
        f"FECHA ACTUAL (Colombia): {dias[now.weekday()]} "
        f"{now.day} de {now.strftime('%B')} de {now.year}, "
        f"{now.strftime('%H:%M')} (hora 24h). Zona: UTC-5, sin horario de verano."
    )


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
        # La detección de intención es clasificación: un modelo rápido basta
        # (si no se define llm_model_intent, cae al modelo general).
        response = await client.chat.completions.create(
            model=settings.llm_model_intent or settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": _now_context()
                    + "\n\n"
                    + _SYSTEM_PROMPT.format(
                        bot_name=tenant.bot_name, tenant_name=tenant.name
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0,
            # Nemotron es un modelo de RAZONAMIENTO: el contenido de
            # razonamiento consume presupuesto. Sin margen, la respuesta
            # llega como cadena de pensamiento sin JSON válido.
            max_tokens=2000,
        )
        raw = (response.choices[0].message.content or "").strip()
        # Modelos de razonamiento pueden filtrar el chain-of-thought al
        # contenido: si no hay JSON arriba, buscar el ÚLTIMO bloque {}
        # (el razonamiento a veces cita ejemplos; el JSON final gana).
        return _parse_intent(raw)
    except Exception:
        logger.exception("El router de intenciones falló; se asume 'chat'")
        return AssistantIntent(intention="chat")
