"""Notas y recordatorios del dueño: guardar, buscar, listar y borrar por chat.

Spec §13: notas con borrado lógico recuperable; recordatorios únicos y
recurrentes con envío automático en la fecha programada.
Incluye pre-notificaciones: 2h antes y 30min antes del recordatorio.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Note, Reminder
from app.services import google_actions
from app.services.google_oauth import GoogleAuthError, GoogleNotConnected

logger = logging.getLogger(__name__)

_SAVE_WORDS = ("guarda", "guárdame", "apunta", "anota", "nota:", "recuerda que", "toma nota")
_LIST_WORDS = ("qué notas", "que notas", "mis notas", "muéstrame", "muestrame", "lista")
_SEARCH_WORDS = ("busca", "encuentra", "hay alguna nota")
_DELETE_WORDS = ("borra", "elimina", "quita", "ya no necesito")


def detect_note_action(text: str) -> str:
    """Detecta qué hacer con la nota: save, list, search, delete."""
    lowered = text.lower().strip()
    if any(word in lowered for word in _SAVE_WORDS):
        return "save"
    if any(word in lowered for word in _LIST_WORDS):
        return "list"
    if any(word in lowered for word in _SEARCH_WORDS):
        return "search"
    if any(word in lowered for word in _DELETE_WORDS):
        return "delete"
    return "save"  # default: guardar


async def save_note(
    db: AsyncSession, *, tenant_id: UUID, content: str
) -> Note:
    """Guarda una nota nueva."""
    note = Note(tenant_id=tenant_id, content=content.strip()[:2000])
    db.add(note)
    await db.commit()
    logger.debug("Nota guardada para tenant %s", tenant_id)
    return note


async def sync_note_to_google(db: AsyncSession, note: Note) -> Note:
    """Sincroniza una nota local sin hacer depender de ello su creación."""
    try:
        external = await google_actions.create_note(
            db, tenant_id=note.tenant_id, content=note.content
        )
    except GoogleNotConnected:
        note.google_sync_status = "local"
    except GoogleAuthError:
        note.google_sync_status = "auth_error"
    except Exception:
        logger.exception("No se pudo sincronizar la nota %s con Google", note.id)
        note.google_sync_status = "error"
    else:
        note.google_provider = external["provider"]
        note.google_external_id = external["external_id"]
        note.google_url = external["url"]
        note.google_sync_status = "synced"
    await db.commit()
    return note


async def list_notes(
    db: AsyncSession, *, tenant_id: UUID, limit: int = 10
) -> list[Note]:
    """Las notas más recientes del negocio."""
    return list(
        (
            await db.execute(
                select(Note)
                .where(Note.tenant_id == tenant_id, Note.is_active.is_(True))
                .order_by(Note.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
    )


async def search_notes(
    db: AsyncSession, *, tenant_id: UUID, query: str, limit: int = 5
) -> list[Note]:
    """Busca notas que contengan el texto (ILIKE escapado)."""

    from app.services.ai_extraction import _escape_like

    pattern = f"%{_escape_like(query.strip()[:50])}%"
    return list(
        (
            await db.execute(
                select(Note)
                .where(
                    Note.tenant_id == tenant_id,
                    Note.is_active.is_(True),
                    Note.content.ilike(pattern),
                )
                .order_by(Note.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
    )


async def soft_delete_note(
    db: AsyncSession, *, tenant_id: UUID, query: str
) -> int:
    """Borrado lógico de las notas que coincidan (spec §13: recuperable)."""
    from sqlalchemy import update

    from app.services.ai_extraction import _escape_like

    pattern = f"%{_escape_like(query.strip()[:50])}%"
    result = await db.execute(
        update(Note)
        .where(
            Note.tenant_id == tenant_id,
            Note.is_active.is_(True),
            Note.content.ilike(pattern),
        )
        .values(is_active=False)
    )
    await db.commit()
    return result.rowcount or 0


async def save_reminder(
    db: AsyncSession, *, tenant_id: UUID, content: str, remind_at: datetime
) -> Reminder:
    """Crea un recordatorio que el bot enviará en la fecha."""
    reminder = Reminder(
        tenant_id=tenant_id, content=content.strip()[:500], remind_at=remind_at
    )
    db.add(reminder)
    await db.commit()
    logger.info("Recordatorio creado para %s (tenant %s)", remind_at, tenant_id)
    return reminder


async def sync_reminder_to_google(
    db: AsyncSession, reminder: Reminder
) -> Reminder:
    """Crea el evento equivalente en Calendar, si OAuth está disponible."""
    try:
        event = await google_actions.create_event(
            db,
            tenant_id=reminder.tenant_id,
            summary=f"⏰ {reminder.content}",
            start_at=reminder.remind_at,
            description="Recordatorio creado por Aura",
        )
    except GoogleNotConnected:
        reminder.google_sync_status = "local"
    except GoogleAuthError:
        reminder.google_sync_status = "auth_error"
    except Exception:
        logger.exception(
            "No se pudo sincronizar el recordatorio %s con Calendar", reminder.id
        )
        reminder.google_sync_status = "error"
    else:
        reminder.google_event_id = event.get("id")
        reminder.google_sync_status = "synced"
    await db.commit()
    return reminder


async def due_reminders(db: AsyncSession) -> list[tuple[Reminder, str]]:
    """
    Recordatorios que necesitan ser notificados.

    Retorna tuplas (reminder, notification_type) donde notification_type es:
    - "2h": pre-notificación 2 horas antes
    - "30m": pre-notificación 30 minutos antes
    - "main": recordatorio principal (en la hora exacta)

    El loop principal itera sobre esto y envía el mensaje apropiado.
    """
    now = datetime.now(UTC)
    results: list[tuple[Reminder, str]] = []

    # 1) Recordatorios principales cuya hora ya llegó
    main_reminders = list(
        (
            await db.execute(
                select(Reminder)
                .where(
                    Reminder.status == "pending",
                    Reminder.remind_at <= now,
                )
                .order_by(Reminder.remind_at.asc())
                .limit(20)
            )
        ).scalars().all()
    )
    for r in main_reminders:
        results.append((r, "main"))

    # 2) Pre-notificación 2 horas antes
    # Ventana: remind_at entre (now + 2h - 5min) y (now + 2h + 5min)
    two_hours_start = now + timedelta(hours=2) - timedelta(minutes=5)
    two_hours_end = now + timedelta(hours=2) + timedelta(minutes=5)
    pre_2h = list(
        (
            await db.execute(
                select(Reminder)
                .where(
                    Reminder.status == "pending",
                    Reminder.pre_notified_2h.is_(False),
                    Reminder.remind_at > now,  # aún no ha llegado la hora principal
                    Reminder.remind_at >= two_hours_start,
                    Reminder.remind_at <= two_hours_end,
                )
                .order_by(Reminder.remind_at.asc())
                .limit(20)
            )
        ).scalars().all()
    )
    for r in pre_2h:
        results.append((r, "2h"))

    # 3) Pre-notificación 30 minutos antes
    # Ventana: remind_at entre (now + 30min - 5min) y (now + 30min + 5min)
    thirty_min_start = now + timedelta(minutes=30) - timedelta(minutes=5)
    thirty_min_end = now + timedelta(minutes=30) + timedelta(minutes=5)
    pre_30m = list(
        (
            await db.execute(
                select(Reminder)
                .where(
                    Reminder.status == "pending",
                    Reminder.pre_notified_30m.is_(False),
                    Reminder.remind_at > now,
                    Reminder.remind_at >= thirty_min_start,
                    Reminder.remind_at <= thirty_min_end,
                )
                .order_by(Reminder.remind_at.asc())
                .limit(20)
            )
        ).scalars().all()
    )
    for r in pre_30m:
        results.append((r, "30m"))

    return results


async def mark_reminder_sent(
    db: AsyncSession, reminder: Reminder, notification_type: str = "main"
) -> None:
    """
    Marca el recordatorio como enviado según el tipo de notificación.

    notification_type: "main" | "2h" | "30m"
    """
    if notification_type == "main":
        reminder.status = "sent"
        reminder.sent_at = datetime.now(UTC)
    elif notification_type == "2h":
        reminder.pre_notified_2h = True
    elif notification_type == "30m":
        reminder.pre_notified_30m = True
    await db.commit()


# ── Panel: la agenda visible ────────────────────────────────────────────────


async def list_reminders(
    db: AsyncSession, *, tenant_id: UUID, status: str | None = None, limit: int = 50
) -> list[Reminder]:
    """Agenda del panel.

    status="pending" → próximos y vencidos, ordenados por hora ascendente
    (los vencidos primero: son lo más urgente). Otro estado → historial.
    Sin estado → todo lo reciente.
    """
    stmt = select(Reminder).where(Reminder.tenant_id == tenant_id)
    if status == "pending":
        stmt = stmt.where(Reminder.status == "pending").order_by(
            Reminder.remind_at.asc()
        )
    elif status:
        stmt = stmt.where(Reminder.status == status).order_by(
            Reminder.created_at.desc()
        )
    else:
        stmt = stmt.order_by(Reminder.remind_at.desc())
    return list((await db.execute(stmt.limit(limit))).scalars().all())


async def set_reminder_status(
    db: AsyncSession, *, tenant_id: UUID, reminder_id: UUID, status: str
) -> Reminder | None:
    """Cierre manual del panel. None si no existe o ya fue cerrado/enviado."""
    reminder = (
        await db.execute(
            select(Reminder).where(
                Reminder.tenant_id == tenant_id, Reminder.id == reminder_id
            )
        )
    ).scalar_one_or_none()
    if reminder is None or reminder.status != "pending":
        return None
    reminder.status = status
    if status == "done":
        reminder.sent_at = datetime.now(UTC)
    if reminder.google_event_id:
        try:
            if status == "cancelled":
                await google_actions.delete_event(
                    db,
                    tenant_id=tenant_id,
                    event_id=reminder.google_event_id,
                )
                reminder.google_event_id = None
            elif status == "done":
                await google_actions.update_event(
                    db,
                    tenant_id=tenant_id,
                    event_id=reminder.google_event_id,
                    summary=f"✅ {reminder.content}",
                    start_at=reminder.remind_at,
                    description="Completado en Aura",
                )
            reminder.google_sync_status = "synced"
        except GoogleNotConnected:
            reminder.google_sync_status = "auth_error"
        except GoogleAuthError:
            reminder.google_sync_status = "auth_error"
        except Exception:
            logger.exception(
                "No se pudo actualizar el evento del recordatorio %s", reminder.id
            )
            reminder.google_sync_status = "error"
    await db.commit()
    return reminder


async def reschedule_reminder(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    reminder_id: UUID,
    remind_at: datetime,
) -> Reminder | None:
    """Aplaza un recordatorio pendiente y actualiza Calendar si existe."""
    reminder = (
        await db.execute(
            select(Reminder).where(
                Reminder.tenant_id == tenant_id,
                Reminder.id == reminder_id,
                Reminder.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if reminder is None:
        return None
    reminder.remind_at = remind_at
    reminder.pre_notified_2h = False
    reminder.pre_notified_30m = False
    if reminder.google_event_id:
        try:
            await google_actions.update_event(
                db,
                tenant_id=tenant_id,
                event_id=reminder.google_event_id,
                summary=f"⏰ {reminder.content}",
                start_at=remind_at,
                description="Recordatorio aplazado por Aura",
            )
            reminder.google_sync_status = "synced"
        except GoogleNotConnected:
            reminder.google_sync_status = "auth_error"
        except GoogleAuthError:
            reminder.google_sync_status = "auth_error"
        except Exception:
            logger.exception(
                "No se pudo aplazar el evento del recordatorio %s", reminder.id
            )
            reminder.google_sync_status = "error"
    await db.commit()
    return reminder
