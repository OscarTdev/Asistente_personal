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
import re
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
from app.services import google_handlers
from app.services import onboarding as onboarding_service
from app.services import pdf_generator as pdf_service
from app.services import quotes as quotes_service
from app.services.chat_utils import (
    resolve_contact_by_name as _resolve_contact_by_name,
)
from app.services.chat_utils import (
    send_out_message as _send_out_message,
)
from app.services.documents import get_branding
from app.services.formatting import format_cop as _format_cop
from app.services.invoice_pdf import generate_invoice_pdf
from app.services.usage import log_service_usage

logger = logging.getLogger(__name__)

_PANEL_NAME_RE = re.compile(
    r"\b(admin|administrador|panel|plataforma)\b", re.IGNORECASE
)
_PANEL_ACTION_RE = re.compile(
    r"\b(entrar|acceder|acceso|ingresar|link|enlace|pásame|pasame|dame|"
    r"cómo entro|como entro)\b",
    re.IGNORECASE,
)
_GOOGLE_CONNECT_RE = re.compile(
    r"\b(conectar|conecta|vincular|vincula|autorizar|autoriza|integrar|"
    r"integra)\b.{0,30}\b(google|gmail|calendar|calendario)\b"
    r"|\b(google|gmail|calendar|calendario)\b.{0,30}\b(conectar|vincular|"
    r"autorizar|integrar)\b",
    re.IGNORECASE,
)


def _requests_panel_access(text: str) -> bool:
    normalized = text.strip()
    return bool(
        _PANEL_NAME_RE.search(normalized) and _PANEL_ACTION_RE.search(normalized)
    )


def _requests_google_connection(text: str) -> bool:
    return bool(_GOOGLE_CONNECT_RE.search(text.strip()))


async def _handle_panel_access(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
) -> None:
    from app.services.onboarding import panel_access_message

    await _send_out_message(
        db,
        tenant_id=tenant.id,
        conversation=conversation,
        channel=channel,
        wa_id=wa_id,
        text=await panel_access_message(db, tenant=tenant),
    )


async def _handle_google_connection(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
) -> None:
    from app.services import google_oauth

    if not google_oauth.google_configured():
        text = (
            "Google todavía no está habilitado en la plataforma. "
            "Avísame cuando el administrador termine la configuración."
        )
    else:
        state = google_oauth.build_state_token(tenant.id)
        url = google_oauth.build_authorization_url(state)
        text = (
            f"🔗 Autoriza Google para {tenant.bot_name or 'Aura'} desde aquí:\n"
            f"{url}\n\n"
            "El enlace vence en 10 minutos. En la ventana de Google elige "
            "tu cuenta y acepta los permisos; luego volverás al panel."
        )
    await _send_out_message(
        db,
        tenant_id=tenant.id,
        conversation=conversation,
        channel=channel,
        wa_id=wa_id,
        text=text,
    )


async def _load_logo_bytes(db: AsyncSession, tenant_id: UUID) -> bytes | None:
    """Logo actual del tenant para los encabezados de PDF (None si no hay)."""
    from app.models import TenantBranding

    branding = (
        await db.execute(
            select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    return branding.logo_bytes if branding else None


_SYSTEM_PROMPT = (
    "Eres {bot_name}, el asistente personal de WhatsApp de "
    "{tenant_name}, un negocio de oficios en Colombia. Le hablas al DUEÑO del "
    "negocio: es tu jefe.\n\n"
    "QUÉ PUEDES HACER (tienes acceso REAL a los datos del negocio):\n"
    "- Cotizar con el catálogo de precios del negocio y generar el PDF "
    "(COT-0001).\n"
    "- Recordatorios: crearlos, listarlos («qué recordatorios tengo») y "
    "cancelarlos («cancela el recordatorio de X»).\n"
    "- Notas por texto o voz, buscarlas y borrarlas.\n"
    "- Contactos del negocio (CRM): SÍ tienes acceso — puedes buscarlos y "
    "escribirles de su parte.\n"
    "- Ver historial de conversaciones: «historial con Juan», «qué hablé con "
    "María», «últimas conversaciones».\n"
    "- Cuentas de cobro (CC), cobros con link de MercadoPago, informes de "
    "visita (IV), garantías, mantenimientos preventivos, bitácora de obra, "
    "gastos, inventario y rentabilidad por obra.\n"
    "- Finanzas personales: registra ingresos («cobré 500 mil a Juliana») "
    "y gastos («gasté 45 mil en cable»), y consulta tu cartera "
    "(«cuánto tengo»).\n"
    "- Buscar en internet: si te piden información externa (precios del "
    "mercado, horarios, normatividad, qué hay en una página), diles que "
    "escriban «busca en internet [tema]» o pásales el enlace y lo abres.\n"
    "- Google (si el dueño conectó su cuenta): su correo, su agenda, hojas "
    "de cálculo e informes en Docs.\n\n"
    "CÓMO RESPONDES:\n"
    "- SIEMPRE en español colombiano: cálido, breve, estilo WhatsApp "
    "(1-3 líneas).\n"
    "- NUNCA muestres tu razonamiento interno: responde directo al "
    "dueño, su mensaje va tal cual a WhatsApp.\n"
    "- Una sola pregunta a la vez.\n"
    "- NUNCA inventes precios ni promesas: los precios salen del catálogo.\n"
    "- Si te preguntan qué puedes hacer o quién eres, responde natural con "
    "un resumen breve (4-6 líneas) de la lista de arriba.\n"
    "- Si te preguntan si tienes acceso a algo (contactos, correo, agenda, "
    "historial), responde con la verdad según la lista.\n"
    "- Si el dueño te corrige (ej: «me llamo Oscar»), discúlpate una vez, "
    "breve, y usa el nombre correcto en adelante.\n"
    "- No ofrezcas servicios que no existen; si piden algo fuera de tu "
    "alcance, dilo claro y ofrece tomarle el mensaje."
)

_CUSTOMER_PROMPT = (
    "Eres {bot_name}, el asistente de WhatsApp de {tenant_name} "
    "(negocio de oficios en Colombia).\n"
    "Atiendes a los clientes del negocio: mensajes cortos, cálidos y "
    "profesionales.\n\n"
    "REGLAS:\n"
    "- Responde SIEMPRE en español, tono cercano, estilo WhatsApp: una sola "
    "pregunta o idea por mensaje.\n"
    "- NUNCA inventes precios, plazos ni promesas: los precios salen del "
    "catálogo del negocio y solo se comparten en una cotización formal.\n"
    "- Si no sabes algo, si el cliente se queja o pide algo delicado, dile "
    "con naturalidad que lo conectas con el dueño y avísale por dentro.\n"
    "- No menciones datos de otros clientes ni asumas información que no te "
    "dieron.\n"
    "- Aclara que eres un asistente automático si te lo preguntan."
)


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


async def _handle_conversation_log(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """El dueño pide ver el historial de conversaciones con un contacto
    o listar sus conversaciones recientes."""
    from app.services.chat_utils import _resolve_contact_by_name

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db,
            tenant_id=tenant.id,
            conversation=conversation,
            channel=channel,
            wa_id=wa_id,
            text=msg,
        )

    name = (intent.contact_name or "").strip()

    if name:
        # Historial con un contacto específico
        matches = await _resolve_contact_by_name(db, tenant_id=tenant.id, name=name)
        if not matches:
            await tell_owner(f"No encontré a nadie llamado «{name}» en tus contactos.")
            return
        if len(matches) > 1:
            names = ", ".join(c.name or c.wa_id for c in matches[:5])
            await tell_owner(f"Encontré varios: {names}. ¿Con cuál quieres ver el historial?")
            return

        target = matches[0]
        # Buscar la conversación más reciente con ese contacto
        target_conv = (
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

        if not target_conv:
            await tell_owner(f"Todavía no hay conversación con {target.name or target.wa_id}.")
            return

        messages = await _conversation_history(db, target_conv.id, limit=15)
        if not messages:
            await tell_owner(f"La conversación con {target.name or target.wa_id} está vacía.")
            return

        # Formatear historial
        lines = [f"💬 Historial con {target.name or target.wa_id} (últimos {len(messages)}):"]
        for m in messages:
            prefix = "👤" if m.direction == "in" else "🤖"
            content = m.content or "<archivo>"
            if len(content) > 120:
                content = content[:117] + "..."
            lines.append(f"{prefix} {content}")

        await tell_owner("\n".join(lines))
    else:
        # Listar últimas conversaciones del negocio
        convs = (
            await db.execute(
                select(Conversation)
                .where(Conversation.tenant_id == tenant.id)
                .order_by(
                    Conversation.last_message_at.desc().nullslast(),
                    Conversation.id.desc(),
                )
                .limit(10)
            )
        ).scalars().all()

        if not convs:
            await tell_owner("Todavía no tienes conversaciones registradas.")
            return

        # Obtener nombres de contactos
        contact_ids = [c.contact_id for c in convs]
        contacts = (
            await db.execute(
                select(Contact).where(Contact.id.in_(contact_ids))
            )
        ).scalars().all()
        contacts_by_id = {c.id: c for c in contacts}

        lines = ["📋 Tus últimas conversaciones:"]
        for c in convs:
            contact = contacts_by_id.get(c.contact_id)
            cname = contact.name if contact else contact.wa_id if contact else "Desconocido"
            status_emoji = "🟢" if c.status == "open" else "⚪"
            last = f" · {c.last_message_at.strftime('%d/%m %H:%M')}" if c.last_message_at else ""
            lines.append(f"{status_emoji} {cname}{last}")

        await tell_owner("\n".join(lines))


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
            "Si es nuevo, agrégalo con "
            "«agrega a [nombre] con número [celular]» y luego le escribo."
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
    text: str = "",
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
    text_lower = " ".join(
        p for p in (text, intent.message_text) if p
    ).lower()
    query_words = (
        "qué mantenimientos", "que mantenimientos", "mis mantenimientos",
        "mantenimientos tengo", "qué mantenimientos tengo",
    )
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
    text: str = "",
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

    text_lower = " ".join(
        p for p in (text, intent.message_text) if p
    ).lower()
    query_words = (
        "qué garantías", "que garantías", "mis garantías",
        "garantías vigentes", "garantias vigentes",
        "que garantias", "mis garantias", "garantias tengo",
        "garantías tengo", "qué garantias",
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


async def _handle_site_log(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
    text: str = "",
) -> None:
    """Bitácora de obra: abrir, registrar avance, consultar y cerrar (spec §13).

    «abre obra para Juliana: instalación de tomacorrientes»
    «registro: se instalaron 5 tomacorrientes, falta el tablero»
    «qué obras tengo abiertas»
    «cierra la obra de Juliana»
    """
    from app.services.site_log import (
        active_sites,
        add_entry,
        close_site,
        entries_of_site,
        find_site_for_contact,
        open_site,
    )

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    text_lower = " ".join(
        p for p in (text, intent.message_text) if p
    ).lower()

    # Consultar obras abiertas
    open_words = ("qué obras", "que obras", "mis obras", "obras abiertas")
    if any(w in text_lower for w in open_words):
        sites = await active_sites(db, tenant_id=tenant.id)
        if not sites:
            await tell_owner(
                "🏗️ No tienes obras abiertas. "
                "Dime «abre obra para [cliente]: [qué]»."
            )
            return
        lines = ["🏗️ Tus obras abiertas:\n"]
        for site in sites:
            contact = (
                await db.execute(select(Contact).where(Contact.id == site.contact_id))
            ).scalar_one_or_none()
            name = contact.name if contact else "—"
            entries = await entries_of_site(db, site_id=site.id)
            lines.append(f"• {site.title[:60]} — {name} ({len(entries)} registros)")
        await tell_owner("\n".join(lines))
        return

    # Cerrar obra
    close_words = ("cierra", "cerrar", "termina", "terminar", "finaliza", "ya terminé")
    if any(w in text_lower for w in close_words) and intent.contact_name:
        matches = await _resolve_contact_by_name(
            db, tenant_id=tenant.id, name=intent.contact_name
        )
        if len(matches) == 1:
            site = await find_site_for_contact(
                db, tenant_id=tenant.id, contact_id=matches[0].id
            )
            if site:
                await close_site(db, site_id=site.id)
                await tell_owner(f"✅ Obra «{site.title[:50]}» cerrada.")
            else:
                await tell_owner("No encontré una obra abierta para ese cliente.")
        else:
            await tell_owner("No encontré a ese cliente.")
        return

    # Registrar avance (necesita obra abierta)
    register_words = (
        "registro", "avance", "avanzamos",
        "se hizo", "se instaló", "instalé", "trabajé",
    )
    if any(w in text_lower for w in register_words):
        note = (intent.message_text or intent.description or "").strip()
        if not note:
            await tell_owner("¿Qué quieres registrar? (ej: se instalaron 5 tomacorrientes)")
            return

        # Buscar la obra más reciente abierta (del dueño o del cliente mencionado)
        if intent.contact_name:
            matches = await _resolve_contact_by_name(
                db, tenant_id=tenant.id, name=intent.contact_name
            )
            if len(matches) == 1:
                site = await find_site_for_contact(
                    db, tenant_id=tenant.id, contact_id=matches[0].id
                )
                if site:
                    await add_entry(db, site_id=site.id, note=note)
                    count = len(await entries_of_site(db, site_id=site.id))
                    await tell_owner(
                        f"📝 Registrado en «{site.title[:50]}» ({count} entradas)."
                    )
                    return

        # Sin cliente específico: buscar la obra más reciente
        sites = await active_sites(db, tenant_id=tenant.id)
        if sites:
            site = sites[0]
            await add_entry(db, site_id=site.id, note=note)
            count = len(await entries_of_site(db, site_id=site.id))
            await tell_owner(
                f"📝 Registrado en «{site.title[:50]}» ({count} entradas)."
            )
        else:
            await tell_owner(
                "No tienes obras abiertas. "
                "Dime «abre obra» primero."
            )
        return

    # Abrir obra
    if intent.contact_name and intent.description:
        matches = await _resolve_contact_by_name(
            db, tenant_id=tenant.id, name=intent.contact_name
        )
        if len(matches) != 1:
            await tell_owner(f"No encontré a «{intent.contact_name}» en tus contactos.")
            return
        site = await open_site(
            db, tenant_id=tenant.id,
            contact_id=matches[0].id,
            title=intent.description,
        )
        await tell_owner(
            f"🏗️ Obra abierta: «{site.title[:50]}» para "
            f"{matches[0].name or matches[0].wa_id}. "
            "Registra avances con «registro: [qué pasó hoy]»."
        )
    else:
        await tell_owner(
            "¿Para qué cliente y qué obra? "
            "(ej: «abre obra para Juliana: instalación de tomacorrientes»)"
        )


async def _handle_profitability(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """Rentabilidad: cotizado vs gastos reales de un trabajo (spec §13).

    «rentabilidad del trabajo de Juliana» → cotización vs gastos.
    """
    from decimal import Decimal as D

    from sqlalchemy import func

    from app.models import Expense, Quote

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    if not intent.contact_name:
        await tell_owner("¿De qué cliente? Dime el nombre (ej: rentabilidad de Juliana).")
        return

    matches = await _resolve_contact_by_name(
        db, tenant_id=tenant.id, name=intent.contact_name
    )
    if len(matches) != 1:
        await tell_owner(f"No encontré a «{intent.contact_name}».")
        return
    target = matches[0]

    # Buscar cotizaciones de este cliente
    quotes = list(
        (
            await db.execute(
                select(Quote)
                .where(
                    Quote.tenant_id == tenant.id,
                    Quote.contact_id == target.id,
                    Quote.status.in_(["sent", "accepted"]),
                )
                .order_by(Quote.created_at.desc())
                .limit(5)
            )
        ).scalars().all()
    )

    if not quotes:
        await tell_owner(
            f"No encontré cotizaciones enviadas o aceptadas para "
            f"{target.name or target.wa_id}."
        )
        return

    # Sumar gastos del mes para este tenant (materiales relacionados)
    total_quoted = sum((q.total or D("0")) for q in quotes)
    total_expenses = (
        await db.execute(
            select(func.sum(Expense.amount)).where(
                Expense.tenant_id == tenant.id,
                Expense.type == "expense",
            )
        )
    ).scalar() or D("0")

    # Calcular rentabilidad estimada
    profit = total_quoted - total_expenses
    margin = (float(profit) / float(total_quoted) * 100) if total_quoted else 0

    await tell_owner(
        f"💰 Rentabilidad de {target.name or target.wa_id}:\n\n"
        f"Cotizado: {_format_cop(total_quoted)}\n"
        f"Gastos totales (materiales): {_format_cop(total_expenses)}\n"
        f"Ganancia: {_format_cop(profit) if profit > 0 else '-' + _format_cop(abs(profit))} "
        f"({margin:.0f}% margen)"
    )


async def _handle_inventory(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
    text: str = "",
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

    text_lower = " ".join(
        p for p in (text, intent.message_text) if p
    ).lower()

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
    text: str = "",
) -> None:
    """Finanzas personales: ingresos, gastos y cartera (spec §13 + adendo).

    «gasté 45 mil en cable» → gasto con categoría auto-detectada
    «cobré 500 mil a Juliana» → ingreso
    «cuánto he gastado este mes» → resumen de gastos por categoría
    «cuánto tengo» / «mi cartera» / «balance» → balance de cartera
    """
    from app.services.expenses import (
        _format_cop,
        get_wallet_balance,
        monthly_summary,
        record_income,
        record_movement,
    )

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    # ¿Consulta de cartera / balance? (mensaje original o extraído)
    text_lower = " ".join(
        part for part in (text, intent.message_text) if part
    ).lower()
    wallet_words = (
        "cuánto tengo", "cuanto tengo", "mi cartera", "balance",
        "cuánto hay en mi cartera", "mi balance", "cuánto es mi cartera",
    )
    if any(w in text_lower for w in wallet_words):
        wallet = await get_wallet_balance(db, tenant_id=tenant.id)
        await tell_owner(
            f"💰 Cartera:\n"
            f"Ingresos: {_format_cop(wallet['total_income'])}\n"
            f"Gastos: {_format_cop(wallet['total_expenses'])}\n"
            f"Balance: {_format_cop(wallet['balance'])}"
        )
        return

    # ¿Consulta de gastos del mes?
    query_words = (
        "cuánto he gastado", "cuanto he gastado", "resumen de gastos",
        "mis gastos", "cuánto he gastado este mes", "resumen del mes",
        "cuanto he gastado este mes", "gastos del mes",
    )
    if any(w in text_lower for w in query_words):
        summary = await monthly_summary(db, tenant_id=tenant.id)
        if summary["total"] == 0 and summary["total_income"] == 0:
            await tell_owner(
                "No tienes movimientos este mes. "
                "Dime «gasté [monto] en [qué]» o «cobré [monto]»."
            )
            return

        lines = [f"📊 Finanzas de {summary['month']}:\n"]
        if summary["total_income"] > 0:
            lines.append(f"INGRESOS: {_format_cop(summary['total_income'])}")
        if summary["total"] > 0:
            lines.append(f"GASTOS: {_format_cop(summary['total'])}")
        lines.append(f"NETO: {_format_cop(summary['net'])}\n")
        if summary["categories"]:
            lines.append("Gastos por categoría:")
            for category, data in summary["categories"].items():
                lines.append(
                    f"• {category.title()}: {_format_cop(data['total'])} "
                    f"({data['count']} gasto{'s' if data['count'] > 1 else ''})"
                )
        await tell_owner("\n".join(lines))
        return

    # Registrar movimiento (ingreso o gasto)
    if intent.amount is None or intent.amount <= 0:
        await tell_owner("¿Cuánto? Dime el monto (ej: 45000)")
        return

    from decimal import Decimal as D

    amount = D(str(int(intent.amount)))

    # ¿Ingreso o gasto? El router de intención no lo distingue:
    # se detecta con el mensaje ORIGINAL del dueño (no solo el
    # description extraído, que puede perder palabras clave).
    from app.services.expenses import detect_type
    full_text = " ".join(
        part for part in (text, intent.description, intent.message_text) if part
    )
    mov_type = detect_type(full_text)

    if mov_type == "income":
        description = (intent.description or "Ingreso").strip()
        if not description or description == "Ingreso":
            description = (intent.message_text or "Ingreso").strip()[:200]
        expense = await record_income(
            db, tenant_id=tenant.id,
            description=description,
            amount=amount,
        )
        await tell_owner(
            f"💵 Ingreso registrado: {_format_cop(amount)} en "
            f"**{expense.category}**\n\n{description}"
        )
        return

    description = (intent.description or "Gasto").strip()
    if not description or description == "Gasto":
        await tell_owner("¿En qué lo gastaste? (ej: cable, gasolina, almuerzo)")
        return

    expense = await record_movement(
        db, tenant_id=tenant.id,
        description=description,
        amount=amount,
        mov_type="expense",
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
        await notes_service.sync_note_to_google(db, note)
        if note.google_sync_status == "synced":
            await tell_owner(
                f"📝 Anotado y guardado en Google {note.google_provider}: "
                f"«{note.content}»\n{note.google_url}"
            )
        elif note.google_sync_status == "auth_error":
            await tell_owner(
                f"📝 Anotado localmente: «{note.content}»\n"
                "Tu conexión de Google necesita reconectarse desde el panel."
            )
        else:
            await tell_owner(f"📝 Anotado localmente: «{note.content}»")

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
    text: str = "",
) -> None:
    """Recordatorios: crear, listar («qué tengo pendiente») y cancelar.

    «recuérdame llamar a Juliana el jueves» → crear.
    «cuándo me recordarás?» / «qué recordatorios tengo» → listar.
    «cancela el recordatorio de la cita» / «elimina ese recordatorio» → cancelar.
    """
    import re
    from datetime import datetime as dt
    from datetime import timedelta

    from app.models import Reminder
    from app.services import notes as notes_service
    from app.services.time_window import to_colombia

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    async def pending_reminders() -> list[Reminder]:
        return list(
            (
                await db.execute(
                    select(Reminder)
                    .where(
                        Reminder.tenant_id == tenant.id,
                        Reminder.status == "pending",
                    )
                    .order_by(Reminder.remind_at.asc())
                )
            ).scalars().all()
        )

    async def list_reminders() -> None:
        pendings = await pending_reminders()
        if not pendings:
            await tell_owner(
                "🔕 No tienes recordatorios pendientes. Dime "
                "«recuérdame X el día Y» y lo apunto."
            )
            return
        lines = ["⏰ Tus recordatorios pendientes:\n"]
        for r in pendings:
            cuando = to_colombia(r.remind_at).strftime("%d/%m %I:%M %p")
            lines.append(f"• {cuando} — {r.content[:60]}")
        lines.append("\nPara cancelar uno: «cancela el recordatorio de [qué]».")
        await tell_owner("\n".join(lines))

    text_lower = (text or "").strip().lower()

    # Cancelar: «cancela/elimina/borra ese recordatorio [de X]»
    cancel_match = re.search(r"\b(cancel\w*|elimin\w*|borr\w*|quita\w*)\b", text_lower)
    if cancel_match and "recordatorio" in text_lower:
        pendings = await pending_reminders()
        if not pendings:
            await tell_owner("🔕 No tienes recordatorios pendientes por cancelar.")
            return
        # El router pudo poner el objetivo en message_text/description;
        # si dice «ese» (o no especifica) y solo hay uno, se cancela ese.
        objetivo = (
            (intent.message_text or intent.description or "").strip().lower()
        )
        objetivo = re.sub(r"^(cancel\w*|elimin\w*|borr\w*|quita\w*)\s+", "", objetivo)
        objetivo = re.sub(r"\b(el|la|ese|esa|de|del)\b", " ", objetivo).strip()
        elegido: Reminder | None = None
        if objetivo and objetivo not in ("ese", "esa", "este"):
            for r in pendings:
                if objetivo[:12] in r.content.lower():
                    elegido = r
                    break
        elif len(pendings) == 1:
            elegido = pendings[0]
        if elegido is None:
            await list_reminders()
            await tell_owner("¿Cuál de estos cancelo?")
            return
        await notes_service.set_reminder_status(
            db,
            tenant_id=tenant.id,
            reminder_id=elegido.id,
            status="cancelled",
        )
        await tell_owner(f"🗑️ Cancelado: «{elegido.content[:60]}».")
        return

    # Completar: «ya quedó», «listo», «hecho» sobre un recordatorio.
    complete_match = re.search(
        r"\b(listo|hecho|terminad\w*|complet\w*|ya qued[oó])\b", text_lower
    )
    if complete_match and ("recordatorio" in text_lower or not intent.remind_at):
        pendings = await pending_reminders()
        objetivo = (intent.message_text or intent.description or "").strip().lower()
        elegido = None
        if objetivo:
            elegido = next(
                (r for r in pendings if objetivo[:12] in r.content.lower()), None
            )
        elif len(pendings) == 1:
            elegido = pendings[0]
        if elegido is None:
            await list_reminders()
            await tell_owner("¿Cuál de estos recordatorios ya quedó listo?")
            return
        await notes_service.set_reminder_status(
            db,
            tenant_id=tenant.id,
            reminder_id=elegido.id,
            status="done",
        )
        await tell_owner(f"✅ Marcado como listo: «{elegido.content[:60]}».")
        return

    postpone_match = re.search(
        r"\b(aplaz\w*|pospon\w*|reprogram\w*|más tarde|mas tarde)\b",
        text_lower,
    )
    if postpone_match:
        pendings = await pending_reminders()
        objetivo = (intent.message_text or intent.description or "").strip().lower()
        elegido = next(
            (r for r in pendings if objetivo and objetivo[:12] in r.content.lower()),
            None,
        )
        if elegido is None and len(pendings) == 1:
            elegido = pendings[0]
        if elegido is None or not intent.remind_at:
            await list_reminders()
            await tell_owner(
                "Dime cuál aplazar y para cuándo, por ejemplo: "
                "«aplaza la llamada para mañana a las 9»."
            )
            return
        try:
            new_time = dt.fromisoformat(intent.remind_at)
            if new_time.tzinfo is None:
                new_time = (new_time + timedelta(hours=5)).replace(tzinfo=UTC)
        except ValueError:
            await tell_owner("No entendí la nueva fecha. ¿Para cuándo lo aplazo?")
            return
        await notes_service.reschedule_reminder(
            db,
            tenant_id=tenant.id,
            reminder_id=elegido.id,
            remind_at=new_time,
        )
        when = to_colombia(new_time).strftime("%d/%m a las %I:%M %p")
        await tell_owner(f"🔁 Aplazado: «{elegido.content[:60]}» para el {when}.")
        return

    # Consultar: pregunta sobre recordatorios SIN contenido nuevo que crear
    content = (intent.message_text or "").strip()
    if not content:
        content = (intent.description or "").strip()
    pregunta = (
        not content
        or any(
            p in text_lower
            for p in (
                "cuándo me", "cuando me", "qué recordatorios",
                "que recordatorios", "mis recordatorios", "tengo pendiente",
            )
        )
    ) and not intent.remind_at
    if pregunta:
        await list_reminders()
        return

    if not content:
        await tell_owner("¿Qué quieres que te recuerde?")
        return

    # Parsear la fecha del intent (ISO 8601) o usar +1 día como default.
    # Fecha sin zona = HORA COLOMBIA (UTC-5): «a las 2 pm» es 19:00 UTC,
    # no 14:00 UTC (bug que disparaba recordatorios 5 horas temprano).
    remind_at = None
    if intent.remind_at:
        try:
            remind_at = dt.fromisoformat(intent.remind_at)
            if remind_at.tzinfo is None:
                remind_at = (remind_at + timedelta(hours=5)).replace(tzinfo=UTC)
        except ValueError:
            pass
    if remind_at is None:
        # Default: mañana a las 8:00 AM Colombia
        now_col = datetime.now(UTC) - timedelta(hours=5)
        tomorrow_col = (now_col + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )
        remind_at = tomorrow_col + timedelta(hours=5)

    reminder = await notes_service.save_reminder(
        db, tenant_id=tenant.id, content=content, remind_at=remind_at
    )
    await notes_service.sync_reminder_to_google(db, reminder)
    # Formatear la fecha para mostrar (hora Colombia = UTC-5)
    when = to_colombia(remind_at).strftime("%d/%m a las %I:%M %p")
    if reminder.google_sync_status == "synced":
        await tell_owner(
            f"⏰ Listo: te recordaré «{content}» el {when} por WhatsApp "
            f"y Google Calendar."
        )
    else:
        await tell_owner(f"⏰ Listo: te recordaré «{content}» el {when} por WhatsApp.")


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
    import re
    from datetime import timedelta

    # Una confirmación vieja no debe dispararse con un «ok» casual días después
    if pending.created_at and (
        datetime.now(UTC) - pending.created_at > timedelta(hours=24)
    ):
        pending.status = "expired"
        await db.commit()
        return False

    # Palabras completas: «no» no debe activarse dentro de «nota» o «número»
    tokens = set(re.findall(r"[a-záéíóúñü]+", lowered))
    yes_words = ("si", "sí", "dale", "ok", "claro", "envía", "envia",
                 "mánda", "manda", "confirmo", "listo", "seguro", "puedes")
    no_words = ("no", "después", "despues", "luego", "cancela", "espera", "nuevo")

    if tokens & set(no_words):
        pending.status = "cancelled"
        await db.commit()
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id,
            text="Entendido, no la envío. Dime si necesitas algo más.",
        )
        return True

    if tokens & set(yes_words):
        pending.status = "confirmed"
        await db.commit()

        if pending.action_type == "send_quote":
            payload = pending.payload
            quote_id = UUID(payload["quote_id"])
            contact_id = UUID(payload["contact_id"])

            quote = (
                await db.execute(
                    select(Quote).where(
                        Quote.id == quote_id, Quote.tenant_id == tenant.id
                    )
                )
            ).scalar_one_or_none()
            target_contact = (
                await db.execute(
                    select(Contact).where(
                        Contact.id == contact_id, Contact.tenant_id == tenant.id
                    )
                )
            ).scalar_one_or_none()
            if quote is None or target_contact is None:
                pending.status = "failed"
                await db.commit()
                await _send_out_message(
                    db, tenant_id=tenant.id, conversation=conversation,
                    channel=channel, wa_id=wa_id,
                    text=(
                        "No pude enviar la cotización: ya no encuentro la "
                        "cotización o el contacto. Revísalo en el panel."
                    ),
                )
                return True

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
                    select(Contact).where(Contact.id == contact_id, Contact.tenant_id == tenant.id)
                )
            ).scalar_one_or_none()
            if target_contact is None:
                return False

            doc = (
                await db.execute(
                    select(Document).where(
                        Document.tenant_id == tenant.id,
                        Document.doc_type == "invoice",
                        Document.number == doc_number,
                    )
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

        if pending.action_type == "send_email":
            # El envío desde la cuenta Google del dueño vive con su módulo
            return await google_handlers.confirm_send_email(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, pending=pending,
            )

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


async def _handle_support(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """Maneja solicitudes de soporte: reenvía el mensaje al admin de la plataforma."""
    from app.core.config import get_settings

    settings = get_settings()
    admin_wa_id = getattr(settings, 'admin_support_wa_id', None) or "3043223100"

    # Mensaje para el admin
    support_msg = (
        f"🆘 *SOPORTE - {tenant.name}*\n"
        f"Negocio: {tenant.name} (slug: {tenant.slug})\n"
        f"Dueño WhatsApp: {wa_id}\n"
        f"Plan: {tenant.plan}\n"
        f"Motivo: {intent.message_text or '(sin detalles)'}"
    )

    try:
        await channel.send_text(admin_wa_id, support_msg)
    except Exception:
        logger.exception("No se pudo enviar mensaje de soporte al admin")

    # Confirmar al dueño
    await _send_out_message(
        db,
        tenant_id=tenant.id,
        conversation=conversation,
        channel=channel,
        wa_id=wa_id,
        text="✅ Tu solicitud de soporte ha sido enviada al equipo. Te contactaremos pronto.",
    )

    logger.info("Soporte enviado al admin para tenant %s", tenant.id)


# ── Gestión de servicios por chat ──────────────────────────────────────────


async def _handle_manage_services(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
    text: str = "",
) -> None:
    """Gestiona servicios del tenant: listar, activar, desactivar.

    El dueño dice: "activa recordatorios", "desactiva cobro de cartera",
    "qué servicios tengo", "lista mis servicios".
    """
    from app.core.modules_registry import (
        AVAILABLE_MODULES,
        MODULES_BY_KEY,
        module_dev_status,
        module_parent,
    )
    from app.services.entitlements import module_allowed

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    # Obtener módulos ya creados para este tenant
    existing = {
        tm.module_key: tm
        for tm in (
            await db.execute(
                select(TenantModule).where(TenantModule.tenant_id == tenant.id)
            )
        ).scalars()
    }

    # Acción: enable / disable / list
    action = (intent.message_text or "").strip().lower()
    service_name = (intent.description or intent.contact_name or "").strip().lower()

    # Normalizar nombres comunes a keys
    name_to_key = {
        "cotizador": "quoter",
        "cotizaciones": "quoter",
        "seguimiento": "follow_up",
        "seguimiento de cotizaciones": "follow_up",
        "cobro": "collections",
        "cobro de cartera": "collections",
        "cartera": "collections",
        "informe": "visit_report",
        "informe de visita": "visit_report",
        "visita": "visit_report",
        "mantenimiento": "maintenance",
        "mantenimiento preventivo": "maintenance",
        "obra": "site_log",
        "seguimiento de obra": "site_log",
        "bitácora": "site_log",
        "inventario": "inventory",
        "materiales": "inventory",
        "rentabilidad": "profitability",
        "garantías": "warranties",
        "garantias": "warranties",
        "recordatorios": "reminders",
        "recordatorios y agenda": "reminders",
        "agenda": "reminders",
        "contactos": "crm",
        "crm": "crm",
        "clientes": "crm",
        "notas": "voice_notes",
        "notas por voz": "voice_notes",
        "voz": "voice_notes",
        "resumen diario": "daily_summary",
        "resumen": "daily_summary",
        "correo": "email_calendar",
        "calendario": "email_calendar",
        "google": "email_calendar",
        "finanzas": "personal_finance",
        "finanzas personales": "personal_finance",
        "búsqueda": "web_search",
        "buscar": "web_search",
        "internet": "web_search",
    }

    service_key = name_to_key.get(service_name, service_name)

    # Si es sub-servicio, redirigir al padre
    if service_key in module_parent:
        parent = module_parent[service_key]
        await tell_owner(
            f"Ese servicio vive dentro de **{MODULES_BY_KEY[parent]['name']}**. "
            f"Dime «activa {MODULES_BY_KEY[parent]['name'].lower()}» para usarlo."
        )
        return

    if action in ("list", "lista", "qué", "que", "ver"):
        # Listar servicios con su estado
        lines = ["📦 **Tus servicios:**\n"]
        for m in AVAILABLE_MODULES:
            if module_dev_status(m["key"]) != "active":
                continue
            tm = existing.get(m["key"])
            enabled = tm.is_enabled if tm else False
            # Verificar si el plan lo permite
            allowed = await module_allowed(db, plan=tenant.plan, module_key=m["key"])
            status = "🟢" if enabled else ("⚪" if allowed else "🔴")
            lines.append(f"{status} {m['name']}")
        lines.append("\n🟢 = activo · ⚪ = disponible (tu plan lo permite)")
        lines.append("🔴 = no incluido en tu plan")
        lines.append("\nPara activar: «activa [nombre]» · Para desactivar: «desactiva [nombre]»")
        await tell_owner("\n".join(lines))
        return

    if not service_key:
        await tell_owner(
            "¿Qué servicio? Dime el nombre: "
            "«activa recordatorios», «desactiva cobro», «qué servicios tengo»..."
        )
        return

    # Verificar que el servicio existe
    if service_key not in MODULES_BY_KEY:
        await tell_owner(
            f"No conozco el servicio «{service_name}». "
            "Dime «qué servicios tengo» para ver la lista."
        )
        return

    # Verificar si el plan lo permite
    allowed = await module_allowed(db, plan=tenant.plan, module_key=service_key)
    if not allowed:
        svc = MODULES_BY_KEY[service_key]["name"]
        await tell_owner(
            f"⚠️ **{svc}** no está incluido en tu plan **{tenant.plan}**.\n"
            "Actualiza a Premium desde el panel para desbloquearlo."
        )
        return

    if action in ("enable", "activa", "enciende", "prende", "activa"):
        # Activar
        tm = existing.get(service_key)
        if tm and tm.is_enabled:
            await tell_owner(f"✅ **{MODULES_BY_KEY[service_key]['name']}** ya está activo.")
            return
        if tm:
            tm.is_enabled = True
        else:
            m = MODULES_BY_KEY[service_key]
            db.add(TenantModule(
                tenant_id=tenant.id,
                module_key=service_key,
                name=m["name"],
                description=m["description"],
                category=m["category"],
                is_enabled=True,
            ))
        await db.commit()
        await tell_owner(
            f"✅ **{MODULES_BY_KEY[service_key]['name']}** activado. "
            "Ya puedes usarlo."
        )
        return

    if action in ("disable", "desactiva", "apaga", "apagar", "desactiva"):
        # Desactivar
        tm = existing.get(service_key)
        if tm is None or not tm.is_enabled:
            await tell_owner(f"⚪ **{MODULES_BY_KEY[service_key]['name']}** ya está inactivo.")
            return
        tm.is_enabled = False
        await db.commit()
        await tell_owner(f"⏸️ **{MODULES_BY_KEY[service_key]['name']}** desactivado.")
        return

    await tell_owner(
        "No entendí la acción. Usa: "
        "«activa [servicio]», «desactiva [servicio]» o «qué servicios tengo»."
    )


# ── Sincronizar contactos de Google ────────────────────────────────────────


async def _handle_sync_contacts(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
    text: str = "",
) -> None:
    """Sincroniza contactos de Google People API al CRM del tenant.

    «sincroniza contactos de google» / «importa mis contactos de google»
    → trae los contactos con nombre y teléfono, crea/actualiza en el CRM.
    """
    from googleapiclient.errors import HttpError

    from app.services.google_actions import _build_people_service
    from app.services.google_oauth import get_google_credentials

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    # Verificar conexión Google
    creds = await get_google_credentials(db, tenant_id=tenant.id)
    if creds is None:
        await tell_owner(
            "🔗 Aún no has conectado tu cuenta de Google. Hazlo desde "
            "el panel (Mi negocio → Conectar Google) y luego dime "
            "«sincroniza contactos de google»."
        )
        return

    await tell_owner("🔄 Sincronizando contactos de Google… esto puede tardar un momento.")

    try:
        service = _build_people_service(creds)
        # Obtener contactos con nombre y teléfono
        results = service.people().connections().list(
            resourceName="people/me",
            pageSize=500,
            personFields="names,phoneNumbers,emailAddresses",
        ).execute()

        connections = results.get("connections", [])
        if not connections:
            await tell_owner("No encontré contactos en tu cuenta de Google.")
            return

        created = 0
        updated = 0
        skipped = 0

        for person in connections:
            names = person.get("names", [])
            phones = person.get("phoneNumbers", [])
            emails = person.get("emailAddresses", [])

            if not names or not phones:
                skipped += 1
                continue

            name = names[0].get("displayName", "").strip()
            if not name:
                skipped += 1
                continue

            # Tomar el primer teléfono
            phone = phones[0].get("value", "").strip()
            if not phone:
                skipped += 1
                continue

            # Normalizar teléfono (solo dígitos)
            import re as _re
            digits = _re.sub(r"\D", "", phone)
            if len(digits) == 10:
                digits = "57" + digits
            if len(digits) < 10 or len(digits) > 15 or not digits.isdigit():
                skipped += 1
                continue

            email = emails[0].get("value", "").strip() if emails else None

            # Verificar si existe
            existing = (
                await db.execute(
                    select(Contact).where(
                        Contact.tenant_id == tenant.id,
                        Contact.wa_id == digits,
                    )
                )
            ).scalar_one_or_none()

            if existing:
                # Actualizar nombre y email si cambió
                changed = False
                if existing.name != name:
                    existing.name = name[:100]
                    changed = True
                if email and existing.email != email:
                    existing.email = email
                    changed = True
                if changed:
                    updated += 1
            else:
                # Crear nuevo
                contact = Contact(
                    tenant_id=tenant.id,
                    wa_id=digits,
                    name=name[:100],
                    email=email,
                    notes="Importado de Google Contacts",
                )
                db.add(contact)
                await db.flush()
                conv = Conversation(
                    tenant_id=tenant.id, contact_id=contact.id, status="open"
                )
                db.add(conv)
                created += 1

        await db.commit()

        msg = "✅ **Sincronización completa**\n\n"
        if created:
            msg += f"🆕 {created} contactos nuevos\n"
        if updated:
            msg += f"🔄 {updated} contactos actualizados\n"
        if skipped:
            msg += f"⏭️ {skipped} sin teléfono válido\n"
        msg += "\nYa puedes escribirles: «escribe a [nombre] hola»"
        await tell_owner(msg)

    except HttpError as e:
        if e.resp.status == 401 or e.resp.status == 403:
            await tell_owner(
                "⚠️ Tu conexión con Google expiró. Reconéctala desde el "
                "panel (Mi negocio → Conectar Google) e intenta de nuevo."
            )
        else:
            logger.exception("Error sincronizando contactos de Google")
            await tell_owner("⚠️ No pude sincronizar. Intenta de nuevo en un momento.")
    except Exception:
        logger.exception("Error inesperado sincronizando contactos")
        await tell_owner("⚠️ Error inesperado. Intenta de nuevo.")


# ── CRM: agregar contactos por chat ────────────────────────────────────────


async def _handle_add_contact(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
    text: str = "",
) -> None:
    """Agrega un contacto al CRM del dueño por chat (adendo §3.4).

    «agrega a Juliana con número 573001234567» → crea el contacto con
    su conversación y confirma. El número se normaliza a wa_id (solo
    dígitos, con 57 de Colombia si faltaba).
    """
    import re as _re

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    name = (intent.contact_name or "").strip()
    raw_phone = (intent.contact_phone or "").strip()

    # Si el router no extrajo el teléfono, buscarlo en el texto original
    if not raw_phone:
        match = _re.search(r"(\+?[\d][\d\s\-().]{8,17}\d)", text or "")
        if match:
            raw_phone = match.group(1)

    if not name:
        await tell_owner(
            "¿Cómo se llama el contacto? Dime "
            "«agrega a [nombre] con número [celular]»."
        )
        return

    # Normalizar: solo dígitos. 10 dígitos → antepone 57 (Colombia).
    digits = _re.sub(r"\D", "", raw_phone)
    if len(digits) == 10:
        digits = "57" + digits
    if len(digits) < 10 or len(digits) > 15 or not digits.isdigit():
        await tell_owner(
            f"El número de {name} no me parece un celular válido. "
            "Envíamelo así: «agrega a Juliana 3001234567»."
        )
        return

    # ¿Ya existe ese número para el tenant?
    existing = (
        await db.execute(
            select(Contact).where(
                Contact.tenant_id == tenant.id,
                Contact.wa_id == digits,
            )
        )
    ).scalar_one_or_none()
    if existing:
        await tell_owner(
            f"Ya tienes a {existing.name or existing.wa_id} con ese número "
            f"({digits}). Si es otra persona, pásame otro celular."
        )
        return

    # Crear contacto + conversación
    contact = Contact(
        tenant_id=tenant.id,
        wa_id=digits,
        name=name[:100],
        notes=(intent.description or "").strip()[:500] or None,
    )
    db.add(contact)
    await db.flush()
    conv = Conversation(
        tenant_id=tenant.id, contact_id=contact.id, status="open"
    )
    db.add(conv)
    await db.commit()

    await tell_owner(
        f"📇 Listo: **{name}** quedó guardad@ en el CRM con el "
        f"número **{digits}**.\n\n¿Quieres agregarle correo, dirección "
        "o una nota (ej: «cliente obra San Diego»)?"
    )
    logger.info("Contacto %s creado por chat (tenant %s)", name, tenant.id)


# ── CRM: editar contacto por chat ──────────────────────────────────────────


async def _handle_edit_contact(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
    text: str = "",
) -> None:
    """Edita un contacto existente (nombre, teléfono, email, notas)."""

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    name = (intent.contact_name or "").strip()
    if not name:
        await tell_owner("¿Qué contacto quieres editar? Dime el nombre.")
        return

    # Buscar el contacto por nombre (case-insensitive)
    from sqlalchemy import func, select
    result = await db.execute(
        select(Contact).where(
            Contact.tenant_id == tenant.id,
            func.lower(Contact.name) == name.lower(),
            Contact.is_active.is_(True),
        )
    )
    contact = result.scalar_one_or_none()

    if not contact:
        await tell_owner(f"No encontré a **{name}** en tus contactos activos.")
        return

    updated = []

    # Detectar nuevo nombre: "edita a X a Y", "edita X a Y" o "cambia X a Y".
    # El "a" tras el verbo es opcional (preposición); el nombre capturado
    # debe empezar por letra (evita confundir un número con nombre).
    import re as _re
    _name_re = (
        r"(?:edita|cambia)\s+(?:a\s+)?\S+\s+a\s+"
        r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ].+?)(?:\s+(?:con|tel[eé]fono|email|nota)|$)"
    )
    match = _re.search(_name_re, text, _re.IGNORECASE)
    if match:
        new_name = match.group(1).strip().rstrip(".,;")
        if new_name:
            contact.name = new_name[:100]
            updated.append("nombre")

    # Teléfono: el router del LLM lo extrae en contact_phone; el texto
    # crudo es respaldo ("teléfono 300…", "teléfono de X a 300…").
    digits = _re.sub(r"\D", "", intent.contact_phone or "")
    if not digits:
        _phone_re = (
            r"(?:tel[eé]fono|celular|n[uú]mero)\s+"
            r"(?:de\s+\S+\s+)?(?:a\s+)?([\d\s\-+().]{8,})"
        )
        phone_match = _re.search(_phone_re, text, _re.IGNORECASE)
        if phone_match:
            digits = _re.sub(r"\D", "", phone_match.group(1))
    if len(digits) == 10:
        digits = "57" + digits
    if len(digits) >= 10 and len(digits) <= 15 and digits.isdigit():
        # Verificar duplicado
        existing = await db.execute(
            select(Contact).where(
                Contact.tenant_id == tenant.id,
                Contact.wa_id == digits,
                Contact.id != contact.id,
            )
        )
        if not existing.scalar_one_or_none():
            contact.wa_id = digits
            updated.append("teléfono")
        else:
            await tell_owner("Ese número ya pertenece a otro contacto.")
            return

    # Email: "email juan@email.com" o "correo juan@email.com"
    email_match = _re.search(r"(?:email|correo)\s+([\w.+-]+@[\w.-]+\.\w+)", text, _re.IGNORECASE)
    if email_match:
        contact.email = email_match.group(1).lower()
        updated.append("email")

    # Nota: "nota cliente VIP", "agrega nota a Juan: cliente VIP"…
    note_match = _re.search(
        r"(?:agrega nota|ponle nota|nota)(?:\s+a\s+\S+)?[:\s]+(.+)", text, _re.IGNORECASE
    )
    if note_match:
        note = note_match.group(1).strip()
        contact.notes = (contact.notes or "") + ("\n" if contact.notes else "") + note
        updated.append("nota")

    # Fallback con el contrato del router: description trae el nombre
    # nuevo (o el email/nota si el texto crudo no matcheó arriba).
    if not updated and intent.description:
        desc = intent.description.strip()
        if "@" in desc:
            contact.email = desc.lower()
            updated.append("email")
        elif "nota" in text.lower():
            contact.notes = (contact.notes or "") + ("\n" if contact.notes else "") + desc
            updated.append("nota")
        else:
            contact.name = desc[:100]
            updated.append("nombre")

    if not updated:
        await tell_owner(
            f"¿Qué quieres cambiar de **{contact.name}**?\n"
            "Ejemplos:\n"
            "• «edita a Juliana a Juliana Pérez»\n"
            "• «cambia el teléfono de Pedro a 3109876543»\n"
            "• «ponle email a María: maria@email.com»\n"
            "• «agrega nota a Juan: cliente VIP»"
        )
        return

    await db.commit()
    await tell_owner(
        f"✏️ **{contact.name}** actualizado: {', '.join(updated)}."
    )
    logger.info("Contacto %s editado por chat (tenant %s)", contact.name, tenant.id)


# ── CRM: borrar (desactivar) contacto por chat ─────────────────────────────


async def _handle_delete_contact(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
    text: str = "",
) -> None:
    """Desactiva un contacto (soft delete)."""

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    name = (intent.contact_name or "").strip()
    if not name:
        await tell_owner("¿Qué contacto quieres borrar? Dime el nombre.")
        return

    from sqlalchemy import func, select
    result = await db.execute(
        select(Contact).where(
            Contact.tenant_id == tenant.id,
            func.lower(Contact.name) == name.lower(),
            Contact.is_active.is_(True),
        )
    )
    contact = result.scalar_one_or_none()

    if not contact:
        await tell_owner(f"No encontré a **{name}** en tus contactos activos.")
        return

    contact.is_active = False
    await db.commit()

    await tell_owner(
        f"🗑️ **{name}** retirado del CRM (su historial se conserva)."
    )
    logger.info("Contacto %s desactivado por chat (tenant %s)", name, tenant.id)


# ── CRM: listar contactos por chat ─────────────────────────────────────────


async def _handle_list_contacts(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
    text: str = "",
) -> None:
    """Lista los contactos activos del tenant."""

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    from sqlalchemy import select
    result = await db.execute(
        select(Contact)
        .where(
            Contact.tenant_id == tenant.id,
            Contact.is_active.is_(True),
            Contact.wa_id != wa_id,
        )
        .order_by(Contact.name)
        .limit(20)
    )
    contacts = result.scalars().all()

    if not contacts:
        await tell_owner(
            "No tienes contactos guardados aún. "
            "Usa «agrega a [nombre] con número [celular]»."
        )
        return

    lines = [f"📇 *Tus contactos ({len(contacts)}):*"]
    for c in contacts:
        tags = f" [{', '.join(c.tags)}]" if c.tags else ""
        lines.append(f"• **{c.name}** — {c.wa_id}{tags}")

    await tell_owner("\n".join(lines))
    logger.info("Listado de contactos por chat (tenant %s)", tenant.id)


# ── CRM: ver detalle de contacto por chat ──────────────────────────────────


async def _handle_view_contact(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
    text: str = "",
) -> None:
    """Muestra el detalle de un contacto."""

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    name = (intent.contact_name or "").strip()
    if not name:
        await tell_owner("¿De qué contacto quieres ver el detalle? Dime el nombre.")
        return

    from sqlalchemy import func, select
    result = await db.execute(
        select(Contact).where(
            Contact.tenant_id == tenant.id,
            func.lower(Contact.name) == name.lower(),
            Contact.is_active.is_(True),
        )
    )
    contact = result.scalar_one_or_none()

    if not contact:
        await tell_owner(f"No encontré a **{name}** en tus contactos activos.")
        return

    lines = [
        f"👤 *{contact.name}*",
        f"📱 Teléfono: {contact.wa_id}",
    ]
    if contact.email:
        lines.append(f"📧 Email: {contact.email}")
    if contact.address:
        lines.append(f"📍 Dirección: {contact.address}")
    if contact.notes:
        lines.append(f"📝 Notas: {contact.notes}")
    if contact.tags:
        lines.append(f"🏷️ Etiquetas: {', '.join(contact.tags)}")

    await tell_owner("\n".join(lines))
    logger.info("Detalle de contacto %s por chat (tenant %s)", contact.name, tenant.id)


# ── Navegación web ─────────────────────────────────────────────────────────

_SEARCH_PREFIXES = (
    "busca en internet", "busca en la web", "busca en la internet",
    "busca en google", "buscame en internet", "buscame en la web",
    "busca informacion sobre", "busca información sobre",
    "consulta en internet", "consulta en la web", "googlea",
    "google ", "búscame", "buscame", "busca", "mira en internet",
    "mira en la web", "necesito saber de internet",
)
_OPEN_WORDS = ("abre", "abra", "abrir", "ver", "ver el", "mostrar")


def _clean_search_query(raw: str) -> str:
    """Quita las palabras de comando y deja solo los términos de búsqueda."""
    q = raw.lower().strip().rstrip("?,.!¿¡")
    for prefix in sorted(_SEARCH_PREFIXES, key=len, reverse=True):
        if q.startswith(prefix):
            q = q[len(prefix):].strip()
            break
    return q.strip(" :,.-") or raw.strip()


def _redis_key(conversation_id) -> str:
    return f"websearch:{conversation_id}"


async def _save_last_search(conversation_id, results: list[dict]) -> None:
    """Guarda la última búsqueda en Redis (TTL 10 min) para «abre N»."""
    try:
        from redis.asyncio import from_url

        from app.core.config import get_settings
        client = from_url(get_settings().redis_url, decode_responses=True)
        try:
            import json as _json

            await client.set(
                _redis_key(conversation_id), _json.dumps(results), ex=600
            )
        finally:
            await client.aclose()
    except Exception:
        logger.debug("No se pudo guardar la última búsqueda en Redis")


async def _load_last_search(conversation_id) -> list[dict] | None:
    try:
        import json as _json

        from redis.asyncio import from_url

        from app.core.config import get_settings
        client = from_url(get_settings().redis_url, decode_responses=True)
        try:
            raw = await client.get(_redis_key(conversation_id))
            return _json.loads(raw) if raw else None
        finally:
            await client.aclose()
    except Exception:
        return None


async def _handle_web_search(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
    text: str = "",
) -> None:
    """Navegación web: busca en internet o abre una página (anti-inyección).

    «busca en internet el precio del cobre» → resultados de DuckDuckGo
    «navega a https://…» / mensaje con URL → contenido de la página
    «abre 2» → abre el resultado 2 de la última búsqueda (Redis, 10 min)

    El contenido descargado es DATO: se trunca y se muestra, jamás se
    interpreta como instrucciones.
    """
    import re as _re

    from app.services.web_search import (
        extract_url_from_text,
        fetch_page_text,
        format_results_for_chat,
        search_web,
    )

    async def tell_owner(msg: str) -> None:
        await _send_out_message(
            db, tenant_id=tenant.id, conversation=conversation,
            channel=channel, wa_id=wa_id, text=msg,
        )

    raw = (intent.message_text or text or "").strip()
    lowered = raw.lower()

    # 1) «abre N»: abrir un resultado de la última búsqueda
    open_match = _re.match(
        r"^(?:abre|abra|abrir|ver|ver el|mostrar|muestrame)\s+"
        r"(?:el\s+|la\s+)?"
        r"(?:n[uú]mero\s+|resultado\s+|p[aá]gina\s+)?"
        r"([1-9])\b",
        lowered,
    )
    if open_match and "http" not in lowered:
        idx = int(open_match.group(1))
        results = await _load_last_search(conversation.id)
        if results and 1 <= idx <= len(results):
            target = results[idx - 1]
            await tell_owner(f"🌐 Abriendo: {target['title']}…")
            try:
                page = await fetch_page_text(target["url"])
                body = page[:1500] + ("…" if len(page) > 1500 else "")
                await tell_owner(
                    f"📄 *{target['title']}*\n🔗 {target['url']}\n\n{body}"
                )
            except Exception:
                await tell_owner(
                    "No pude leer esa página (el sitio puede bloquear "
                    "lectores automáticos). Prueba con otro resultado."
                )
            return
        await tell_owner(
            "No tengo una búsqueda reciente con ese número. Hazme una "
            "búsqueda primero (ej: «busca el precio del cobre») o pásame "
            "el enlace directo."
        )
        return

    # 2) URL directa: abrir la página
    url = extract_url_from_text(raw)
    if url:
        await tell_owner("🌐 Abriendo la página…")
        try:
            page = await fetch_page_text(url)
            body = page[:1500] + ("…" if len(page) > 1500 else "")
            await tell_owner(f"📄 Contenido de {url}:\n\n{body}")
        except Exception:
            await tell_owner(
                f"No pude leer {url}. Verifica que el enlace sea válido."
            )
        return

    # 3) Búsqueda en internet
    query = _clean_search_query(raw)
    if not query:
        await tell_owner(
            "¿Qué busco? Dime «busca en internet [tema]» o pásame un enlace."
        )
        return

    await tell_owner(f"🔍 Buscando «{query}» en internet…")
    try:
        results = await search_web(query, max_results=5)
    except Exception:
        logger.exception("Falló la búsqueda web: %s", query[:50])
        await tell_owner(
            "No pude conectarme a internet ahora mismo. Intenta de nuevo "
            "en un momento."
        )
        return

    await _save_last_search(conversation.id, results)
    await tell_owner(format_results_for_chat(results, query))
    logger.info("Búsqueda web OK: %s → %d resultados", query[:50], len(results))


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
    # El LLM no sabe qué día es: inyectar la fecha actual de Colombia
    from app.services.assistant import _now_context

    messages_payload[0]["content"] = (
        f"{_now_context()}\n\n{messages_payload[0]['content']}"
    )
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=messages_payload,
        temperature=0.6,
        # Nemotron razona antes de responder: margen para no quedar
        # con la cadena de pensamiento como contenido final.
        max_tokens=1200,
    )
    reply = (response.choices[0].message.content or "").strip()
    # Anti-fuga de razonamiento: si la "respuesta" parece chain-of-thought
    # (razona sobre el usuario en vez de hablarle), no enviarla tal cual.
    # Modelos de razonamiento (Nemotron, etc.) pueden filtrar su thinking.
    _REASONING_MARKERS = (
        # Inglés - chain of thought típico
        "the user", "user wants", "user said", "user is", "user needs",
        "let me", "i should", "i will", "i need to", "i must", "i'll",
        "first i", "then i", "next i", "finally i",
        "analysis:", "reasoning:", "thinking:", "thought:",
        "step 1", "step 2", "step 3",
        # Español - razonamiento en español
        "debo", "primero debo", "luego debo", "después debo",
        "tengo que", "voy a", "primero voy a", "luego voy a",
        "analizando:", "razonando:", "pensando:",
        "el usuario quiere", "el usuario dice", "el usuario necesita",
        "el usuario está", "el usuario solicitó",
    )
    lowered = reply[:500].lower()  # revisar más caracteres
    if reply and any(m in lowered for m in _REASONING_MARKERS):
        logger.warning("Chat: respuesta con fuga de razonamiento, descartada (len=%d)", len(reply))
        reply = ""
    # Fallback si el filtro dejó la respuesta vacía
    if not reply:
        reply = "Entendido, ¿en qué te ayudo? 🙌"
        logger.info("Chat: usando fallback tras filtro anti-leakage")
    if reply:
        await _send_out_message(
            db,
            tenant_id=tenant.id,
            conversation=conversation,
            channel=channel,
            wa_id=wa_id,
            text=reply,
        )
        # NO loguear uso de "quoter" aquí: _chat_reply es charla general,
        # el quoter se loguea solo en _handle_quote cuando se genera una cotización real.


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

    # El acceso al panel debe funcionar aunque el dueño haya apagado el
    # cotizador: es una capacidad de cuenta, no un servicio contratado.
    wa_id = contact.wa_id
    text = (text_override or message.content or "").strip()
    if _requests_google_connection(text):
        await _handle_google_connection(
            db,
            tenant=tenant,
            channel=channel,
            conversation=conversation,
            wa_id=wa_id,
        )
        return
    if _requests_panel_access(text):
        await _handle_panel_access(
            db,
            tenant=tenant,
            channel=channel,
            conversation=conversation,
            wa_id=wa_id,
        )
        return

    # El asistente solo atiende con el cotizador encendido (contrato del plan)
    if not await _quoter_enabled(db, tenant.id):
        return

    # Motor de disponibilidad (adendo §5): si un servicio que el dueño
    # encendió está caído/en mantenimiento, el bot lo dice con claridad.
    # El lote unificado (debounce) llega como text_override; si no, el propio
    text = (text_override or message.content or "").strip()
    _t0 = datetime.now(UTC)  # para medir la latencia percibida por el dueño

    try:
        # Comandos de super admin desde el chat (prefijo "admin:"):
        # "admin: lista tenants", "admin: activa módulo X en tenant Y", etc.
        if text.lower().startswith("admin:"):
            await _handle_platform_admin(
                db,
                tenant=tenant,
                contact=contact,
                channel=channel,
                conversation=conversation,
                wa_id=wa_id,
                text=text,
            )
            return

        # Soporte para comandos con barra "/" como alias de lenguaje natural
        text = _normalize_slash_commands(text)

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

        if intent.intention == "google_connect":
            await _handle_google_connection(
                db,
                tenant=tenant,
                channel=channel,
                conversation=conversation,
                wa_id=wa_id,
            )
            return

        if intent.intention == "panel_access":
            await _handle_panel_access(
                db,
                tenant=tenant,
                channel=channel,
                conversation=conversation,
                wa_id=wa_id,
            )
            return

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

        if intent.intention == "site_log":
            await _handle_site_log(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
                text=text,
            )
            return

        if intent.intention == "profitability":
            await _handle_profitability(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
            )
            return

        if intent.intention in (
            "google_email", "google_calendar", "google_sheets", "google_docs",
        ):
            usable, why = await _module_usable(
                db, tenant=tenant, module_key="email_calendar"
            )
            if not usable and why:
                await _send_out_message(
                    db, tenant_id=tenant.id, conversation=conversation,
                    channel=channel, wa_id=wa_id, text=f"⚠️ {why}. Te aviso cuando vuelva.",
                )
                return
            if intent.intention == "google_email":
                await google_handlers.handle_google_email(
                    db, tenant=tenant, channel=channel,
                    conversation=conversation, wa_id=wa_id, intent=intent,
                )
            elif intent.intention == "google_calendar":
                await google_handlers.handle_google_calendar(
                    db, tenant=tenant, channel=channel,
                    conversation=conversation, wa_id=wa_id, intent=intent,
                )
            elif intent.intention == "google_sheets":
                await google_handlers.handle_google_sheets(
                    db, tenant=tenant, channel=channel,
                    conversation=conversation, wa_id=wa_id,
                )
            else:
                await google_handlers.handle_google_docs(
                    db, tenant=tenant, channel=channel,
                    conversation=conversation, wa_id=wa_id,
                )
            return

        if intent.intention == "inventory":
            await _handle_inventory(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
                text=text,
            )
            return

        if intent.intention == "expense":
            await _handle_expense(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
                text=text,
            )
            return

        if intent.intention == "warranty":
            await _handle_warranty(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
                text=text,
            )
            return

        if intent.intention == "maintenance":
            await _handle_maintenance(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
                text=text,
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
                conversation=conversation, wa_id=wa_id,
                intent=intent, text=text,
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

        if intent.intention == "support":
            await _handle_support(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
            )
            return

        if intent.intention == "conversation_log":
            await _handle_conversation_log(
                db,
                tenant=tenant,
                channel=channel,
                conversation=conversation,
                wa_id=wa_id,
                intent=intent,
            )
            return

        if intent.intention == "web_search":
            usable, why = await _module_usable(db, tenant=tenant, module_key="web_search")
            if not usable and why:
                await _send_out_message(
                    db, tenant_id=tenant.id, conversation=conversation,
                    channel=channel, wa_id=wa_id, text=f"⚠️ {why}. Te aviso cuando vuelva.",
                )
                return
            await _handle_web_search(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
                text=text,
            )
            return

        if intent.intention == "manage_services":
            await _handle_manage_services(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
                text=text,
            )
            return

        if intent.intention == "add_contact":
            usable, why = await _module_usable(db, tenant=tenant, module_key="crm")
            if not usable and why:
                await _send_out_message(
                    db, tenant_id=tenant.id, conversation=conversation,
                    channel=channel, wa_id=wa_id, text=f"⚠️ {why}. Te aviso cuando vuelva.",
                )
                return
            await _handle_add_contact(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
                text=text,
            )
            return

        # CRM: editar, borrar, listar y ver contactos
        if intent.intention in ("edit_contact", "delete_contact", "list_contacts", "view_contact"):
            usable, why = await _module_usable(db, tenant=tenant, module_key="crm")
            if not usable and why:
                await _send_out_message(
                    db, tenant_id=tenant.id, conversation=conversation,
                    channel=channel, wa_id=wa_id, text=f"⚠️ {why}. Te aviso cuando vuelva.",
                )
                return

            if intent.intention == "edit_contact":
                await _handle_edit_contact(
                    db, tenant=tenant, channel=channel,
                    conversation=conversation, wa_id=wa_id, intent=intent,
                    text=text,
                )
            elif intent.intention == "delete_contact":
                await _handle_delete_contact(
                    db, tenant=tenant, channel=channel,
                    conversation=conversation, wa_id=wa_id, intent=intent,
                    text=text,
                )
            elif intent.intention == "list_contacts":
                await _handle_list_contacts(
                    db, tenant=tenant, channel=channel,
                    conversation=conversation, wa_id=wa_id, intent=intent,
                    text=text,
                )
            elif intent.intention == "view_contact":
                await _handle_view_contact(
                    db, tenant=tenant, channel=channel,
                    conversation=conversation, wa_id=wa_id, intent=intent,
                    text=text,
                )
            return

        if intent.intention == "sync_contacts":
            await _handle_sync_contacts(
                db, tenant=tenant, channel=channel,
                conversation=conversation, wa_id=wa_id, intent=intent,
                text=text,
            )
            return

        if intent.intention == "help":
            # Verificar si este contacto/tenant tiene un user platform_admin
            from sqlalchemy import select

            from app.models import User

            platform_admin_user = (
                await db.execute(
                    select(User).where(
                        User.tenant_id == tenant.id,
                        User.is_platform_admin.is_(True),
                    )
                )
            ).scalar_one_or_none()
            is_platform_admin = platform_admin_user is not None

            await _handle_help(
                db,
                tenant=tenant,
                channel=channel,
                conversation=conversation,
                wa_id=wa_id,
                is_platform_admin=is_platform_admin,
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
        logger.info(
            "Mensaje %s atendido (intención %s) en %.0f ms",
            message.id,
            intent.intention,
            (datetime.now(UTC) - _t0).total_seconds() * 1000,
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


# ═════════════════════════════════════════════════════════════════════
# Guía de herramientas del chat (intención "help")
# ═════════════════════════════════════════════════════════════════════


async def _handle_help(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    is_platform_admin: bool = False,
) -> None:
    """Envía la guía paso a paso de comandos que el dueño puede usar
    por WhatsApp (adendo §3.4: guía de herramientas del asistente).

    Si es super admin de la plataforma, incluye comandos de administración
    multi-tenant. Se aceptan tanto lenguaje natural como barra /.
    """
    # Sección común (dueño del negocio)
    guia = (
        "🤖 *Aura — Guía de comandos por chat*\n\n"
        "💡 *Tip:* puedes usar lenguaje natural o barra `/`\n"
        "   (ej: `/ayuda`, `/mis_contactos`, `/cotiza ...`)\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "*📋 PARA TU NEGOCIO (dueño):*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Cotizaciones:*\n"
        "• `/cotiza a Juan Pérez: 2 tableros, 10m cable`\n"
        "• `/cotizacion para el cliente María`\n\n"
        "*Contactos (CRM):*\n"
        "• `/crea_contacto Jhoymar +57321933514`\n"
        "• `/mis_contactos` — lista tus clientes\n"
        "• `/edita_contacto Jhoymar a Juan Pérez`\n"
        "• `/borra_contacto Jhoymar`\n"
        "• `/contacto Jhoymar` — ver detalle\n\n"
        "*Obras / seguimiento de obra:*\n"
        "• `/abre_obra Instalación iluminación para Jhoymar`\n"
        "• `/mis_obras` — obras abiertas\n"
        "• `/obra Jhoymar: agrega gasto 140k mano de obra`\n"
        "• `/edita_obra Jhoymar a Instalación completa`\n"
        "• `/cierra_obra Jhoymar`\n\n"
        "*Recordatorios:*\n"
        "• `/recordame llamar a Laura a las 8 PM`\n"
        "• `/mis_recordatorios`\n\n"
        "*Gastos / Finanzas:*\n"
        "• `/gasto 45000 cable THHN`\n"
        "• `/ingreso 500000 cobré a Juliana`\n"
        "• `/mis_gastos` — resumen del mes\n"
        "• `/mi_cartera` — balance actual\n\n"
        "*Inventario:*\n"
        "• `/tengo 20m cable` / `/usé 5m cable`\n"
        "• `/inventario` — ver stock\n\n"
        "*Otros:*\n"
        "• `/ayuda` o «ayuda» — esta guía\n"
        "• `/servicios` — ver módulos activos\n"
        "• `/sincroniza_contactos` — trae contactos de Google\n"
    )

    # Sección super admin (solo si es platform admin)
    if is_platform_admin:
        guia += (
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "*🛡️ SUPER ADMIN (plataforma):*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "*Tenants (dueños del bot):*\n"
            "• `/admin: lista tenants` — ver todos los negocios\n"
            "• `/admin: ver tenant <nombre>` — detalle + módulos\n\n"
            "*Módulos por tenant:*\n"
            "• `/admin: activa <módulo> en <tenant>`\n"
            "• `/admin: desactiva <módulo> en <tenant>`\n\n"
            "*Planes:*\n"
            "• `/admin: cambia plan de <tenant> a premium`\n"
            "  (opciones: trial, freemium, premium)\n\n"
            "*Comunicación:*\n"
            "• `/admin: envía mensaje a dueño de <tenant> <texto>`\n"
        )

    guia += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nEscribe lo que necesites y te ayudo al instante."

    await _send_out_message(
        db,
        tenant_id=tenant.id,
        conversation=conversation,
        channel=channel,
        wa_id=wa_id,
        text=guia,
    )


def _normalize_slash_commands(text: str) -> str:
    """Convierte comandos con barra / a lenguaje natural para el router LLM.

    El router de intenciones entiende mejor el lenguaje natural; esto permite
    usar `/ayuda`, `/mis_contactos`, etc. como atajos rápidos.
    """
    text_lower = text.strip().lower()

    # Mapeo de comandos / → lenguaje natural
    slash_map: dict[str, str] = {
        "/ayuda": "ayuda",
        "/help": "ayuda",
        "/comandos": "ayuda",
        "/guia": "ayuda",
        "/mis_contactos": "mis contactos",
        "/contactos": "mis contactos",
        "/crea_contacto": "crea contacto",
        "/nuevo_contacto": "crea contacto",
        "/edita_contacto": "edita contacto",
        "/borra_contacto": "borra contacto",
        "/contacto": "contacto",
        "/mis_obras": "mis obras",
        "/obras": "mis obras",
        "/abre_obra": "abre obra",
        "/nueva_obra": "abre obra",
        "/edita_obra": "edita obra",
        "/cierra_obra": "cierra obra",
        "/cerrar_obra": "cierra obra",
        "/obra": "obra",
        "/mis_recordatorios": "mis recordatorios",
        "/recordatorios": "mis recordatorios",
        "/recordame": "recuérdame",
        "/mis_gastos": "mis gastos",
        "/gastos": "mis gastos",
        "/mi_cartera": "mi cartera",
        "/cartera": "mi cartera",
        "/balance": "mi cartera",
        "/gasto": "gasté",
        "/ingreso": "cobré",
        "/inventario": "qué inventario tengo",
        "/stock": "qué inventario tengo",
        "/tengo": "tengo",
        "/usé": "usé",
        "/use": "usé",
        "/servicios": "lista mis servicios",
        "/modulos": "lista mis servicios",
        "/modulos_activos": "lista mis servicios",
        "/sincroniza_contactos": "sincroniza contactos de google",
        "/sync_contactos": "sincroniza contactos de google",
        "/cotiza": "cotiza",
        "/cotizacion": "cotización",
    }

    # Buscar coincidencia exacta al inicio (después de /)
    for slash_cmd, natural in slash_map.items():
        if text_lower.startswith(slash_cmd):
            # Reemplazar solo el comando, mantener el resto
            resto = text[len(slash_cmd):].strip()
            if resto:
                return f"{natural} {resto}"
            return natural

    # Si no coincide, devolver el texto original
    return text


# ═════════════════════════════════════════════════════════════════════
# Super admin desde el chat (comandos con prefijo "admin:")
# ═════════════════════════════════════════════════════════════════════


def _normalize_admin_cmd(text: str) -> tuple[str, str]:
    """Separa el prefijo "admin:" y devuelve (comando, argumento)."""
    cuerpo = text[len("admin:"):].strip()
    partes = cuerpo.split(None, 1)
    comando = partes[0].lower() if partes else ""
    argumento = partes[1].strip() if len(partes) > 1 else ""
    return comando, argumento


async def _handle_platform_admin(
    db: AsyncSession,
    *,
    tenant: Tenant,
    contact: Contact,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    text: str,
) -> None:
    """Acciones de super admin desde el chat del dueño.

    Requiere que el remitente sea owner de su tenant (ya verificado al
    llegar al path de equipo). Comandos soportados:
    - admin: lista tenants
    - admin: ver tenant <nombre|slug>
    - admin: activa <módulo> en <tenant>
    - admin: desactiva <módulo> en <tenant>
    - admin: cambia plan de <tenant> a <trial|freemium|premium>
    - admin: envía mensaje a dueño de <tenant> <texto>
    """
    from sqlalchemy import func, select

    from app.models import TenantModule

    async def tell(msg: str) -> None:
        await _send_out_message(
            db,
            tenant_id=tenant.id,
            conversation=conversation,
            channel=channel,
            wa_id=wa_id,
            text=msg,
        )

    comando, argumento = _normalize_admin_cmd(text)
    if not comando:
        await tell(
            "Comandos de admin disponibles:\n"
            "• «admin: lista tenants»\n"
            "• «admin: ver tenant <nombre>»\n"
            "• «admin: activa <módulo> en <tenant>»\n"
            "• «admin: desactiva <módulo> en <tenant>»\n"
            "• «admin: cambia plan de <tenant> a <trial|freemium|premium>»\n"
            "• «admin: envía mensaje a dueño de <tenant> <texto>»"
        )
        return

    # Listar todos los tenants (clientes del super admin = dueños del bot)
    if comando in ("lista", "listar", "list"):
        result = await db.execute(select(Tenant).order_by(Tenant.name))
        tenants = result.scalars().all()
        if not tenants:
            await tell("No hay tenants registrados todavía.")
            return
        lines = ["🏢 *Tenants registrados (dueños del bot):*\n"]
        for t in tenants:
            mod_count = (
                await db.execute(
                    select(func.count(TenantModule.id)).where(
                        TenantModule.tenant_id == t.id,
                        TenantModule.is_enabled.is_(True),
                    )
                )
            ).scalar_one()
            lines.append(
                f"• {t.name} ({t.slug}) — plan: {t.plan}, "
                f"WhatsApp: {t.wa_id or '—'}, módulos activos: {mod_count}"
            )
        await tell("\n".join(lines))
        return

    # Ver detalle de un tenant
    if comando in ("ver", "detalle"):
        nombre = argumento.strip()
        if not nombre:
            await tell("Dime el nombre o slug del tenant: «admin: ver tenant <nombre>»")
            return
        result = await db.execute(
            select(Tenant).where(
                (Tenant.name.ilike(f"%{nombre}%")) | (Tenant.slug.ilike(f"%{nombre}%"))
            )
        )
        t = result.scalar_one_or_none()
        if not t:
            await tell(f"No encontré ningún tenant llamado «{nombre}».")
            return
        mod_rows = (
            await db.execute(
                select(TenantModule).where(TenantModule.tenant_id == t.id)
            )
        ).scalars().all()
        mods = ", ".join(
            f"{m.module_key}:{'✅' if m.is_enabled else '❌'}" for m in mod_rows
        ) or "—"
        await tell(
            f"🏢 *{t.name}* ({t.slug})\n"
            f"Plan: {t.plan} | WhatsApp: {t.wa_id or '—'} | "
            f"Activo: {'sí' if t.is_active else 'no'}\n"
            f"Módulos: {mods}"
        )
        return

    # Activar / desactivar módulo de un tenant
    if comando in ("activa", "activar", "enciende", "enable") or comando in (
        "desactiva", "desactivar", "apaga", "disable"
    ):
        enable = comando in ("activa", "activar", "enciende", "enable")
        # Formato: "modulo X en tenant Y" o "X en Y"
        arg_lower = argumento.lower()
        if " en " not in arg_lower:
            await tell(
                "Formato: «admin: activa <módulo> en <tenant>» "
                "o «admin: desactiva <módulo> en <tenant>»."
            )
            return
        modulo, tenant_nombre = arg_lower.split(" en ", 1)
        modulo = modulo.strip()
        tenant_nombre = tenant_nombre.strip()
        result = await db.execute(
            select(Tenant).where(
                (Tenant.name.ilike(f"%{tenant_nombre}%"))
                | (Tenant.slug.ilike(f"%{tenant_nombre}%"))
            )
        )
        t = result.scalar_one_or_none()
        if not t:
            await tell(f"No encontré ningún tenant llamado «{tenant_nombre}».")
            return
        modulo_row = (
            await db.execute(
                select(TenantModule).where(
                    TenantModule.tenant_id == t.id,
                    TenantModule.module_key == modulo,
                )
            )
        ).scalar_one_or_none()
        if not modulo_row:
            await tell(
                f"El tenant «{t.name}» no tiene el módulo «{modulo}» registrado."
            )
            return
        modulo_row.is_enabled = enable
        await db.commit()
        await tell(
            f"{'✅ Activado' if enable else '⛔ Desactivado'} el módulo "
            f"«{modulo}» en el tenant «{t.name}»."
        )
        return

    # Cambiar plan de un tenant
    if comando in ("cambia", "cambiar"):
        # Formato: "plan de <tenant> a <plan>"
        arg_lower = argumento.lower()
        if " de " not in arg_lower or " a " not in arg_lower:
            await tell(
                "Formato: «admin: cambia plan de <tenant> a <trial|freemium|premium>»."
            )
            return
        # "plan de <tenant> a <plan>"
        resto = arg_lower.split(" de ", 1)[1]
        tenant_nombre, plan_nombre = resto.split(" a ", 1)
        tenant_nombre = tenant_nombre.strip()
        plan_nombre = plan_nombre.strip()
        if plan_nombre not in ("trial", "freemium", "premium"):
            await tell("El plan debe ser: trial, freemium o premium.")
            return
        result = await db.execute(
            select(Tenant).where(
                (Tenant.name.ilike(f"%{tenant_nombre}%"))
                | (Tenant.slug.ilike(f"%{tenant_nombre}%"))
            )
        )
        t = result.scalar_one_or_none()
        if not t:
            await tell(f"No encontré ningún tenant llamado «{tenant_nombre}».")
            return
        t.plan = plan_nombre
        await db.commit()
        await tell(
            f"✅ Plan del tenant «{t.name}» cambiado a *{plan_nombre}*."
        )
        return

    # Enviar mensaje al dueño de un tenant
    if comando in ("envía", "enviar"):
        # Formato: "mensaje a dueño de <tenant> <texto>"
        arg_lower = argumento.lower()
        if " dueño de " not in arg_lower:
            await tell(
                "Formato: «admin: envía mensaje a dueño de <tenant> <texto>»."
            )
            return
        # Usamos el argumento original para preservar mayúsculas en el mensaje
        texto_original = argumento
        _, despues = texto_original.split(" dueño de ", 1)
        # despues = "<tenant> <texto>" → split en el primer espacio
        partes_despues = despues.split(None, 1)
        tenant_nombre = partes_despues[0]
        mensaje = partes_despues[1] if len(partes_despues) > 1 else ""
        if not mensaje:
            await tell("Dime el texto a enviar: «admin: envía mensaje a dueño de <tenant> <texto>»")
            return
        result = await db.execute(
            select(Tenant).where(
                (Tenant.name.ilike(f"%{tenant_nombre}%"))
                | (Tenant.slug.ilike(f"%{tenant_nombre}%"))
            )
        )
        t = result.scalar_one_or_none()
        if not t or not t.wa_id:
            await tell(
                f"No encontré un tenant con WhatsApp configurado para «{tenant_nombre}»."
            )
            return
        try:
            await channel.send_text(t.wa_id, f"📢 Mensaje del super admin:\n{mensaje}")
            await tell(f"✅ Mensaje enviado al dueño de «{t.name}» ({t.wa_id}).")
        except Exception as exc:
            logger.exception("No se pudo enviar mensaje de admin al tenant %s", t.id)
            await tell(f"No pude enviar el mensaje al dueño de «{t.name}»: {exc}")
        return

    await tell(
        "Comando no reconocido. Usa «admin: lista tenants» para ver las opciones."
    )
