"""Agenda de recordatorios: ver, programar y cerrar desde el panel.

El flujo por chat («recuérdame llamar al cliente el jueves») crea
recordatorios igual; esta API es su contraparte visual. El ciclo de
main.py sigue siendo quien los envía por WhatsApp cuando llega la hora.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas.reminders import ReminderCreate, ReminderOut, ReminderStatusUpdate
from app.services import notes as notes_service

router = APIRouter()


@router.get("", response_model=list[ReminderOut])
async def list_reminders(
    status_filter: str | None = Query(
        None, alias="status", pattern="^(pending|sent|done|cancelled)$"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReminderOut]:
    """Agenda del negocio. ?status=pending → próximos y vencidos por hora."""
    reminders = await notes_service.list_reminders(
        db, tenant_id=current_user.tenant_id, status=status_filter
    )
    return [ReminderOut.model_validate(r) for r in reminders]


@router.post("", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
async def create_reminder(
    body: ReminderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReminderOut:
    """Programa un recordatorio: el bot escribirá al dueño en la fecha."""
    reminder = await notes_service.save_reminder(
        db,
        tenant_id=current_user.tenant_id,
        content=body.content,
        remind_at=body.remind_at,
    )
    await notes_service.sync_reminder_to_google(db, reminder)
    return ReminderOut.model_validate(reminder)


@router.put("/{reminder_id}", response_model=ReminderOut)
async def update_reminder_status(
    reminder_id: UUID,
    body: ReminderStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReminderOut:
    """Cierra un recordatorio pendiente: hecho (done) o cancelado."""
    reminder = await notes_service.set_reminder_status(
        db,
        tenant_id=current_user.tenant_id,
        reminder_id=reminder_id,
        status=body.status,
    )
    if reminder is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recordatorio no encontrado o ya cerrado",
        )
    return ReminderOut.model_validate(reminder)
