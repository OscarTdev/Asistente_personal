"""Resolución de identidades de canal: quién escribe → su núcleo.

El núcleo del asistente (conversaciones, notas, cotizaciones,
recordatorios, catálogo) vive en la BD ligado al contacto del tenant.
Esta pieza traduce una identidad de canal («+573001112233 en WhatsApp»,
«@jgomez en Telegram», «user-42 en la app») a ese núcleo: el mismo humano
por cualquier puerta es el mismo usuario y no pierde nada al cambiar.

Orden de resolución:
1. Identidad registrada en `channel_identities` → su contacto y tenant.
2. Legado de WhatsApp, con creación perezosa: si el número es el wa_id de
   un tenant (dueño) o de un contacto conocido (cliente), se crea la
   identidad para que la próxima resolución vaya directo.
3. Desconocido en cualquier canal → contacto nuevo en el tenant de
   fallback (prospecto: el orquestador decide onboarding o silencio).
"""

import logging
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChannelIdentity, Contact, Tenant

logger = logging.getLogger(__name__)

KIND_OWNER = "owner"
KIND_CONTACT = "contact"


class ResolvedIdentity(NamedTuple):
    """El núcleo detrás de una identidad de canal."""

    tenant: Tenant
    contact: Contact
    is_owner: bool
    created: bool  # ¿el contacto se creó en esta resolución? (prospecto)


async def _get_or_create_contact(
    db: AsyncSession,
    *,
    tenant: Tenant,
    external_id: str,
    display_name: str | None,
) -> tuple[Contact, bool]:
    """Get-or-create del contacto del tenant para esta identidad."""
    contact = (
        await db.execute(
            select(Contact).where(
                Contact.tenant_id == tenant.id,
                Contact.wa_id == external_id,
            )
        )
    ).scalar_one_or_none()
    if contact is not None:
        if display_name and contact.name is None:
            contact.name = display_name
        return contact, False

    contact = Contact(
        tenant_id=tenant.id,
        wa_id=external_id,  # el identificador externo como teléfono/nombre
        name=display_name,
    )
    db.add(contact)
    await db.flush()
    return contact, True


async def _register(
    db: AsyncSession,
    *,
    tenant: Tenant,
    contact: Contact,
    kind: str,
    channel: str,
    external_id: str,
) -> None:
    db.add(
        ChannelIdentity(
            tenant_id=tenant.id,
            contact_id=contact.id,
            kind=kind,
            channel=channel,
            external_id=external_id,
        )
    )
    await db.flush()


async def resolve_identity(
    db: AsyncSession,
    *,
    channel: str,
    external_id: str,
    fallback_tenant: Tenant,
    display_name: str | None = None,
    alias_external_id: str | None = None,
) -> ResolvedIdentity:
    """Traduce una identidad de canal a su núcleo (tenant + contacto).

    alias_external_id: identidad alternativa del MISMO humano (p. ej. el
    LID de WhatsApp, que algunos chats usan en lugar del teléfono). Si la
    identidad real no existe pero la alias sí, sus llaves se migran al
    identificador real: el LID es interno de WhatsApp; el teléfono es la
    identidad estable.
    """
    identity = (
        await db.execute(
            select(ChannelIdentity).where(
                ChannelIdentity.channel == channel,
                ChannelIdentity.external_id == external_id,
            )
        )
    ).scalar_one_or_none()
    if identity is None and alias_external_id and alias_external_id != external_id:
        identity = (
            await db.execute(
                select(ChannelIdentity).where(
                    ChannelIdentity.channel == channel,
                    ChannelIdentity.external_id == alias_external_id,
                )
            )
        ).scalar_one_or_none()
        if identity is not None:
            identity.external_id = external_id
            await db.flush()
            # Sin el teléfono real en logs — dato personal (Ley 1581);
            # el LID es un identificador interno y puede quedar.
            logger.info(
                "Identidad %s/%s migrada al identificador real",
                channel,
                alias_external_id,
            )
    if identity is not None:
        contact = (
            await db.execute(
                select(Contact).where(Contact.id == identity.contact_id)
            )
        ).scalar_one()
        tenant = (
            await db.execute(select(Tenant).where(Tenant.id == identity.tenant_id))
        ).scalar_one()
        return ResolvedIdentity(
            tenant=tenant,
            contact=contact,
            is_owner=identity.kind == KIND_OWNER,
            created=False,
        )

    # 2) Legado de WhatsApp: identidades se crean perezosamente
    if channel == "whatsapp":
        owner_tenant = (
            await db.execute(
                select(Tenant).where(
                    Tenant.wa_id == external_id, Tenant.is_active.is_(True)
                )
            )
        ).scalar_one_or_none()
        if owner_tenant is not None:
            contact, created = await _get_or_create_contact(
                db,
                tenant=owner_tenant,
                external_id=external_id,
                display_name=display_name,
            )
            await _register(
                db,
                tenant=owner_tenant,
                contact=contact,
                kind=KIND_OWNER,
                channel=channel,
                external_id=external_id,
            )
            return ResolvedIdentity(
                tenant=owner_tenant, contact=contact, is_owner=True, created=created
            )

        known_contacts = (
            (
                await db.execute(
                    select(Contact)
                    .where(Contact.wa_id == external_id, Contact.is_active.is_(True))
                    .order_by(Contact.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        if known_contacts:
            contact = known_contacts[0]
            owner_tenant = (
                await db.execute(select(Tenant).where(Tenant.id == contact.tenant_id))
            ).scalar_one()
            await _register(
                db,
                tenant=owner_tenant,
                contact=contact,
                kind=KIND_CONTACT,
                channel=channel,
                external_id=external_id,
            )
            return ResolvedIdentity(
                tenant=owner_tenant, contact=contact, is_owner=False, created=False
            )

        # Puente LID: contacto legado creado con el LID como wa_id (antes del
        # fix del LID no se podía responderle). Migra su llave al teléfono
        # real y conserva su historial.
        if alias_external_id and alias_external_id != external_id:
            alias_contact = (
                await db.execute(
                    select(Contact)
                    .where(
                        Contact.wa_id == alias_external_id,
                        Contact.is_active.is_(True),
                    )
                    .order_by(Contact.created_at.desc())
                )
            ).scalars().first()
            if alias_contact is not None:
                alias_contact.wa_id = external_id
                owner_tenant = (
                    await db.execute(
                        select(Tenant).where(Tenant.id == alias_contact.tenant_id)
                    )
                ).scalar_one()
                await _register(
                    db,
                    tenant=owner_tenant,
                    contact=alias_contact,
                    kind=KIND_CONTACT,
                    channel=channel,
                    external_id=external_id,
                )
                logger.info(
                    "Contacto legado %s migrado del LID al teléfono real",
                    alias_contact.id,
                )
                return ResolvedIdentity(
                    tenant=owner_tenant,
                    contact=alias_contact,
                    is_owner=False,
                    created=False,
                )

    # 3) Desconocido en cualquier canal: prospecto en el tenant fallback
    contact, created = await _get_or_create_contact(
        db,
        tenant=fallback_tenant,
        external_id=external_id,
        display_name=display_name,
    )
    await _register(
        db,
        tenant=fallback_tenant,
        contact=contact,
        kind=KIND_CONTACT,
        channel=channel,
        external_id=external_id,
    )
    return ResolvedIdentity(
        tenant=fallback_tenant, contact=contact, is_owner=False, created=created
    )


async def link_identity(
    db: AsyncSession,
    *,
    tenant: Tenant,
    contact: Contact,
    kind: str,
    channel: str,
    external_id: str,
) -> ChannelIdentity:
    """Vincula una identidad nueva a un contacto (p. ej. su Telegram)."""
    identity = ChannelIdentity(
        tenant_id=tenant.id,
        contact_id=contact.id,
        kind=kind,
        channel=channel,
        external_id=external_id,
    )
    db.add(identity)
    await db.flush()
    logger.info(
        "Identidad %s/%s vinculada al contacto %s (%s)",
        channel,
        external_id,
        contact.id,
        kind,
    )
    return identity


async def clear_identities(
    db: AsyncSession, *, channel: str, external_id: str
) -> int:
    """Borra las identidades de un identificador externo (un canal).

    Caso onboarding: al completar su registro, el prospecto deja de ser el
    contacto-puerta del tenant de la plataforma y se convierte en dueño de
    su propio tenant. Sin esto, su identidad perezosa de prospecto lo
    seguiría routeando al tenant equivocado.
    """
    rows = (
        await db.execute(
            select(ChannelIdentity).where(
                ChannelIdentity.channel == channel,
                ChannelIdentity.external_id == external_id,
            )
        )
    ).scalars().all()
    for row in rows:
        await db.delete(row)
    if rows:
        await db.flush()
        logger.info(
            "Identidades %s/%s limpiadas (%d): su dueño ya tiene tenant propio",
            channel,
            external_id,
            len(rows),
        )
    return len(rows)


async def identities_of_contact(
    db: AsyncSession, *, tenant_id: UUID, contact_id: UUID
) -> list[ChannelIdentity]:
    return list(
        (
            await db.execute(
                select(ChannelIdentity)
                .where(
                    ChannelIdentity.tenant_id == tenant_id,
                    ChannelIdentity.contact_id == contact_id,
                )
                .order_by(ChannelIdentity.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
