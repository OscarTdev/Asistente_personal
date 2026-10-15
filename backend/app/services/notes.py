"""Notas y recordatorios del dueño: guardar, buscar, listar y borrar por chat.

Spec §13: notas con borrado lógico recuperable; recordatorios únicos y
recurrentes con envío automático en la fecha programada.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Note, Reminder

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


async def due_reminders(db: AsyncSession) -> list[Reminder]:
    """Recordatorios pendientes cuya hora ya llegó."""
    return list(
        (
            await db.execute(
                select(Reminder)
                .where(
                    Reminder.status == "pending",
                    Reminder.remind_at <= datetime.now(UTC),
                )
                .order_by(Reminder.remind_at.asc())
                .limit(20)
            )
        ).scalars().all()
    )


async def mark_reminder_sent(db: AsyncSession, reminder: Reminder) -> None:
    reminder.status = "sent"
    reminder.sent_at = datetime.now(UTC)
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
    await db.commit()
    return reminder
