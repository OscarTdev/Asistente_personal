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
import uuid
from datetime import UTC, datetime
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.core.config import get_settings
from app.models import (
    Contact,
    Conversation,
    Event,
    FollowUp,
    Message,
    Quote,
    QuoteItem,
    Tenant,
    TenantModule,
)
from app.schemas.assistant import AssistantIntent
from app.schemas.quotes import QuoteCreate
from app.services import ai_extraction as ai_service
from app.services import assistant as assistant_service
from app.services import onboarding as onboarding_service
from app.services import pdf_generator as pdf_service
from app.services import quotes as quotes_service
from app.services.ai_extraction import _escape_like
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
    """Envía por el canal y persiste la respuesta como mensaje saliente.

    El id real del mensaje (si el canal lo devuelve) se guarda para que el
    eco del webhook quede deduplicado: el bot nunca responde a sí mismo.
    """
    sent_id = await channel.send_text(wa_id, text)
    db.add(
        Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction="out",
            type="text",
            content=text,
            whatsapp_message_id=sent_id or f"bot-{uuid.uuid4()}",
            status="sent",
        )
    )
    await db.commit()


async def _resolve_contact_by_name(
    db: AsyncSession, *, tenant_id: UUID, name: str
) -> list[Contact]:
    """Contactos del tenant que responden al nombre (exacto o contenido)."""
    clean = name.strip()
    exact = (
        await db.execute(
            select(Contact).where(
                Contact.tenant_id == tenant_id,
                Contact.is_active.is_(True),
                func.lower(Contact.name) == clean.lower(),
            )
        )
    ).scalars().all()
    if exact:
        return list(exact)

    pattern = f"%{_escape_like(clean[:50])}%"
    partial = (
        await db.execute(
            select(Contact).where(
                Contact.tenant_id == tenant_id,
                Contact.is_active.is_(True),
                Contact.name.ilike(pattern),
            )
        )
    ).scalars().all()
    return list(partial)


async def _handle_send_message(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """El dueño pide escribirle a un contacto suyo: resuelve, envía y confirma.

    Ambigüedad = pregunta: si el nombre no existe o matchea a varios, el
    asistente pregunta en vez de arriesgar un mensaje a la persona equivocada.
    """
    name = (intent.contact_name or "").strip()
    text = (intent.message_text or "").strip()

    async def ask_owner(question: str) -> None:
        await _send_out_message(
            db,
            tenant_id=tenant.id,
            conversation=conversation,
            channel=channel,
            wa_id=wa_id,
            text=question,
        )

    if not name:
        await ask_owner("Claro: ¿a quién le escribo y qué le digo?")
        return
    if not text:
        await ask_owner(f"¿Y qué le quieres decir a {name}?")
        return

    matches = await _resolve_contact_by_name(db, tenant_id=tenant.id, name=name)
    if not matches:
        await ask_owner(
            f"No encontré a nadie llamado «{name}» en tus contactos. "
            "¿Me confirmas el nombre?"
        )
        return
    if len(matches) > 1:
        names = ", ".join(c.name or c.wa_id for c in matches[:5])
        await ask_owner(f"Encontré varios: {names}. ¿A cuál le escribo?")
        return

    target = matches[0]
    sent_id = await channel.send_text(target.wa_id, text)

    # El mensaje enviado queda en la conversación DEL CONTACTO (historial)
    target_conversation = (
        await db.execute(
            select(Conversation)
            .where(Conversation.contact_id == target.id)
            .order_by(
                Conversation.last_message_at.desc().nullslast(),
                Conversation.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if target_conversation is None:
        target_conversation = Conversation(
            tenant_id=tenant.id, contact_id=target.id, status="open"
        )
        db.add(target_conversation)
        await db.flush()

    db.add(
        Message(
            tenant_id=tenant.id,
            conversation_id=target_conversation.id,
            direction="out",
            type="text",
            content=text,
            whatsapp_message_id=sent_id or f"bot-{uuid.uuid4()}",
            status="sent",
        )
    )
    target_conversation.last_message_at = datetime.now(UTC)
    await db.commit()

    await _send_out_message(
        db,
        tenant_id=tenant.id,
        conversation=conversation,
        channel=channel,
        wa_id=wa_id,
        text=f"✅ Le escribí a {target.name or target.wa_id}: «{text}»",
    )
    logger.info("Mensaje enviado por encargo del dueño (contacto %s)", target.id)


async def _handle_quote(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    message: Message,
    intent: AssistantIntent,
) -> None:
    """Cotización por encargo del dueño: el PDF queda en SU chat.

    La cotización se crea en 'draft' y con el cliente mencionado (si existe
    en los contactos): el dueño la revisa y se la envía a su cliente; al
    marcarla como enviada en el panel, el seguimiento hace el resto.
    """
    extraction = await ai_service.extract_items_from_text(
        db, tenant_id=tenant.id, text=(message.content or "").strip()
    )

    suggestions = extraction.suggestions
    matched = [s for s in suggestions if s.matched and s.unit_price]
    unmatched = [s for s in suggestions if not (s.matched and s.unit_price)]

    async def tell_owner(text: str) -> None:
        await _send_out_message(
            db,
            tenant_id=tenant.id,
            conversation=conversation,
            channel=channel,
            wa_id=wa_id,
            text=text,
        )

    if unmatched:
        # La IA nunca inventa precios: nada de PDFs con ítems a $0
        db.add(
            Event(
                tenant_id=tenant.id,
                type="quote.needs_review",
                payload={
                    "items": [s.description for s in unmatched][:10],
                    "conversation_id": str(conversation.id),
                },
            )
        )
        await db.commit()
        await tell_owner(
            "Estoy verificando los precios de tu solicitud y te confirmo "
            "el valor en breve. 🙌"
        )
        return

    if not matched:
        await tell_owner(
            "No pude identificar los materiales o servicios. "
            "¿Me los listas con cantidades?"
        )
        return

    # ¿Para qué cliente es la cotización? Del nombre mencionado en la orden
    quote_contact: Contact | None = None
    if intent.contact_name:
        matches = await _resolve_contact_by_name(
            db, tenant_id=tenant.id, name=intent.contact_name
        )
        if len(matches) == 1:
            quote_contact = matches[0]

    items = [
        {
            "description": suggestion.description,
            "quantity": suggestion.quantity,
            "unit_price": suggestion.unit_price,
            "catalog_item_id": suggestion.catalog_item_id,
        }
        for suggestion in matched
    ]
    quote = await quotes_service.create_quote(
        db,
        tenant_id=tenant.id,
        data=QuoteCreate(
            contact_id=quote_contact.id if quote_contact else None,
            conversation_id=conversation.id,
            items=items,
        ),
    )

    tenant_orm = (
        await db.execute(select(Tenant).where(Tenant.id == tenant.id))
    ).scalar_one()
    quote_items = (
        await db.execute(
            select(QuoteItem).where(QuoteItem.quote_id == quote.id)
        )
    ).scalars().all()

    pdf_buffer = pdf_service.generate_quote_pdf(
        quote=quote,
        items=quote_items,
        tenant=tenant_orm,
        contact=quote_contact,
    )
    # El generador devuelve un BytesIO (el endpoint lo sirve como
    # StreamingResponse): para base64 hay que sacar los bytes.
    pdf_b64 = base64.b64encode(pdf_buffer.getvalue()).decode("ascii")

    client_label = (
        quote_contact.name if quote_contact and quote_contact.name else "tu cliente"
    )
    await tell_owner(
        f"📄 Lista tu cotización para {client_label}. Te la dejo en PDF: "
        "cuando se la envíes, márcala como enviada en el panel y el "
        "seguimiento hace el resto."
    )
    doc_id = await channel.send_document(
        wa_id,
        f"cotizacion_{str(quote.id)[:8]}.pdf",
        pdf_b64,
        "application/pdf",
    )
    # Registrar el PDF enviado con su id real (el eco queda deduplicado)
    db.add(
        Message(
            tenant_id=tenant.id,
            conversation_id=conversation.id,
            direction="out",
            type="document",
            content=f"cotizacion_{str(quote.id)[:8]}.pdf",
            whatsapp_message_id=doc_id or f"bot-{uuid.uuid4()}",
            status="sent",
        )
    )
    await db.commit()

    await log_service_usage(
        db,
        tenant_id=tenant.id,
        module_key="quoter",
        kind="pdf",
        contact_id=quote_contact.id if quote_contact else None,
    )
    logger.info("Cotización %s preparada para el dueño", quote.id)


async def _is_prospect(
    db: AsyncSession, *, contact: Contact, conversation: Conversation
) -> bool:
    """¿Es un prospecto nuevo (nunca atendido) o un cliente del dueño?

    Cliente = tiene cotizaciones, seguimientos o mensajes previos del bot
    (p. ej. respondió a un seguimiento). Prospecto = cero historial: el bot
    es la puerta de entrada y arranca el registro conversacional.
    """
    quotes_count = (
        await db.execute(
            select(func.count())
            .select_from(Quote)
            .where(Quote.contact_id == contact.id)
        )
    ).scalar_one()
    followups_count = (
        await db.execute(
            select(func.count())
            .select_from(FollowUp)
            .where(FollowUp.contact_id == contact.id)
        )
    ).scalar_one()
    bot_messages_count = (
        await db.execute(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.direction == "out",
            )
        )
    ).scalar_one()
    return quotes_count == 0 and followups_count == 0 and bot_messages_count == 0


async def handle_incoming(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    message: Message,
    contact: Contact,
    conversation: Conversation,
) -> None:
    """Atiende un mensaje entrante ya persistido.

    Rol del producto (definido por el dueño de la plataforma):
    - Al bot le escriben LOS CLIENTES DE LA PLATAFORMA (los técnicos que
      tienen el bot). Un número desconocido es un prospecto: el bot es la
      puerta de entrada y lo registra conversando (onboarding), creando su
      tenant en plan trial con su número como llave de enrutamiento.
    - Un dueño registrado le habla a su asistente: cotiza por encargo,
      manda mensajes a sus contactos o conversa.
    - Los clientes de los dueños (contactos con historial) quedan
      registrados (sus respuestas alimentan el seguimiento) pero el bot
      NUNCA les contesta.
    """
    settings = get_settings()

    # Sin canal configurado (Evolution apagado) no hay a quién responder
    if not settings.evolution_api_key:
        return

    is_owner = bool(tenant.wa_id) and contact.wa_id == tenant.wa_id

    if not is_owner:
        text_in = (message.content or "").strip()

        # Onboarding en curso → siguiente paso del registro
        if contact.onboarding_state:
            await onboarding_service.continue_onboarding(
                db,
                contact=contact,
                conversation=conversation,
                channel=channel,
                tenant=tenant,
                text=text_in,
            )
            return

        # Prospecto nuevo (cero historial) → el bot se presenta y registra
        if await _is_prospect(db, contact=contact, conversation=conversation):
            await onboarding_service.start_onboarding(
                db,
                contact=contact,
                conversation=conversation,
                channel=channel,
                tenant=tenant,
            )
            return

        # Cliente del dueño: registrado, histórico, y en silencio
        logger.debug("Mensaje %s de un cliente del dueño: el bot calla", message.id)
        return

    # ── El dueño le habla a su asistente ────────────────────────────────────

    # El asistente solo atiende con el cotizador encendido (contrato del plan)
    if not await _quoter_enabled(db, tenant.id):
        return

    wa_id = contact.wa_id
    text = (message.content or "").strip()

    try:
        # Sin texto: solo las notas de voz del dueño piden aclaración.
        # Documentos e imágenes van en silencio (eco de nuestros propios PDFs
        # incluido — además quedan deduplicados por id en la ingesta).
        if not text:
            if message.type == "audio":
                await _send_out_message(
                    db,
                    tenant_id=tenant.id,
                    conversation=conversation,
                    channel=channel,
                    wa_id=wa_id,
                    text=(
                        "¡Te recibí! Por ahora cuéntame el detalle por "
                        "escrito y te ayudo al instante."
                    ),
                )
            return

        intent = await assistant_service.detect_intent(tenant=tenant, text=text)

        if intent.intention == "send_message":
            await _handle_send_message(
                db,
                tenant=tenant,
                channel=channel,
                conversation=conversation,
                wa_id=wa_id,
                intent=intent,
            )
            return

        if intent.intention == "quote":
            await _handle_quote(
                db,
                tenant=tenant,
                channel=channel,
                conversation=conversation,
                wa_id=wa_id,
                message=message,
                intent=intent,
            )
            return

        # Conversación: el LLM responde con el contexto del historial
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
