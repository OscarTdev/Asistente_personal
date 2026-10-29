"""Actividad real del bot para el panel del tenant."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact, Conversation, Message
from app.schemas.realtime import ActiveBotUser, RealtimeActivity


async def compute_realtime_activity(
    db: AsyncSession, *, tenant_id: UUID, window_minutes: int = 15
) -> RealtimeActivity:
    """Devuelve quién interactuó con Aura recientemente.

    Se agrupa en PostgreSQL para no transferir el historial completo al panel.
    Complejidad: O(M_w log M_w) por la agrupación/ordenación de mensajes de la
    ventana; memoria de aplicación O(U_w), donde U_w son contactos activos.
    """
    now = datetime.now(UTC)
    since = now - timedelta(minutes=window_minutes)
    last_activity = func.max(Message.created_at).label("last_activity_at")
    messages_count = func.count(Message.id).label("messages")
    last_in = func.max(
        case((Message.direction == "in", Message.created_at), else_=None)
    )
    last_out = func.max(
        case((Message.direction == "out", Message.created_at), else_=None)
    )
    rows = (
        await db.execute(
            select(
                Contact.id,
                Contact.name,
                Contact.wa_id,
                last_activity,
                messages_count,
                last_in.label("last_in"),
                last_out.label("last_out"),
            )
            .join(Conversation, Conversation.contact_id == Contact.id)
            .join(Message, Message.conversation_id == Conversation.id)
            .where(
                Contact.tenant_id == tenant_id,
                Conversation.tenant_id == tenant_id,
                Message.tenant_id == tenant_id,
                Message.created_at >= since,
            )
            .group_by(Contact.id, Contact.name, Contact.wa_id)
            .order_by(last_activity.desc())
            .limit(50)
        )
    ).all()

    users = []
    for row in rows:
        direction = "in" if row.last_in and (
            not row.last_out or row.last_in >= row.last_out
        ) else "out"
        users.append(
            ActiveBotUser(
                contact_id=row.id,
                name=row.name or row.wa_id,
                wa_id=row.wa_id,
                last_activity_at=row.last_activity_at,
                last_direction=direction,
                messages=int(row.messages),
            )
        )
    total = int(
        (
            await db.execute(
                select(func.count(Message.id)).where(
                    Message.tenant_id == tenant_id,
                    Message.created_at >= since,
                )
            )
        ).scalar_one()
    )
    return RealtimeActivity(
        window_minutes=window_minutes,
        active_now=len(users),
        messages_in_window=total,
        last_activity_at=users[0].last_activity_at if users else None,
        users=users,
    )
