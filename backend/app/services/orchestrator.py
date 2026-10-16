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
from decimal import Decimal
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.core.config import get_settings
from app.models import (
    ChannelIdentity,
    Contact,
    Conversation,
    Document,
    Event,
    FollowUp,
    Message,
    PendingAction,
    Quote,
    QuoteItem,
    Tenant,
    TenantModule,
    Warranty,
)
from app.schemas.assistant import AssistantIntent
from app.schemas.quotes import QuoteCreate
from app.services import ai_extraction as ai_service
from app.services import assistant as assistant_service
from app.services import onboarding as onboarding_service
from app.services import pdf_generator as pdf_service
from app.services import quotes as quotes_service
from app.services.ai_extraction import _escape_like
from app.services.documents import get_branding
from app.services.invoice_pdf import generate_invoice_pdf
from app.services.usage import log_service_usage

logger = logging.getLogger(__name__)


async def _load_logo_bytes(db: AsyncSession, tenant_id: UUID) -> bytes | None:
    """Logo actual del tenant para los encabezados de PDF (None si no hay)."""
    from app.models import TenantBranding

    branding = (
        await db.execute(
            select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    return branding.logo_bytes if branding else None


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

_CUSTOMER_PROMPT = """Eres {bot_name}, el asistente de WhatsApp de {tenant_name} \
(negocio de oficios en Colombia).
Atiendes a los clientes del negocio: mensajes cortos, cálidos y profesionales.

REGLAS:
- Responde SIEMPRE en español, tono cercano, estilo WhatsApp: una sola
  pregunta o idea por mensaje.
- NUNCA inventes precios, plazos ni promesas: los precios salen del
  catálogo del negocio y solo se comparten en una cotización formal.
- Si no sabes algo, si el cliente se queja o pide algo delicado, dile con
  naturalidad que lo conectas con el dueño y avísale por dentro.
- No menciones datos de otros clientes ni asumas información que no te dieron.
- Aclara que eres un asistente automático si te lo preguntan.
"""


async def _quoter_enabled(db: AsyncSession, tenant_id: UUID) -> bool:
    result = await db.execute(
        select(TenantModule.is_enabled).where(
            TenantModule.tenant_id == tenant_id,
            TenantModule.module_key == "quoter",
        )
    )
    return bool(result.scalar_one_or_none())


async def _module_usable(
    db: AsyncSession, *, tenant: Tenant, module_key: str
) -> tuple[bool, str | None]:
    """Un módulo es usable si el dueño lo encendió Y el motor lo autoriza
    (adendo §5: interruptor global → excepción → plan). El motivo alimenta
    el mensaje claro al dueño; nunca silencio técnico."""
    result = await db.execute(
        select(TenantModule.is_enabled).where(
            TenantModule.tenant_id == tenant.id,
            TenantModule.module_key == module_key,
        )
    )
    if not bool(result.scalar_one_or_none()):
        return False, None  # apagado por el dueño: el bot simplemente calla

    from app.services.service_engine import service_available

    return await service_available(
        db, tenant_id=tenant.id, plan=tenant.plan, service_key=module_key
    )


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


async def _handle_collection(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """Cobro de cartera: enviar un link de pago al cliente del dueño (spec §13).

    «cobrale a Juliana 450 mil por la instalación» → Juliana recibe el link
    de MercadoPago en su WhatsApp con un mensaje amable.
    """
    from app.services.mercadopago import create_collection_link

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    # Resolver el cliente
    target: Contact | None = None
    if intent.contact_name:
        matches = await _resolve_contact_by_name(
            db, tenant_id=tenant.id, name=intent.contact_name
        )
        if len(matches) == 1:
            target = matches[0]
        elif len(matches) > 1:
            names = ", ".join(c.name or c.wa_id for c in matches[:5])
            await tell_owner(f"Encontré varios: {names}. ¿A cuál le cobro?")
            return
        else:
            await tell_owner(
                f"No encontré a nadie llamado «{intent.contact_name}» en tus contactos."
            )
            return

    if intent.amount is None or intent.amount <= 0:
        await tell_owner("¿De cuánto es el cobro? (ej: 450000)")
        return

    amount = int(intent.amount)
    description = intent.description or "Servicios prestados"

    # Si no hay MP configurado, enviar solo el mensaje sin link
    settings = get_settings()
    mp_token = settings.mercadopago_access_token
    link = ""
    if mp_token:
        try:
            pref = await create_collection_link(
                tenant=tenant,
                amount_cop=amount,
                description=description,
                access_token=mp_token,
                notification_url=settings.mercadopago_notification_url or None,
            )
            link = pref.get("init_point") or pref.get("sandbox_init_point") or ""
        except Exception:
            logger.exception("No se pudo crear el link de cobro de MP")

    # Formatear el monto: 450000 → $450.000
    amount_str = f"${amount:,.0f}".replace(",", ".")
    target_name = target.name or target.wa_id if target else "tu cliente"

    # Enviar el cobro al CLIENTE
    if target:
        msg = (
            f"¡Hola {target.name or ''}! {tenant.name} te comparte un "
            f"cobro por {description}: {amount_str}.\n\n"
        )
        if link:
            msg += f"Puedes pagar aquí: {link}\n\n"
        msg += "¡Gracias por tu negocio!"
        await channel.send_text(target.wa_id, msg)

        # Registrar en la conversación del CLIENTE
        target_conv = (
            await db.execute(
                select(Conversation)
                .where(Conversation.contact_id == target.id)
                .order_by(Conversation.last_message_at.desc().nullslast())
                .limit(1)
            )
        ).scalar_one_or_none()
        if target_conv is None:
            target_conv = Conversation(
                tenant_id=tenant.id, contact_id=target.id, status="open"
            )
            db.add(target_conv)
            await db.flush()
        db.add(
            Message(
                tenant_id=tenant.id,
                conversation_id=target_conv.id,
                direction="out",
                type="text",
                content=msg,
                whatsapp_message_id=f"bot-{uuid.uuid4()}",
                status="sent",
            )
        )
        target_conv.last_message_at = datetime.now(UTC)
        await db.commit()

        mp_status = "Con link de pago." if link else "Sin link de MP (pendiente configurar)."
        await tell_owner(
            f"💰 Envié el cobro de {amount_str} a {target_name} "
            f"por «{description}». {mp_status}"
        )
    else:
        await tell_owner(
            f"💰 Cobro de {amount_str} por «{description}». "
            "Dime a qué contacto se lo envío."
        )


async def _handle_visit_report(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """Informe de visita técnica: PDF con hallazgos para el cliente (spec §13).

    «informe de visita para Juliana: revisé el tablero, cambié 2 breakers»
    → genera el PDF y lo envía al dueño con opción de compartirlo.
    """
    from app.services.documents import next_document_number
    from app.services.visit_report_pdf import generate_visit_report_pdf

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    description = (intent.description or "").strip()
    if not description:
        await tell_owner(
            "¿Cuál fue el trabajo realizado? Descríbelo y genero el informe."
        )
        return

    # Resolver el cliente
    target: Contact | None = None
    if intent.contact_name:
        matches = await _resolve_contact_by_name(
            db, tenant_id=tenant.id, name=intent.contact_name
        )
        if len(matches) == 1:
            target = matches[0]

    # Consecutivo del informe (IV-0001)
    number = await next_document_number(db, tenant_id=tenant.id, doc_type="visit_report")
    _DOC_PREFIX = {"visit_report": "IV"}
    # El next_document_number usa el prefijo correcto internamente
    # pero el resultado ya viene con el prefijo

    # Generar PDF
    tenant_orm = (
        await db.execute(select(Tenant).where(Tenant.id == tenant.id))
    ).scalar_one()
    pdf_buffer = generate_visit_report_pdf(
        tenant=tenant_orm,
        contact=target,
        report_number=number,
        description=description,
        findings=[],
        recommendations=[],
    )

    import base64 as b64mod
    pdf_b64 = b64mod.b64encode(pdf_buffer.getvalue()).decode("ascii")

    # Enviar al dueño
    client_label = target.name if target and target.name else "tu cliente"
    await tell_owner(
        f"📋 Informe de visita {number} listo para {client_label}. "
        "Te lo dejo en PDF."
    )
    await channel.send_document(
        wa_id, f"{number}.pdf", pdf_b64, "application/pdf"
    )

    # Registrar en la conversación del CLIENTE si existe
    if target:
        target_conv = (
            await db.execute(
                select(Conversation)
                .where(Conversation.contact_id == target.id)
                .order_by(Conversation.last_message_at.desc().nullslast())
                .limit(1)
            )
        ).scalar_one_or_none()
        if target_conv is None:
            target_conv = Conversation(
                tenant_id=tenant.id, contact_id=target.id, status="open"
            )
            db.add(target_conv)
            await db.flush()
        db.add(
            Message(
                tenant_id=tenant.id,
                conversation_id=target_conv.id,
                direction="out",
                type="document",
                content=f"{number}.pdf",
                whatsapp_message_id=f"bot-{uuid.uuid4()}",
                status="sent",
            )
        )
        target_conv.last_message_at = datetime.now(UTC)
        await db.commit()

        await tell_owner(
            f"¿Quieres que le envíe el informe a {client_label}?"
        )


async def _handle_maintenance(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """Mantenimiento preventivo: programar avisos recurrentes (spec §13).

    «programa mantenimiento de aire para Juliana cada 6 meses»
    → registra el mantenimiento y el bot avisa cuando toque.
    """
    from app.services.maintenance import parse_frequency_days

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    # ¿Es consulta o programación?
    text_lower = (intent.message_text or "").lower()
    query_words = ("qué mantenimientos", "que mantenimientos", "mis mantenimientos")
    if any(w in text_lower for w in query_words):
        # Listar mantenimientos activos
        from sqlalchemy import select as sel

        from app.models import Maintenance
        items = list(
            (
                await db.execute(
                    sel(Maintenance)
                    .where(
                        Maintenance.tenant_id == tenant.id,
                        Maintenance.status == "active",
                    )
                    .order_by(Maintenance.next_due.asc())
                )
            ).scalars().all()
        )
        if not items:
            await tell_owner(
                "No tienes mantenimientos programados. "
                "Dime «programa mantenimiento de X para [cliente] cada N meses»."
            )
        else:
            lines = ["🔧 Tus mantenimientos:\n"]
            for m in items:
                contact = (
                    await db.execute(
                        sel(Contact).where(Contact.id == m.contact_id)
                    )
                ).scalar_one_or_none()
                name = contact.name if contact else "—"
                due = m.next_due.strftime("%d/%m/%Y")
                lines.append(f"• {m.description[:50]} — {name} — próximo: {due}")
            await tell_owner("\n".join(lines))
        return

    # Programar: necesita cliente, descripción y frecuencia
    if not intent.contact_name:
        await tell_owner("¿Para qué cliente programo el mantenimiento?")
        return

    matches = await _resolve_contact_by_name(
        db, tenant_id=tenant.id, name=intent.contact_name
    )
    if len(matches) != 1:
        names = ", ".join(c.name or c.wa_id for c in matches[:5])
        await tell_owner(
            f"Encontré: {names}. ¿A cuál?" if matches else
            f"No encontré a «{intent.contact_name}»."
        )
        return
    target = matches[0]

    description = (intent.message_text or intent.description or "").strip()
    if not description:
        await tell_owner("¿Qué mantenimiento debo programar? (ej: limpieza de aire)")
        return

    freq = parse_frequency_days(
        intent.message_text or "" or description
    )
    if freq is None:
        freq = 180  # semestral por defecto

    from datetime import timedelta
    next_due = datetime.now(UTC) + timedelta(days=freq)

    from app.services.maintenance import schedule_maintenance as _sched
    m = await _sched(
        db,
        tenant_id=tenant.id,
        contact_id=target.id,
        description=description,
        frequency_days=freq,
        next_due=next_due,
    )

    due_str = next_due.strftime("%d/%m/%Y")
    await tell_owner(
        f"🔧 Listo: «{description}» para {target.name or target.wa_id} "
        f"cada {freq} días. Próximo aviso: {due_str}. "
        f"Le escribiré a {target.name or 'tu cliente'} cuando toque."
    )


async def _handle_warranty(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """Garantías: registrar qué se instaló y consultar las vigentes (spec §13).

    «registra garantía para Juliana: breaker 30A, 1 año»
    → el bot rastrea cuándo vence y puede avisar.
    """
    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    text_lower = (intent.message_text or "").lower()
    query_words = (
        "qué garantías", "que garantías", "mis garantías",
        "garantías vigentes", "garantias vigentes",
    )
    if any(w in text_lower for w in query_words):
        # Listar garantías activas
        items = list(
            (
                await db.execute(
                    select(Warranty)
                    .where(
                        Warranty.tenant_id == tenant.id,
                        Warranty.status == "active",
                    )
                    .order_by(Warranty.expires_at.asc())
                )
            ).scalars().all()
        )
        if not items:
            await tell_owner(
                "No tienes garantías registradas. "
                "Dime «registra garantía para [cliente]: [qué], [cuánto tiempo]»."
            )
        else:
            now = datetime.now(UTC)
            lines = ["🛡️ Tus garantías:\n"]
            for w in items:
                contact = (
                    await db.execute(
                        select(Contact).where(Contact.id == w.contact_id)
                    )
                ).scalar_one_or_none()
                name = contact.name if contact else "—"
                expires = w.expires_at.strftime("%d/%m/%Y")
                expired = " ⚠️ VENCIDA" if w.expires_at < now else ""
                lines.append(f"• {w.item[:50]} — {name} — vence: {expires}{expired}")
            await tell_owner("\n".join(lines))
        return

    # Registrar: necesita cliente, item y duración
    if not intent.contact_name:
        await tell_owner("¿Para qué cliente registro la garantía?")
        return

    matches = await _resolve_contact_by_name(
        db, tenant_id=tenant.id, name=intent.contact_name
    )
    if len(matches) != 1:
        if matches:
            await tell_owner("Encontré varios. ¿A cuál?")
        else:
            await tell_owner(f"No encontré a «{intent.contact_name}».")
        return
    target = matches[0]

    item = (intent.description or "").strip()
    if not item:
        await tell_owner("¿Qué se instaló? (ej: breaker 30A Schneider)")
        return

    # Calcular fecha de vencimiento
    from datetime import timedelta
    now = datetime.now(UTC)
    if intent.remind_at:
        try:
            expires_at = datetime.fromisoformat(intent.remind_at)
        except ValueError:
            expires_at = now + timedelta(days=365)
    else:
        # Parsear duración del texto
        from app.services.maintenance import parse_frequency_days
        days = parse_frequency_days(intent.message_text or item)
        expires_at = now + timedelta(days=days or 365)

    db.add(
        Warranty(
            tenant_id=tenant.id,
            contact_id=target.id,
            item=item[:500],
            installed_at=now,
            expires_at=expires_at,
        )
    )
    await db.commit()

    expires_str = expires_at.strftime("%d/%m/%Y")
    await tell_owner(
        f"🛡️ Garantía registrada: «{item}» para "
        f"{target.name or target.wa_id} hasta el {expires_str}."
    )


async def _handle_inventory(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """Inventario de materiales: registrar, consultar y descontar (spec §13).

    «tengo 20 metros de cable» / «qué inventario tengo» / «usé 5 breakers»
    """
    from app.services.inventory import (
        _fmt_qty,
        add_stock,
        deduct_stock,
        list_inventory,
    )

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    text_lower = (intent.message_text or "").lower()

    # Consultar
    query_words = (
        "qué inventario", "que inventario", "mis materiales",
        "qué materiales tengo", "que materiales tengo", "inventario tengo",
    )
    if any(w in text_lower for w in query_words):
        items = await list_inventory(db, tenant_id=tenant.id)
        if not items:
            await tell_owner(
                "📦 Tu inventario está vacío. "
                "Dime «tengo [cantidad] [unidad] de [material]» para empezar."
            )
            return
        lines = ["📦 Tu inventario:\n"]
        for it in items:
            low = " ⚠️ BAJO" if it.min_quantity > 0 and it.quantity <= it.min_quantity else ""
            lines.append(f"• {it.name[:60]}: {_fmt_qty(it.quantity, it.unit)}{low}")
        await tell_owner("\n".join(lines))
        return

    # Descontar
    deduct_words = (
        "usé", "use", "gasté", "gaste",
        "agoté", "agote", "quité", "quite",
        "consumí", "consumi",
    )
    is_deduct = any(w in text_lower for w in deduct_words)

    if intent.amount is None or intent.amount <= 0:
        await tell_owner(
            "¿Qué material? Dime la cantidad y el nombre "
            "(ej: «tengo 20 metros de cable» o «usé 5 breakers»)."
        )
        return

    description = (intent.description or "").strip()
    if not description:
        await tell_owner("¿Qué material? (ej: cable THHN, breaker 30A)")
        return

    from decimal import Decimal as D
    qty = D(str(int(intent.amount)))

    if is_deduct:
        item = await deduct_stock(
            db, tenant_id=tenant.id, name=description, quantity=qty,
        )
        if item is None:
            await tell_owner(
                f"No tienes suficiente «{description}» en inventario, "
                "o el material no está registrado."
            )
        else:
            await tell_owner(
                f"📦 {item.name}: {_fmt_qty(item.quantity, item.unit)} "
                f"restantes (desconté {qty})."
            )
    else:
        item = await add_stock(
            db, tenant_id=tenant.id,
            name=description,
            quantity=qty,
        )
        await tell_owner(
            f"📦 Inventario actualizado: {item.name} → "
            f"{_fmt_qty(item.quantity, item.unit)}."
        )


async def _handle_expense(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """Finanzas personales: registrar gastos y resumen mensual (spec §13).

    «gasté 45 mil en cable» → categoría auto-detectada + registro
    «cuánto he gastado este mes» → resumen por categoría
    """
    from app.services.expenses import (
        _format_cop,
        monthly_summary,
        record_expense,
    )

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    # ¿Consulta o registro?
    text_lower = (intent.message_text or "").lower()
    query_words = (
        "cuánto he gastado", "cuanto he gastado", "resumen de gastos",
        "mis gastos", "cuánto he gastado este mes", "resumen del mes",
        "cuanto he gastado este mes", "cuánto he gastado", "gastos del mes",
    )
    if any(w in text_lower for w in query_words):
        summary = await monthly_summary(db, tenant_id=tenant.id)
        if summary["total"] == 0:
            await tell_owner(
                "No tienes gastos registrados este mes. "
                "Dime «gasté [monto] en [qué]» para empezar."
            )
            return

        lines = [f"📊 Gastos de {summary['month']}:\n"]
        lines.append(f"TOTAL: {_format_cop(summary['total'])}\n")
        for category, data in summary["categories"].items():
            cat_total = data["total"]
            lines.append(
                f"• {category.title()}: {_format_cop(cat_total)} "
                f"({data['count']} gasto{'s' if data['count'] > 1 else ''})"
            )
        await tell_owner("\n".join(lines))
        return

    # Registrar gasto
    if intent.amount is None or intent.amount <= 0:
        await tell_owner("¿Cuánto gastaste? Dime el monto (ej: 45000)")
        return

    description = (intent.description or "Gasto").strip()
    if not description or description == "Gasto":
        await tell_owner("¿En qué lo gastaste? (ej: cable, gasolina, almuerzo)")
        return

    from decimal import Decimal as D
    amount = D(str(int(intent.amount)))
    expense = await record_expense(
        db, tenant_id=tenant.id,
        description=description,
        amount=amount,
    )
    await tell_owner(
        f"💸 Gasto registrado: {_format_cop(amount)} en "
        f"**{expense.category}** ({description})"
    )


async def _handle_note(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    text: str,
) -> None:
    """Notas del dueño: guardar, listar, buscar y borrar por chat (spec §13)."""
    from app.services import notes as notes_service

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    action = notes_service.detect_note_action(text)

    if action == "save":
        # Extraer el contenido: lo que va después del comando
        content = text.strip()
        for prefix in ("guarda una nota:", "guarda una nota", "guárdame:", "guárdame",
                       "apunta:", "apunta", "anota:", "anota", "recuerda que",
                       "toma nota:", "toma nota", "nota:"):
            if content.lower().startswith(prefix.lower()):
                content = content[len(prefix):].strip()
                break
        if not content:
            await tell_owner("¿Qué quieres que te anote?")
            return
        note = await notes_service.save_note(
            db, tenant_id=tenant.id, content=content
        )
        await tell_owner(f"📝 Anotado: «{note.content}»")

    elif action == "list":
        items = await notes_service.list_notes(db, tenant_id=tenant.id)
        if not items:
            await tell_owner(
                "No tienes notas. Dime «guarda una nota: ...» para empezar."
            )
        else:
            lines = [f"📝 Tus últimas {len(items)} notas:\n"]
            for i, note in enumerate(items, 1):
                short = note.content[:80] + ("..." if len(note.content) > 80 else "")
                lines.append(f"{i}. {short}")
            await tell_owner("\n".join(lines))

    elif action == "search":
        # Extraer el término: lo que va después de "busca" / "encuentra"
        query = text.lower()
        for prefix in ("busca la nota", "busca", "encuentra", "hay alguna nota"):
            if query.startswith(prefix):
                query = text[len(prefix):].strip()
                break
        if not query:
            await tell_owner("¿Qué nota buscas?")
            return
        items = await notes_service.search_notes(
            db, tenant_id=tenant.id, query=query
        )
        if not items:
            await tell_owner(f"No encontré notas sobre «{query}».")
        else:
            lines = [f"🔍 Encontré {len(items)} nota(s):\n"]
            for note in items:
                lines.append(f"• {note.content[:100]}")
            await tell_owner("\n".join(lines))

    elif action == "delete":
        query = text.lower()
        for prefix in ("borra la nota", "borra", "elimina la nota",
                       "elimina", "quita la nota", "quita"):
            if query.startswith(prefix):
                query = text[len(prefix):].strip()
                break
        # Quitar artículos/preposiciones del inicio: «del cable» → «cable»
        for filler in ("del ", "de ", "la ", "el ", "los ", "las ", "sobre "):
            if query.lower().startswith(filler):
                query = query[len(filler):].strip()
                break
        if not query:
            await tell_owner("¿Qué nota quieres borrar?")
            return
        deleted = await notes_service.soft_delete_note(
            db, tenant_id=tenant.id, query=query
        )
        if deleted:
            await tell_owner(f"🗑️ Borré {deleted} nota(s) sobre «{query}».")
        else:
            await tell_owner(f"No encontré notas sobre «{query}» para borrar.")


async def _handle_reminder(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """Recordatorios: el bot escribe al dueño en la fecha programada."""
    from datetime import datetime as dt

    from app.services import notes as notes_service

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    content = (intent.message_text or "").strip()
    if not content:
        # Extraer el contenido del texto original
        content = intent.description or "Recordatorio"
    if not content:
        await tell_owner("¿Qué quieres que te recuerde?")
        return

    # Parsear la fecha del intent (ISO 8601) o usar +1 día como default
    from datetime import timedelta

    remind_at = None
    if intent.remind_at:
        try:
            remind_at = dt.fromisoformat(intent.remind_at)
        except ValueError:
            pass
    if remind_at is None:
        # Default: mañana a las 8:00 AM Colombia (UTC-5 → 13:00 UTC)
        now = datetime.now(UTC)
        tomorrow = (now + timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
        remind_at = tomorrow

    await notes_service.save_reminder(
        db, tenant_id=tenant.id, content=content, remind_at=remind_at
    )
    # Formatear la fecha para mostrar (hora Colombia = UTC-5)
    colombia_time = remind_at - timedelta(hours=5)
    when = colombia_time.strftime("%d/%m a las %I:%M %p")
    await tell_owner(f"⏰ Listo: te recordaré «{content}» el {when}.")


async def _handle_confirmation(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    text: str,
) -> bool:
    """Procesa una confirmación si hay una acción pendiente.

    Devuelve True si la acción se ejecutó (el orquestador no sigue).
    """
    pending = (
        await db.execute(
            select(PendingAction)
            .where(
                PendingAction.conversation_id == conversation.id,
                PendingAction.status == "pending",
            )
            .order_by(PendingAction.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if pending is None:
        return False

    lowered = text.lower().strip()
    yes_words = ("si", "sí", "dale", "ok", "claro", "envía", "envia",
                 "mánda", "manda", "confirmo", "listo", "seguro", "puedes")
    no_words = ("no", "después", "despues", "luego", "cancela", "espera", "nuevo")

    if any(word in lowered for word in no_words):
        pending.status = "cancelled"
        await db.commit()
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id,
            text="Entendido, no la envío. Dime si necesitas algo más.",
        )
        return True

    if any(word in lowered for word in yes_words):
        pending.status = "confirmed"
        await db.commit()

        if pending.action_type == "send_quote":
            payload = pending.payload
            quote_id = UUID(payload["quote_id"])
            contact_id = UUID(payload["contact_id"])

            quote = (
                await db.execute(select(Quote).where(Quote.id == quote_id))
            ).scalar_one_or_none()
            target_contact = (
                await db.execute(
                    select(Contact).where(Contact.id == contact_id)
                )
            ).scalar_one_or_none()
            if quote is None or target_contact is None:
                return False

            tenant_orm = (
                await db.execute(select(Tenant).where(Tenant.id == tenant.id))
            ).scalar_one()
            quote_items = (
                await db.execute(
                    select(QuoteItem).where(QuoteItem.quote_id == quote.id)
                )
            ).scalars().all()
            doc = (
                await db.execute(
                    select(Document)
                    .where(Document.quote_id == quote.id)
                    .order_by(Document.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            doc_number = doc.number if doc else f"COT-{str(quote.id)[:8]}"

            pdf_buffer = pdf_service.generate_quote_pdf(
                quote=quote, items=quote_items, tenant=tenant_orm,
                contact=target_contact, doc_number=doc_number,
            )
            import base64 as b64mod
            pdf_b64 = b64mod.b64encode(pdf_buffer.getvalue()).decode("ascii")

            await channel.send_document(
                target_contact.wa_id,
                f"{doc_number}.pdf",
                pdf_b64,
                "application/pdf",
            )

            # Registrar en la conversación del CLIENTE
            target_conv = (
                await db.execute(
                    select(Conversation)
                    .where(Conversation.contact_id == target_contact.id)
                    .order_by(Conversation.last_message_at.desc().nullslast())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if target_conv is not None:
                db.add(
                    Message(
                        tenant_id=tenant.id,
                        conversation_id=target_conv.id,
                        direction="out",
                        type="document",
                        content=f"{doc_number}.pdf",
                        whatsapp_message_id=f"bot-{uuid.uuid4()}",
                        status="sent",
                    )
                )

            # La cotización pasa a 'sent' → el seguimiento la cobra
            quote.status = "sent"
            quote.sent_at = datetime.now(UTC)
            await db.commit()

            await _send_out_message(
                db, tenant_id=tenant.id, conversation=conversation,
                channel=channel, wa_id=wa_id,
                text=(
                    f"✅ Envié {doc_number} a "
                    f"{target_contact.name or target_contact.wa_id}. "
                    "El seguimiento le escribirá a los 3 y 7 días."
                ),
            )
            return True

        if pending.action_type == "send_invoice":
            payload = pending.payload
            contact_id = UUID(payload["contact_id"])
            doc_number = payload.get("doc_number", "CC-0001")

            target_contact = (
                await db.execute(
                    select(Contact).where(Contact.id == contact_id)
                )
            ).scalar_one_or_none()
            if target_contact is None:
                return False

            doc = (
                await db.execute(
                    select(Document).where(Document.number == doc_number)
                )
            ).scalar_one_or_none()
            if doc is None:
                return False

            snapshot = doc.snapshot
            tenant_orm = (
                await db.execute(select(Tenant).where(Tenant.id == tenant.id))
            ).scalar_one()

            pdf_buffer = generate_invoice_pdf(
                tenant=tenant_orm,
                contact=target_contact,
                doc_number=doc_number,
                description=snapshot.get("description", "Servicios"),
                amount=Decimal(snapshot.get("amount", "0")),
                bank_details=snapshot.get("bank_details"),
                logo_bytes=await _load_logo_bytes(db, tenant.id),
            )
            import base64 as b64mod
            pdf_b64 = b64mod.b64encode(pdf_buffer.getvalue()).decode("ascii")
            await channel.send_document(
                target_contact.wa_id,
                f"{doc_number}.pdf",
                pdf_b64,
                "application/pdf",
            )
            await _send_out_message(
                db, tenant_id=tenant.id, conversation=conversation,
                channel=channel, wa_id=wa_id,
                text=f"✅ Envié {doc_number} a {target_contact.name or target_contact.wa_id}.",
            )
            return True

    # Ni sí ni no: la acción sigue pendiente
    await _send_out_message(
        db, tenant_id=tenant.id, conversation=conversation,
        channel=channel, wa_id=wa_id,
        text=(
            "Tengo una acción pendiente de tu confirmación. "
            "¿Quieres que la envíe? Responde «sí» o «no»."
        ),
    )
    return True


async def _handle_invoice(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """Cuenta de cobro: generar PDF y preguntar antes de enviar al cliente."""
    from decimal import Decimal

    from app.services.documents import create_document
    from app.services.invoice_pdf import generate_invoice_pdf

    async def tell_owner(text: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=text,
        )

    # Resolver cliente
    quote_contact: Contact | None = None
    if intent.contact_name:
        matches = await _resolve_contact_by_name(
            db, tenant_id=tenant.id, name=intent.contact_name
        )
        if len(matches) == 1:
            quote_contact = matches[1] if False else matches[0]

    if intent.amount is None or intent.amount <= 0:
        await tell_owner("¿De cuánto es la cuenta de cobro? (ej: 500000)")
        return

    amount = Decimal(str(intent.amount))
    description = intent.description or "Servicios prestados"

    # Consecutivo + snapshot
    branding = await get_branding(db, tenant_id=tenant.id)
    snapshot = {
        "tenant_name": tenant.name,
        "tenant_nit": tenant.nit,
        "client_name": quote_contact.name if quote_contact else None,
        "amount": str(amount),
        "description": description,
        "bank_details": branding.bank_details if branding else None,
    }
    document = await create_document(
        db, tenant_id=tenant.id, doc_type="invoice", snapshot=snapshot,
    )
    await db.commit()

    # PDF
    tenant_orm = (
        await db.execute(select(Tenant).where(Tenant.id == tenant.id))
    ).scalar_one()
    pdf_buffer = generate_invoice_pdf(
        tenant=tenant_orm,
        contact=quote_contact,
        doc_number=document.number,
        description=description,
        amount=amount,
        bank_details=branding.bank_details if branding else None,
        logo_bytes=branding.logo_bytes if branding else None,
    )

    import base64 as b64mod
    pdf_b64 = b64mod.b64encode(pdf_buffer.getvalue()).decode("ascii")

    # Enviar al dueño
    client_label = quote_contact.name if quote_contact else "tu cliente"
    await tell_owner(
        f"🧾 Lista la cuenta de cobro {document.number} para {client_label} "
        f"por {_format_cop(amount)}. Te la dejo en PDF."
    )
    await channel.send_document(
        wa_id, f"{document.number}.pdf", pdf_b64, "application/pdf"
    )

    # Si hay cliente, preguntar antes de enviar
    if quote_contact:
        db.add(
            PendingAction(
                tenant_id=tenant.id,
                conversation_id=conversation.id,
                action_type="send_invoice",
                payload={
                    "document_id": str(document.id),
                    "contact_id": str(quote_contact.id),
                    "doc_number": document.number,
                },
            )
        )
        await db.commit()
        await tell_owner(
            f"¿Quieres que le envíe {document.number} a {client_label}?"
        )


def _format_cop(amount: Decimal | float | int) -> str:
    try:
        return f"${float(amount):,.0f}".replace(",", ".")
    except Exception:
        return f"${amount}"


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

    # Consecutivo legible (COT-0001) + snapshot inmutable del documento
    from app.services.documents import create_document

    snapshot = {
        "tenant_name": tenant_orm.name,
        "tenant_nit": tenant_orm.nit,
        "bot_name": tenant_orm.bot_name,
        "client_name": quote_contact.name if quote_contact else None,
        "client_wa_id": quote_contact.wa_id if quote_contact else None,
        "items": [
            {
                "description": it.description,
                "quantity": str(it.quantity),
                "unit_price": str(it.unit_price),
                "line_total": str(it.line_total),
            }
            for it in quote_items
        ],
        "total": str(quote.total),
        "quote_id": str(quote.id),
    }
    document = await create_document(
        db,
        tenant_id=tenant.id,
        doc_type="quote",
        snapshot=snapshot,
        quote_id=quote.id,
    )
    doc_number = document.number

    pdf_buffer = pdf_service.generate_quote_pdf(
        quote=quote,
        items=quote_items,
        tenant=tenant_orm,
        contact=quote_contact,
        doc_number=doc_number,
    )
    # El generador devuelve un BytesIO (el endpoint lo sirve como
    # StreamingResponse): para base64 hay que sacar los bytes.
    pdf_b64 = base64.b64encode(pdf_buffer.getvalue()).decode("ascii")

    client_label = (
        quote_contact.name if quote_contact and quote_contact.name else "tu cliente"
    )
    if quote_contact:
        await tell_owner(
            f"📄 Lista tu cotización {doc_number} para {client_label}. "
            "Te la dejo en PDF. ¿Quieres que se la envíe?"
        )
    else:
        await tell_owner(
            f"📄 Lista tu cotización {doc_number}. Te la dejo en PDF."
        )
    doc_id = await channel.send_document(
        wa_id,
        f"{doc_number}.pdf",
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
            content=f"{doc_number}.pdf",
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

    # Si hay cliente destino: pedir confirmación antes de enviarle (spec §9.1)
    if quote_contact:
        db.add(
            PendingAction(
                tenant_id=tenant.id,
                conversation_id=conversation.id,
                action_type="send_quote",
                payload={
                    "quote_id": str(quote.id),
                    "contact_id": str(quote_contact.id),
                    "doc_number": doc_number,
                },
            )
        )
        await db.commit()


async def _send_voice_reply(
    db: AsyncSession,
    *,
    tenant: Tenant,
    conversation: Conversation,
    channel: Channel,
    wa_id: str,
) -> None:
    """Envía la última respuesta del bot también como nota de voz (spec §12).

    El texto YA fue enviado por _chat_reply; esto añade la versión hablada.
    Si la síntesis falla, no revienta nada — el texto ya llegó.
    """
    try:
        from app.services.audio import get_tts_provider

        # Buscar el último mensaje saliente (la respuesta que acabamos de dar)
        last_out = (
            await db.execute(
                select(Message)
                .where(
                    Message.conversation_id == conversation.id,
                    Message.direction == "out",
                    Message.type == "text",
                )
                .order_by(Message.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if last_out is None or not last_out.content:
            return

        provider = get_tts_provider()
        if provider is None:
            return

        audio_bytes = await provider.synthesize(last_out.content)
        if not audio_bytes:
            return

        import base64 as b64mod
        audio_b64 = b64mod.b64encode(audio_bytes).decode("ascii")
        sent_id = await channel.send_document(
            wa_id,
            f"respuesta_{uuid.uuid4().hex[:8]}.mp3",
            audio_b64,
            "audio/mpeg",
        )
        db.add(
            Message(
                tenant_id=tenant.id,
                conversation_id=conversation.id,
                direction="out",
                type="audio",
                content=last_out.content,
                whatsapp_message_id=sent_id or f"bot-voice-{uuid.uuid4()}",
                status="sent",
            )
        )
        await db.commit()
        logger.debug("Respuesta de voz enviada a %s", wa_id)
    except Exception:
        # La versión en texto ya llegó: la voz es best-effort
        logger.exception("No se pudo enviar la respuesta de voz")


async def _is_team_member(
    db: AsyncSession, *, tenant: Tenant, contact: Contact
) -> bool:
    """¿El remitente es dueño o equipo? Identidad owner/team o legado wa_id."""
    if tenant.wa_id and contact.wa_id == tenant.wa_id:
        return True
    identity = (
        await db.execute(
            select(ChannelIdentity).where(
                ChannelIdentity.channel == "whatsapp",
                ChannelIdentity.external_id == contact.wa_id,
                ChannelIdentity.tenant_id == tenant.id,
            )
        )
    ).scalar_one_or_none()
    return identity is not None and identity.kind in ("owner", "team")


async def _client_context_block(db: AsyncSession, conversation: Conversation) -> str:
    """El bot recuerda quién es quién: memoria del cliente para el LLM.

    Nombre, etiquetas, dirección, apuntes, cotizaciones y notas recientes.
    Sin datos → bloque vacío (un desconocido se atiende igual).
    """
    from app.models import Note

    if conversation.contact_id is None:
        return ""
    contact = (
        await db.execute(select(Contact).where(Contact.id == conversation.contact_id))
    ).scalar_one_or_none()
    if contact is None:
        return ""

    lines: list[str] = []
    if contact.name:
        lines.append(f"- Se llama {contact.name}.")
    if contact.tags:
        lines.append(f"- Etiquetas: {', '.join(contact.tags)}.")
    if contact.address:
        lines.append(f"- Dirección: {contact.address}.")
    if contact.notes:
        lines.append(f"- Apuntes: {contact.notes[:300]}")

    quotes = (
        (
            await db.execute(
                select(Quote)
                .where(Quote.contact_id == contact.id)
                .order_by(Quote.created_at.desc())
                .limit(3)
            )
        )
        .scalars()
        .all()
    )
    for quote in quotes:
        fecha = quote.created_at.strftime("%d/%m/%Y") if quote.created_at else "s/f"
        lines.append(f"- Cotización {fecha}: ${int(quote.total):,} ({quote.status}).")

    notes = (
        (
            await db.execute(
                select(Note)
                .where(Note.contact_id == contact.id, Note.is_active.is_(True))
                .order_by(Note.created_at.desc())
                .limit(3)
            )
        )
        .scalars()
        .all()
    )
    for note in notes:
        fecha = note.created_at.strftime("%d/%m/%Y") if note.created_at else "s/f"
        lines.append(f"- Nota {fecha}: {note.content[:200]}")

    if not lines:
        return ""
    return (
        "\n\nCONTEXTO DEL CLIENTE (memoria del negocio; personaliza la "
        "respuesta con naturalidad, sin recitar la lista):\n" + "\n".join(lines)
    )


async def _chat_reply(
    db: AsyncSession,
    *,
    tenant: Tenant,
    conversation: Conversation,
    channel: Channel,
    wa_id: str,
    text: str,
    system_prompt: str,
    contact_id_for_usage=None,
) -> None:
    """Conversa con el LLM usando el historial y responde por el canal."""
    settings = get_settings()
    history = await _conversation_history(db, conversation.id)
    client_context = await _client_context_block(db, conversation)
    messages_payload = [
        {
            "role": "system",
            "content": system_prompt.format(
                bot_name=tenant.bot_name, tenant_name=tenant.name
            )
            + client_context,
        }
    ]
    for historical in history:
        role = "user" if historical.direction == "in" else "assistant"
        content_text = historical.content or f"[{historical.type}]"
        messages_payload.append({"role": role, "content": content_text})
    if messages_payload[-1]["role"] != "user":
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
            contact_id=contact_id_for_usage,
        )


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
    text_override: str | None = None,
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

    is_team = await _is_team_member(db, tenant=tenant, contact=contact)

    if not is_team:
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

        # Cliente conocido: atención solo si el negocio la activó
        # (por defecto el bot calla; sus respuestas alimentan el seguimiento)
        if tenant.customer_mode:
            try:
                await _chat_reply(
                    db,
                    tenant=tenant,
                    conversation=conversation,
                    channel=channel,
                    wa_id=contact.wa_id,
                    text=text_in,
                    system_prompt=_CUSTOMER_PROMPT,
                    contact_id_for_usage=contact.id,
                )
            except Exception:
                logger.exception(
                    "El modo atención al cliente falló con el mensaje %s", message.id
                )
            return

        logger.debug("Mensaje %s de un cliente del dueño: el bot calla", message.id)
        return

    # ── El dueño o su equipo le hablan al asistente ────────────────────────

    # El asistente solo atiende con el cotizador encendido (contrato del plan)
    if not await _quoter_enabled(db, tenant.id):
        return

    # Motor de disponibilidad (adendo §5): si un servicio que el dueño
    # encendió está caído/en mantenimiento, el bot lo dice con claridad.
    wa_id = contact.wa_id
    # El lote unificado (debounce) llega como text_override; si no, el propio
    text = (text_override or message.content or "").strip()

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

        # ¿Confirmación de una acción pendiente? (spec §9.1: efecto externo
        # requiere confirmación explícita del dueño)
        if intent.intention == "confirm" or intent.intention == "invoice":
            handled = await _handle_confirmation(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, text=text,
            )
            if handled:
                return
            if intent.intention == "invoice":
                await _handle_invoice(
                    db, tenant=tenant, channel=channel,
                    conversation=conversation, wa_id=wa_id, intent=intent,
                )
                return

        if intent.intention == "collection":
            await _handle_collection(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
            )
            return

        if intent.intention == "inventory":
            await _handle_inventory(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
            )
            return

        if intent.intention == "expense":
            await _handle_expense(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
            )
            return

        if intent.intention == "warranty":
            await _handle_warranty(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
            )
            return

        if intent.intention == "maintenance":
            await _handle_maintenance(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
            )
            return

        if intent.intention == "visit_report":
            await _handle_visit_report(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
            )
            return

        if intent.intention == "note":
            usable, why = await _module_usable(db, tenant=tenant, module_key="voice_notes")
            if not usable and why:
                await _send_out_message(
                    db, tenant_id=tenant.id, conversation=conversation,
                    channel=channel, wa_id=wa_id, text=f"⚠️ {why}. Te aviso cuando vuelva.",
                )
                return
            await _handle_note(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, text=text,
            )
            return

        if intent.intention == "reminder":
            usable, why = await _module_usable(db, tenant=tenant, module_key="reminders")
            if not usable and why:
                await _send_out_message(
                    db, tenant_id=tenant.id, conversation=conversation,
                    channel=channel, wa_id=wa_id, text=f"⚠️ {why}. Te aviso cuando vuelva.",
                )
                return
            await _handle_reminder(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
            )
            return

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
            usable, why = await _module_usable(db, tenant=tenant, module_key="quoter")
            if not usable and why:
                await _send_out_message(
                    db, tenant_id=tenant.id, conversation=conversation,
                    channel=channel, wa_id=wa_id, text=f"⚠️ {why}. Te aviso cuando vuelva.",
                )
                return
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
        await _chat_reply(
            db,
            tenant=tenant,
            conversation=conversation,
            channel=channel,
            wa_id=wa_id,
            text=text,
            system_prompt=_SYSTEM_PROMPT,
            contact_id_for_usage=contact.id,
        )
        # Si el dueño escribió por audio, responder también con voz
        # (spec §12: las cifras SIEMPRE van también en texto primero)
        if message.type == "audio" and text:
            await _send_voice_reply(
                db, tenant=tenant, conversation=conversation,
                channel=channel, wa_id=wa_id,
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
