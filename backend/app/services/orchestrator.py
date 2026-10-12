"""Cerebro conversacional del asistente (v1).

Por cada mensaje entrante de un cliente:
1. Si el servicio cotizador está apagado para el tenant → el bot permanece
   en silencio (apagado = no atiende).
2. Intenta la extracción con IA → si el catálogo matchea algo, crea la
   cotización, genera el PDF y lo envía al chat del cliente.
3. Si no, responde conversacionalmente con el LLM usando el contexto de la
   conversación (identifica al cliente, responde en español, nunca inventa
   precios).

Nunca revienta el webhook: toda falla se loguea y el cliente recibe una
nota amable si el canal está disponible.
"""

import base64
import logging
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.core.config import get_settings
from app.models import Contact, Conversation, Message, QuoteItem, Tenant, TenantModule
from app.schemas.quotes import QuoteCreate
from app.services import ai_extraction as ai_service
from app.services import pdf_generator as pdf_service
from app.services import quotes as quotes_service
from app.services.usage import log_service_usage

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Eres {bot_name}, el asistente por WhatsApp de {tenant_name}.
Ayudas al dueño del negocio a atender a sus clientes por WhatsApp.

REGLAS:
- Responde SIEMPRE en español, tono cercano y profesional, mensajes cortos
  (estilo WhatsApp).
- Las cotizaciones se arman con el catálogo de precios del negocio: NUNCA
  inventes precios ni prometas descuentos.
- Si el cliente pide una cotización, pídele los materiales o servicios que
  necesita y las cantidades.
- No ofrezcas servicios que no existen. Si preguntan por algo que no está
  disponible, dilo con claridad y ofrece tomarle el mensaje.
"""


async def _quoter_enabled(db: AsyncSession, tenant_id: UUID) -> bool:
    result = await db.execute(
        select(TenantModule.is_enabled).where(
            TenantModule.tenant_id == tenant_id,
            TenantModule.module_key == "quoter",
        )
    )
    return bool(result.scalar_one_or_none())


async def _conversation_history(
    db: AsyncSession, conversation_id: UUID, limit: int = 10
) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


async def _send_out_message(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    channel: Channel,
    wa_id: str,
    text: str,
) -> None:
    """Envía por el canal y persiste la respuesta como mensaje saliente."""
    await channel.send_text(wa_id, text)
    db.add(
        Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction="out",
            type="text",
            content=text,
            whatsapp_message_id=f"bot-{uuid.uuid4()}",
            status="sent",
        )
    )
    await db.commit()


async def handle_incoming(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    message: Message,
    contact: Contact,
    conversation: Conversation,
) -> None:
    """Atiende un mensaje entrante ya persistido (cerebro v1)."""
    settings = get_settings()

    # Sin canal configurado (Evolution apagado) no hay a quién responder
    if not settings.evolution_api_key:
        return
    # El bot solo atiende si el servicio cotizador está encendido
    if not await _quoter_enabled(db, tenant.id):
        return

    wa_id = contact.wa_id
    text = (message.content or "").strip()

    try:
        # Mensajes sin texto (audio/imagen aún sin transcribir)
        if not text:
            await _send_out_message(
                db,
                tenant_id=tenant.id,
                conversation=conversation,
                channel=channel,
                wa_id=wa_id,
                text=(
                    "¡Te recibí! Por ahora cuéntame el detalle por escrito "
                    "(materiales, cantidades) y te preparo la cotización."
                ),
            )
            return

        # 1) Intento de cotización: extracción con IA + matching del catálogo
        extraction = await ai_service.extract_items_from_text(
            db, tenant_id=tenant.id, text=text
        )

        if extraction.suggestions:
            items = [
                {
                    "description": suggestion.description,
                    "quantity": float(suggestion.quantity),
                    "unit_price": float(suggestion.unit_price or 0),
                    "catalog_item_id": suggestion.catalog_item_id,
                }
                for suggestion in extraction.suggestions
            ]
            quote = await quotes_service.create_quote(
                db,
                tenant_id=tenant.id,
                data=QuoteCreate(
                    contact_id=contact.id,
                    conversation_id=conversation.id,
                    items=items,
                ),
            )

            tenant_orm = (
                await db.execute(select(Tenant).where(Tenant.id == tenant.id))
            ).scalar_one()
            contact_orm = (
                await db.execute(select(Contact).where(Contact.id == contact.id))
            ).scalar_one()
            quote_items = (
                await db.execute(
                    select(QuoteItem).where(QuoteItem.quote_id == quote.id)
                )
            ).scalars().all()

            pdf_bytes = pdf_service.generate_quote_pdf(
                quote=quote,
                items=quote_items,
                tenant=tenant_orm,
                contact=contact_orm,
            )
            pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

            await _send_out_message(
                db,
                tenant_id=tenant.id,
                conversation=conversation,
                channel=channel,
                wa_id=wa_id,
                text=(
                    "Lista tu cotización 📄 Te la envío en PDF junto con el detalle. "
                    f"Quedo pendiente de tu confirmación."
                ),
            )
            await channel.send_document(
                wa_id,
                f"cotizacion_{str(quote.id)[:8]}.pdf",
                pdf_b64,
                "application/pdf",
            )
            await log_service_usage(
                db,
                tenant_id=tenant.id,
                module_key="quoter",
                kind="pdf",
                contact_id=contact.id,
            )
            logger.info("Cotización %s entregada por WhatsApp", quote.id)
            return

        # 2) Conversación: el LLM responde con el contexto del historial
        history = await _conversation_history(db, conversation.id)
        messages_payload = [
            {"role": "system", "content": _SYSTEM_PROMPT.format(
                bot_name=tenant.bot_name,
                tenant_name=tenant.name,
            )}
        ]
        for historical in history:
            role = "user" if historical.direction == "in" else "assistant"
            content_text = historical.content or f"[{historical.type}]"
            messages_payload.append({"role": role, "content": content_text})
        if not messages_payload[-1]["role"] == "user":
            messages_payload.append({"role": "user", "content": text})

        client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=30,
        )
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages_payload,
            temperature=0.6,
            max_tokens=400,
        )
        reply = (response.choices[0].message.content or "").strip()
        if reply:
            await _send_out_message(
                db,
                tenant_id=tenant.id,
                conversation=conversation,
                channel=channel,
                wa_id=wa_id,
                text=reply,
            )
            await log_service_usage(
                db,
                tenant_id=tenant.id,
                module_key="quoter",
                kind="message",
                contact_id=contact.id,
            )
    except Exception:
        logger.exception("El orquestador falló atendiendo el mensaje %s", message.id)
        try:
            await channel.send_text(
                wa_id,
                "Tuve un problema procesando tu mensaje. ¿Lo puedes repetir?",
            )
        except Exception:
            logger.exception("Tampoco pude avisar al cliente del fallo")
