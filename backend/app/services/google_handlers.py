"""Handlers de chat de Google Workspace (spec §15).

La lógica de correo, agenda, hojas y docs de Google vive aquí — no en el
orquestador — junto a su confirmación de envío. El orquestador solo
despacha: mantiene el cerebro pequeño y esta familia junta.

Regla §8.1: enviar un correo a un tercero es irreversible → siempre
pasa por PendingAction con «¿Te lo envío?» antes de tocar Gmail.
"""

import logging
from datetime import UTC, datetime, timedelta
from datetime import timezone as tz

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.models import Conversation, PendingAction, Tenant
from app.schemas.assistant import AssistantIntent
from app.services import google_actions
from app.services.chat_utils import resolve_contact_by_name, send_out_message
from app.services.google_oauth import GoogleAuthError, GoogleNotConnected

logger = logging.getLogger(__name__)

_DIAS_CORTOS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def _fmt_event_time(raw: str) -> str:
    """RFC3339 de Google → «jue 20/10 03:00 PM» en hora Colombia (UTC-5).

    Los eventos de todo el día llegan como "2026-10-20" (sin hora).
    """
    if "T" not in raw:
        try:
            day = datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError:
            return raw
        return f"{_DIAS_CORTOS[day.weekday()]} {day.strftime('%d/%m')} (todo el día)"

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    local = parsed.astimezone(tz(timedelta(hours=-5)))
    return f"{_DIAS_CORTOS[local.weekday()]} {local.strftime('%d/%m %I:%M %p')}"


def _tell_owner_factory(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
):
    """El «tell_owner» que todos los handlers usan para hablar con el dueño."""

    async def tell_owner(msg: str) -> None:
        await send_out_message(
            db,
            tenant_id=tenant.id,
            conversation=conversation,
            channel=channel,
            wa_id=wa_id,
            text=msg,
        )

    return tell_owner


async def handle_google_email(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """Correo de Gmail: resumir la bandeja o escribir a un contacto.

    «resumime el correo» → los últimos correos (solo lectura).
    «escríbele un correo a Juliana diciendo que llego a las 3» → borrador
    con confirmación previa: enviar a un tercero es irreversible (§8.1).
    """
    tell_owner = _tell_owner_factory(
        db, tenant=tenant, channel=channel, conversation=conversation, wa_id=wa_id
    )

    # Escribirle un correo a un contacto → borrador + confirmación.
    # Conexión primero: sin cuenta Google no ofrecemos el borrador (el
    # dueño no debería confirmar algo que va a fallar al enviar).
    if intent.contact_name and intent.message_text:
        status = await google_actions.connection_status(db, tenant_id=tenant.id)
        if not status["connected"]:
            await tell_owner(
                "🔗 Aún no has conectado tu cuenta de Google. Hazlo desde "
                "el panel (Mi negocio → Conectar Google) y te ayudo a "
                "escribir correos."
            )
            return
        matches = await resolve_contact_by_name(
            db, tenant_id=tenant.id, name=intent.contact_name
        )
        target = next((c for c in matches if c.email), None)
        if target is None:
            await tell_owner(
                f"No tengo el correo de «{intent.contact_name}». "
                "Agrégalo en el panel (CRM) o dime su correo electrónico."
            )
            return
        subject = f"Mensaje de {tenant.name}"
        body = intent.message_text.strip()
        db.add(
            PendingAction(
                tenant_id=tenant.id,
                conversation_id=conversation.id,
                action_type="send_email",
                payload={
                    "to": target.email,
                    "subject": subject,
                    "body": body,
                    "contact_id": str(target.id),
                },
            )
        )
        await db.commit()
        await tell_owner(
            f"📧 Preparé este correo:\n\n"
            f"Para: {target.name or target.email} <{target.email}>\n"
            f"Asunto: {subject}\n\n{body}\n\n¿Te lo envío?"
        )
        return

    # Resumen de la bandeja de entrada
    try:
        messages = await google_actions.summarize_inbox(
            db, tenant_id=tenant.id, max_results=5
        )
    except GoogleNotConnected:
        await tell_owner(
            "🔗 Aún no has conectado tu cuenta de Google. Hazlo desde el "
            "panel (Mi negocio → Conectar Google) y podré leerte el correo."
        )
        return
    except GoogleAuthError as exc:
        await tell_owner(f"⚠️ {exc}")
        return
    except Exception:
        logger.exception("El resumen de Gmail falló")
        await tell_owner("⚠️ No pude leer tu correo ahora. Intenta de nuevo.")
        return

    if not messages:
        await tell_owner("📭 No tienes correos en la bandeja de entrada.")
        return
    lines = ["📬 Tus últimos correos:\n"]
    for i, m in enumerate(messages, start=1):
        lines.append(
            f"{i}. {m['subject'] or '(sin asunto)'}\n"
            f"   De: {m['from'] or 'desconocido'}\n"
            f"   «{m['snippet']}»"
        )
    await tell_owner("\n\n".join(lines))


async def handle_google_calendar(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    intent: AssistantIntent,
) -> None:
    """Agenda de Google Calendar: consultar o agendar eventos.

    «qué tengo mañana» → eventos de los próximos días.
    «agenda visita de Juliana el jueves a las 3» → crea el evento.
    """
    tell_owner = _tell_owner_factory(
        db, tenant=tenant, channel=channel, conversation=conversation, wa_id=wa_id
    )

    # Agendar: el router de intenciones extrajo la fecha ISO en remind_at
    if intent.remind_at:
        start = None
        try:
            start = datetime.fromisoformat(intent.remind_at)
        except ValueError:
            pass
        if start is not None:
            if start.tzinfo is None:
                # Hora Colombia (UTC-5): naive 15:00 Bogotá → 20:00 UTC
                start = (start + timedelta(hours=5)).replace(tzinfo=UTC)
            title = (
                intent.message_text or intent.description or "Evento"
            ).strip()[:150]
            if (
                intent.contact_name
                and intent.contact_name.lower() not in title.lower()
            ):
                title = f"{title} — {intent.contact_name}"
            try:
                await google_actions.create_event(
                    db,
                    tenant_id=tenant.id,
                    summary=title,
                    start_at=start,
                    description=intent.description,
                )
            except GoogleNotConnected:
                await tell_owner(
                    "🔗 Conecta tu cuenta de Google desde el panel "
                    "(Mi negocio) y agendo por ti."
                )
                return
            except GoogleAuthError as exc:
                await tell_owner(f"⚠️ {exc}")
                return
            except Exception:
                logger.exception("Crear evento de Calendar falló")
                await tell_owner("⚠️ No pude agendar el evento. Intenta de nuevo.")
                return
            local = start.astimezone(tz(timedelta(hours=-5)))
            when = local.strftime("%d/%m a las %I:%M %p")
            await tell_owner(
                f"✅ Agendado en tu Google Calendar: «{title}» el {when}."
            )
            return

    # Consultar la agenda: hoy / mañana / esta semana
    text_lower = (intent.message_text or intent.description or "").lower()
    days = 7
    if "hoy" in text_lower:
        days = 1
    elif "mañana" in text_lower or "manana" in text_lower:
        days = 2
    try:
        events = await google_actions.upcoming_events(
            db, tenant_id=tenant.id, days=days
        )
    except GoogleNotConnected:
        await tell_owner(
            "🔗 Conecta tu cuenta de Google desde el panel "
            "(Mi negocio) y podré ver tu agenda."
        )
        return
    except GoogleAuthError as exc:
        await tell_owner(f"⚠️ {exc}")
        return
    except Exception:
        logger.exception("Leer la agenda de Calendar falló")
        await tell_owner("⚠️ No pude leer tu agenda ahora. Intenta de nuevo.")
        return

    if not events:
        await tell_owner(f"📅 Nada agendado en los próximos {days} día(s).")
        return
    lines = ["📅 Tu agenda:\n"]
    for ev in events:
        start_raw = (
            ev.get("start", {}).get("dateTime")
            or ev.get("start", {}).get("date", "")
        )
        lines.append(
            f"• {_fmt_event_time(start_raw)} — {ev.get('summary', '(sin título)')}"
        )
    await tell_owner("\n".join(lines))


async def handle_google_sheets(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
) -> None:
    """Exporta los gastos del mes a una hoja de Google Sheets (spec §15)."""
    tell_owner = _tell_owner_factory(
        db, tenant=tenant, channel=channel, conversation=conversation, wa_id=wa_id
    )
    try:
        result = await google_actions.export_expenses_sheet(db, tenant=tenant)
    except GoogleNotConnected:
        await tell_owner(
            "🔗 Conecta tu cuenta de Google desde el panel "
            "(Mi negocio) y exporto tus gastos a Sheets."
        )
        return
    except GoogleAuthError as exc:
        await tell_owner(f"⚠️ {exc}")
        return
    except Exception:
        logger.exception("Exportar gastos a Sheets falló")
        await tell_owner("⚠️ No pude crear la hoja de cálculo. Intenta de nuevo.")
        return
    await tell_owner(
        f"📊 Listo: pasé {result['rows']} gastos del mes a la hoja "
        f"«{result['title']}».\n{result['url']}"
    )


async def handle_google_docs(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
) -> None:
    """Genera el informe del mes en un Google Doc nuevo (spec §15)."""
    tell_owner = _tell_owner_factory(
        db, tenant=tenant, channel=channel, conversation=conversation, wa_id=wa_id
    )
    try:
        result = await google_actions.create_month_report_doc(db, tenant=tenant)
    except GoogleNotConnected:
        await tell_owner(
            "🔗 Conecta tu cuenta de Google desde el panel "
            "(Mi negocio) y genero tu informe en Docs."
        )
        return
    except GoogleAuthError as exc:
        await tell_owner(f"⚠️ {exc}")
        return
    except Exception:
        logger.exception("Generar informe en Docs falló")
        await tell_owner("⚠️ No pude crear el documento. Intenta de nuevo.")
        return
    await tell_owner(
        f"📄 Informe listo en Google Docs: «{result['title']}».\n{result['url']}"
    )


async def confirm_send_email(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel: Channel,
    conversation: Conversation,
    wa_id: str,
    pending: PendingAction,
) -> bool:
    """El dueño dijo «sí»: enviar el correo desde SU cuenta Google.

    Si falla, la acción VUELVE a quedar pendiente (el borrador no se
    pierde): reconecta y dice «sí» de nuevo para reintentar.
    """
    tell_owner = _tell_owner_factory(
        db, tenant=tenant, channel=channel, conversation=conversation, wa_id=wa_id
    )
    payload = pending.payload
    try:
        await google_actions.send_email(
            db,
            tenant_id=tenant.id,
            to=payload["to"],
            subject=payload["subject"],
            body=payload["body"],
        )
    except GoogleNotConnected:
        pending.status = "pending"
        await db.commit()
        await tell_owner(
            "🔗 Tu cuenta de Google no está conectada. Conéctala desde "
            "el panel (Mi negocio) y respóndeme «sí» para reintentar el envío."
        )
        return True
    except GoogleAuthError:
        pending.status = "pending"
        await db.commit()
        await tell_owner(
            "⚠️ Tu conexión con Google expiró. Reconéctala desde el "
            "panel (Mi negocio) y respóndeme «sí» para reintentar el envío."
        )
        return True
    except Exception:
        pending.status = "pending"
        await db.commit()
        logger.exception("El envío de correo desde Google falló")
        await tell_owner(
            "⚠️ No pude enviar el correo ahora. Dime «sí» para reintentarlo."
        )
        return True
    await tell_owner(f"✅ Correo enviado a {payload['to']}.")
    return True
