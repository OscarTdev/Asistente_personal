"""Utilidades de chat compartidas por los handlers del orquestador.

Enviar por el canal y persistir, y resolver contactos por nombre: los
usan el orquestador y los módulos de handlers (google, ...), para que
ninguno duplique la mecánica de conversación.
"""

import uuid
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.models import Contact, Conversation, Message
from app.services.ai_extraction import _escape_like


async def send_out_message(
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


async def resolve_contact_by_name(
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
