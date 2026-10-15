"""Administración de clientes (contactos de WhatsApp) para el panel."""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact, Conversation, Message, Note, Quote, ServiceUsage
from app.schemas.contacts import ContactDetail, ContactOut, ContactUpdate


async def list_contacts(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    skip: int,
    limit: int,
    search: str | None,
    active_only: bool,
    tag: str | None = None,
) -> tuple[list[ContactOut], int]:
    """Lista los clientes del tenant con métricas de interacción."""
    last_at_sq = (
        select(
            Conversation.contact_id.label("contact_id"),
            func.max(Conversation.last_message_at).label("last_at"),
        )
        .where(Conversation.tenant_id == tenant_id)
        .group_by(Conversation.contact_id)
    ).subquery()

    msg_count_sq = (
        select(
            Conversation.contact_id.label("contact_id"),
            func.count(Message.id).label("cnt"),
        )
        .join(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id == tenant_id)
        .group_by(Conversation.contact_id)
    ).subquery()

    usage_count_sq = (
        select(
            ServiceUsage.contact_id.label("contact_id"),
            func.count(ServiceUsage.id).label("cnt"),
        )
        .where(
            ServiceUsage.tenant_id == tenant_id,
            ServiceUsage.contact_id.is_not(None),
        )
        .group_by(ServiceUsage.contact_id)
    ).subquery()

    conditions = [Contact.tenant_id == tenant_id]
    if active_only:
        conditions.append(Contact.is_active.is_(True))
    if search:
        pattern = f"%{search}%"
        conditions.append(or_(Contact.name.ilike(pattern), Contact.wa_id.ilike(pattern)))
    if tag:
        # JSONB containment: tags @> '["etiqueta"]'
        conditions.append(Contact.tags.contains([tag]))

    total = (
        await db.execute(select(func.count()).select_from(Contact).where(*conditions))
    ).scalar_one()

    stmt = (
        select(
            Contact,
            last_at_sq.c.last_at,
            func.coalesce(msg_count_sq.c.cnt, 0),
            func.coalesce(usage_count_sq.c.cnt, 0),
        )
        .outerjoin(last_at_sq, last_at_sq.c.contact_id == Contact.id)
        .outerjoin(msg_count_sq, msg_count_sq.c.contact_id == Contact.id)
        .outerjoin(usage_count_sq, usage_count_sq.c.contact_id == Contact.id)
        .where(*conditions)
        .order_by(last_at_sq.c.last_at.desc().nullslast(), Contact.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()

    items = [
        ContactOut(
            id=contact.id,
            wa_id=contact.wa_id,
            name=contact.name,
            notes=contact.notes,
            is_active=contact.is_active,
            created_at=contact.created_at,
            last_interaction_at=last_at,
            messages_count=int(messages),
            interactions_count=int(interactions),
            tags=list(contact.tags or []),
            email=contact.email,
            address=contact.address,
        )
        for contact, last_at, messages, interactions in rows
    ]
    return items, total


async def get_contact(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID,
) -> ContactDetail | None:
    """Ficha del cliente con sus mensajes recientes."""
    result = await db.execute(
        select(Contact).where(
            Contact.tenant_id == tenant_id, Contact.id == contact_id
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        return None

    messages = (
        (
            await db.execute(
                select(Message)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.contact_id == contact_id,
                )
                .order_by(Message.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )

    interactions = (
        await db.execute(
            select(func.count(ServiceUsage.id)).where(
                ServiceUsage.tenant_id == tenant_id,
                ServiceUsage.contact_id == contact_id,
            )
        )
    ).scalar_one()

    return ContactDetail(
        id=contact.id,
        wa_id=contact.wa_id,
        name=contact.name,
        notes=contact.notes,
        is_active=contact.is_active,
        created_at=contact.created_at,
        last_interaction_at=None,
        messages_count=len(messages),
        interactions_count=int(interactions),
        recent_messages=list(messages),
        tags=list(contact.tags or []),
        email=contact.email,
        address=contact.address,
    )


async def list_contact_messages(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    skip: int,
    limit: int,
) -> tuple[list[Message], int] | None:
    """Historial paginado del cliente a través de todos sus hilos.

    Más reciente primero (el panel muestra burbujas y carga hacia atrás).
    None si el contacto no existe o no pertenece al tenant.
    """
    contact = (
        await db.execute(
            select(Contact).where(
                Contact.tenant_id == tenant_id, Contact.id == contact_id
            )
        )
    ).scalar_one_or_none()
    if contact is None:
        return None

    base = (
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id == tenant_id, Conversation.contact_id == contact_id)
    )
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    messages = (
        (
            await db.execute(
                base.order_by(Message.created_at.desc(), Message.id.desc())
                .offset(skip)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(messages), int(total)


async def update_contact(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    data: ContactUpdate,
) -> Contact | None:
    """Actualiza nombre, notas o estado del cliente."""
    result = await db.execute(
        select(Contact).where(
            Contact.tenant_id == tenant_id, Contact.id == contact_id
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        return None

    if data.name is not None:
        contact.name = data.name.strip() or None
    if data.notes is not None:
        contact.notes = data.notes.strip() or None
    if data.is_active is not None:
        contact.is_active = data.is_active
    if data.tags is not None:
        contact.tags = data.tags or None
    if data.email is not None:
        contact.email = data.email.strip() or None
    if data.address is not None:
        contact.address = data.address.strip() or None

    await db.commit()
    await db.refresh(contact)
    return contact


async def deactivate_contact(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID,
) -> bool:
    """Retiro suave del cliente: conserva su historial (Ley 1581)."""
    result = await db.execute(
        select(Contact).where(
            Contact.tenant_id == tenant_id, Contact.id == contact_id
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        return False
    contact.is_active = False
    await db.commit()
    return True


# ── Mini CRM: etiquetas y notas por cliente ─────────────────────────────────


async def list_distinct_tags(db: AsyncSession, *, tenant_id: UUID) -> list[str]:
    """Etiquetas distintas usadas por el tenant (para el filtro del panel)."""
    rows = await db.execute(
        select(func.jsonb_array_elements_text(Contact.tags).distinct()).where(
            Contact.tenant_id == tenant_id, Contact.tags.is_not(None)
        )
    )
    return sorted(str(r[0]) for r in rows.all())


async def _get_contact_owned(
    db: AsyncSession, *, tenant_id: UUID, contact_id: UUID
) -> Contact | None:
    return (
        await db.execute(
            select(Contact).where(
                Contact.tenant_id == tenant_id, Contact.id == contact_id
            )
        )
    ).scalar_one_or_none()


async def list_contact_notes(
    db: AsyncSession, *, tenant_id: UUID, contact_id: UUID
) -> list[Note] | None:
    """Notas activas del cliente (más recientes primero). None si no es suyo."""
    if await _get_contact_owned(db, tenant_id=tenant_id, contact_id=contact_id) is None:
        return None
    return list(
        (
            await db.execute(
                select(Note)
                .where(
                    Note.tenant_id == tenant_id,
                    Note.contact_id == contact_id,
                    Note.is_active.is_(True),
                )
                .order_by(Note.created_at.desc())
            )
        ).scalars().all()
    )


async def create_contact_note(
    db: AsyncSession, *, tenant_id: UUID, contact_id: UUID, content: str
) -> Note | None:
    """Nueva nota ligada al cliente. None si el contacto no es del tenant."""
    if await _get_contact_owned(db, tenant_id=tenant_id, contact_id=contact_id) is None:
        return None
    note = Note(
        tenant_id=tenant_id,
        contact_id=contact_id,
        content=content.strip()[:2000],
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def delete_contact_note(
    db: AsyncSession, *, tenant_id: UUID, contact_id: UUID, note_id: UUID
) -> bool:
    """Borrado lógico de una nota del cliente (spec §13: recuperable)."""
    note = (
        await db.execute(
            select(Note).where(
                Note.tenant_id == tenant_id,
                Note.id == note_id,
                Note.contact_id == contact_id,
                Note.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if note is None:
        return False
    note.is_active = False
    await db.commit()
    return True


async def list_contact_quotes(
    db: AsyncSession, *, tenant_id: UUID, contact_id: UUID, limit: int = 10
) -> list[Quote] | None:
    """Cotizaciones del cliente (más recientes primero). None si no es suyo."""
    if await _get_contact_owned(db, tenant_id=tenant_id, contact_id=contact_id) is None:
        return None
    return list(
        (
            await db.execute(
                select(Quote)
                .where(Quote.tenant_id == tenant_id, Quote.contact_id == contact_id)
                .order_by(Quote.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
    )
