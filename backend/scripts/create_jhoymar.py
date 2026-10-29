"""Crea el contacto Jhoymar en el tenant personal directamente.

El contacto no existe en la BD - el bot alucinó que lo creó vía _chat_reply.
Este script lo crea correctamente con ChannelIdentity para futuros mensajes.
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select, text

from app.core.database import SessionFactory
from app.models import ChannelIdentity, Contact, Conversation, Tenant

JH_WHAID = "57321933514"
JH_NAME = "Jhoymar"


async def main() -> None:
    async with SessionFactory() as db:
        personal = (
            await db.execute(select(Tenant).where(Tenant.slug == "personal"))
        ).scalar_one()

        # Verificar si ya existe en personal
        jh_personal = (
            await db.execute(
                select(Contact).where(
                    Contact.tenant_id == personal.id,
                    Contact.wa_id == JH_WHAID,
                )
            )
        ).scalar_one_or_none()

        if jh_personal is not None:
            print(f"[INFO] Jhoymar ya existe en personal: id={jh_personal.id}")
        else:
            # INSERT: crear en personal
            jh_personal = Contact(
                tenant_id=personal.id,
                wa_id=JH_WHAID,
                name=JH_NAME,
                notes="Cliente creado manualmente para seguimiento de obra",
                is_active=True,
                tags=["cliente", "obra"],
                email=None,
                address=None,
            )
            db.add(jh_personal)
            await db.flush()
            print(f"[OK] Contacto creado en personal: id={jh_personal.id}")

        # Crear Conversation asociada en personal
        conv = (
            await db.execute(
                select(Conversation).where(
                    Conversation.tenant_id == personal.id,
                    Conversation.contact_id == jh_personal.id,
                )
            )
        ).scalar_one_or_none()

        if conv is None:
            conv = Conversation(
                tenant_id=personal.id,
                contact_id=jh_personal.id,
            )
            db.add(conv)
            await db.flush()
            print(f"[OK] Conversation creada en personal: id={conv.id}")
        else:
            print(f"[INFO] Conversation ya existe en personal: id={conv.id}")

        # ChannelIdentity kind=contact en personal (para que futuros mensajes resuelvan a personal)
        identity = (
            await db.execute(
                select(ChannelIdentity).where(
                    ChannelIdentity.channel == "whatsapp",
                    ChannelIdentity.external_id == JH_WHAID,
                    ChannelIdentity.tenant_id == personal.id,
                )
            )
        ).scalar_one_or_none()

        if identity is None:
            identity = ChannelIdentity(
                channel="whatsapp",
                external_id=JH_WHAID,
                kind="contact",
                tenant_id=personal.id,
                contact_id=jh_personal.id,
            )
            db.add(identity)
            print("[OK] ChannelIdentity creada en personal")
        else:
            # Actualizar para asegurar que apunte al contacto correcto
            identity.kind = "contact"
            identity.contact_id = jh_personal.id
            print("[INFO] ChannelIdentity actualizada en personal")

        await db.commit()

        # Verificación final
        rows = (
            (
                await db.execute(
                    text("""
                        SELECT ci.external_id, ci.kind, t.slug as tenant, c.name, c.wa_id,
                               c.is_active, c.tenant_id
                        FROM channel_identities ci
                        JOIN tenants t ON t.id = ci.tenant_id
                        JOIN contacts c ON c.id = ci.contact_id
                        WHERE ci.external_id = :wa
                    """),
                    {"wa": JH_WHAID},
                )
            )
            .mappings()
            .all()
        )
        print(f"\n[LIST] Identidades para {JH_WHAID}:")
        for r in rows:
            print(
                f"  - {r['tenant']}: kind={r['kind']}, "
                f"contact={r['name']} ({r['wa_id']}), active={r['is_active']}"
            )


asyncio.run(main())