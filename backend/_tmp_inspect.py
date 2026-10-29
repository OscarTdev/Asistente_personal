"""Inspeccion de datos antes de la cirugia de identidades (solo lectura)."""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import text

from app.core.database import engine as _engine


def get_engine():
    return _engine


def safe(v) -> str:
    return str(v).encode("ascii", "ignore").decode("ascii")


async def q(engine, sql: str, params: dict | None = None):
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), params or {})).mappings().all()
        return [dict(r) for r in rows]


async def main() -> None:
    engine = get_engine()
    try:
        tenants = await q(engine, """
            SELECT id, slug, name, wa_id, bot_name, plan, customer_mode,
                   is_platform, is_active
            FROM tenants WHERE slug IN ('plataforma', 'personal')
        """)
        print("== TENANTS ==")
        for t in tenants:
            print(safe(t))

        print("\n== IDENTITIES (573012110405 / 573043223100 / LID) ==")
        ids = await q(engine, """
            SELECT ci.id, ci.channel, ci.external_id, ci.kind, ci.tenant_id,
                   t.slug AS tenant_slug, ci.contact_id, c.name AS contact_name,
                   c.wa_id AS contact_wa_id, ci.created_at
            FROM channel_identities ci
            LEFT JOIN tenants t ON t.id = ci.tenant_id
            LEFT JOIN contacts c ON c.id = ci.contact_id
            WHERE ci.external_id IN ('573012110405', '573043223100')
               OR ci.external_id LIKE '%%@lid'
            ORDER BY ci.created_at
        """)
        for i in ids:
            print(safe(i))

        print("\n== CONTACTS con esos numeros o LID ==")
        cs = await q(engine, """
            SELECT id, tenant_id, name, wa_id, is_active, onboarding_state,
                   created_at
            FROM contacts
            WHERE wa_id IN ('573012110405', '573043223100')
               OR wa_id LIKE '%%@lid'
            ORDER BY created_at
        """)
        for c in cs:
            print(safe(c))

        print("\n== ONBOARDING SESSIONS activas ==")
        obs = await q(engine, """
            SELECT os.id, os.contact_id, c.name, t.slug,
                   os.step, os.is_active, os.expires_at, os.updated_at
            FROM onboarding_sessions os
            LEFT JOIN contacts c ON c.id = os.contact_id
            LEFT JOIN tenants t ON t.id = c.tenant_id
            WHERE os.is_active = true
            ORDER BY os.updated_at DESC LIMIT 10
        """)
        for o in obs:
            print(safe(o))

        print("\n== Mensaje LID del test (AC7F...) ==")
        m = await q(engine, """
            SELECT m.id, m.tenant_id, t.slug, m.direction, m.content,
                   m.whatsapp_message_id, m.created_at
            FROM messages m LEFT JOIN tenants t ON t.id = m.tenant_id
            WHERE m.whatsapp_message_id = 'AC7F4DB89E176E859398A7F55DD63A94'
        """)
        for r in m:
            print(safe(r))

        print("\n== Mensajes de prueba de hoy ==")
        ts = await q(engine, """
            SELECT m.id, m.tenant_id, t.slug, m.whatsapp_message_id, m.content,
                   m.created_at
            FROM messages m LEFT JOIN tenants t ON t.id = m.tenant_id
            WHERE m.whatsapp_message_id LIKE 'test_%%'
            ORDER BY m.created_at
        """)
        for r in ts:
            print(safe(r))

        print("\n== Reminder pendiente d061d836 ==")
        rem = await q(engine, """
            SELECT id, tenant_id, content, remind_at, status, sent_at
            FROM reminders WHERE id::text LIKE 'd061d836%%'
        """)
        for r in rem:
            print(safe(r))

        print("\n== Ultimos mensajes out del tenant personal (verificar envios) ==")
        outs = await q(engine, """
            SELECT m.whatsapp_message_id, m.content, m.status, m.created_at
            FROM messages m JOIN tenants t ON t.id = m.tenant_id
            WHERE t.slug = 'personal' AND m.direction = 'out'
            ORDER BY m.created_at DESC LIMIT 8
        """)
        for r in outs:
            print(safe(r))
    finally:
        await engine.dispose()


asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
