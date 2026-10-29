"""Ultimos mensajes del tenant personal: quien escribe y que responde."""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import text

from app.core.database import engine


def safe(v) -> str:
    return str(v).encode("ascii", "ignore").decode("ascii")


async def main() -> None:
    async with engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    text("""
                        SELECT m.direction, m.whatsapp_message_id, m.content,
                               m.created_at, c.name AS contact_name, c.wa_id AS contact_wa
                        FROM messages m
                        JOIN conversations cv ON cv.id = m.conversation_id
                        JOIN contacts c ON c.id = cv.contact_id
                        JOIN tenants t ON t.id = m.tenant_id
                        WHERE t.slug = 'personal'
                        ORDER BY m.created_at DESC LIMIT 14
                    """)
                )
            )
            .mappings()
            .all()
        )
        for r in rows:
            print(safe({k: r[k] for k in r}))
    await engine.dispose()


asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
