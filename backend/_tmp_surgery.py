"""Cirugia de datos (sin borrados): registrar el telefono del bot
(573012110405) como owner del tenant personal para que el auto-chat
(Message Yourself) funcione.

Todo son INSERT/UPDATE reversibles; ningun dato se destruye:
1. Cerrar (is_active=false) la sesion de onboarding de Niurka.
2. Desactivar el contacto Niurka del tenant plataforma (queda como historico).
3. Re-apuntar la identidad existente (whatsapp, 573012110405) de
   plataforma/contact → personal/owner y su nuevo contacto.
4. Crear el contacto del movil del bot en el tenant personal.

El tenant.wa_id NO se toca: los envios proactivos (resumen diario,
recordatorios, mantenimientos) siguen al telefono personal de Oscar.
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select, text

from app.core.database import SessionFactory
from app.models import ChannelIdentity, Contact, OnboardingSession, Tenant

BOT_WA = "573012110405"


def safe(v) -> str:
    return str(v).encode("ascii", "ignore").decode("ascii")


async def main() -> None:
    async with SessionFactory() as db:
        personal = (
            await db.execute(select(Tenant).where(Tenant.slug == "personal"))
        ).scalar_one()
        plataforma = (
            await db.execute(select(Tenant).where(Tenant.slug == "plataforma"))
        ).scalar_one()

        niurka = (
            await db.execute(
                select(Contact).where(
                    Contact.tenant_id == plataforma.id,
                    Contact.wa_id == BOT_WA,
                )
            )
        ).scalar_one()
        print(
            "Antes - Niurka:",
            safe({"id": niurka.id, "name": niurka.name,
                  "is_active": niurka.is_active,
                  "onboarding_state": niurka.onboarding_state}),
        )

        # ── 1. Cerrar onboarding de Niurka (UPDATE) ─────────────────────────
        sessions = (
            await db.execute(
                select(OnboardingSession).where(
                    OnboardingSession.contact_id == niurka.id,
                    OnboardingSession.is_active.is_(True),
                )
            )
        ).scalars().all()
        for s in sessions:
            s.is_active = False
        print(f"Sesiones de onboarding cerradas: {len(sessions)}")

        # ── 2. Desactivar contacto Niurka (UPDATE, historico) ───────────────
        niurka.is_active = False
        niurka.onboarding_state = None
        await db.flush()

        # ── 3. Contacto del movil del bot en personal (INSERT si falta) ────
        bot_contact = (
            await db.execute(
                select(Contact).where(
                    Contact.tenant_id == personal.id,
                    Contact.wa_id == BOT_WA,
                )
            )
        ).scalar_one_or_none()
        if bot_contact is None:
            bot_contact = Contact(
                tenant_id=personal.id,
                wa_id=BOT_WA,
                name="Aura (móvil del bot)",
            )
            db.add(bot_contact)
            await db.flush()
            print("Contacto creado:", safe(bot_contact.id))
        else:
            print("Contacto ya existia:", safe(bot_contact.id))
            bot_contact.is_active = True

        # ── 4. Re-apuntar la identidad existente (UPDATE) ──────────────────
        identity = (
            await db.execute(
                select(ChannelIdentity).where(
                    ChannelIdentity.channel == "whatsapp",
                    ChannelIdentity.external_id == BOT_WA,
                )
            )
        ).scalar_one()
        print(
            "Antes - identidad:",
            safe({"kind": identity.kind, "tenant": identity.tenant_id,
                  "contact": identity.contact_id}),
        )
        identity.kind = "owner"
        identity.tenant_id = personal.id
        identity.contact_id = bot_contact.id
        await db.flush()

        await db.commit()

        # ── Verificación post-cirugía ──────────────────────────────────────
        rows = (
            (
                await db.execute(
                    text("""
                        SELECT ci.external_id, ci.kind, t.slug, c.name, c.wa_id,
                               c.is_active
                        FROM channel_identities ci
                        JOIN tenants t ON t.id = ci.tenant_id
                        JOIN contacts c ON c.id = ci.contact_id
                        WHERE ci.external_id = :wa
                    """),
                    {"wa": BOT_WA},
                )
            )
            .mappings()
            .all()
        )
        print("\nDespues - identidad de", BOT_WA, ":")
        for r in rows:
            print(safe(dict(r)))
        print("\nDespues - contacto Niurka:")
        await db.refresh(niurka)
        print(safe({"is_active": niurka.is_active,
                    "onboarding_state": niurka.onboarding_state}))


asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
