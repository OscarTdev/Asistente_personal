"""Isolated repro: async DB query through the app's own SessionFactory."""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import psycopg
from sqlalchemy import select

from app.core.database import SessionFactory
from app.models import User


async def main() -> None:
    # 1. Postgres connection census
    sync = psycopg.connect(
        "host=127.0.0.1 port=5433 dbname=asistente user=asistente password=asistente",
        connect_timeout=10,
    )
    rows = sync.execute(
        "select state, count(*) from pg_stat_activity group by state order by 2 desc"
    ).fetchall()
    total = sync.execute("select count(*) from pg_stat_activity").fetchone()[0]
    maxconn = sync.execute("show max_connections").fetchone()[0]
    print(f"pg_stat_activity total={total} max={maxconn} estados={rows}")
    sync.close()

    # 2. The app's async path with a hard timeout
    async def query() -> str:
        async with SessionFactory() as session:
            result = await session.execute(select(User).limit(1))
            user = result.scalars().first()
            return f"OK user={user.email}" if user else "OK (sin usuarios)"

    try:
        print(await asyncio.wait_for(query(), timeout=20))
    except asyncio.TimeoutError:
        print("TIMEOUT: la consulta async cuelga")


asyncio.run(main())
