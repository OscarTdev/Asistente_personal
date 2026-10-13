from contextlib import asynccontextmanager

from fastapi import FastAPI

import logging

from app.api import ws
from app.api.v1 import api_router

logger = logging.getLogger(__name__)


async def _followup_loop() -> None:
    """Seguimiento programado: una ronda por hora (ARQ en producción)."""
    import asyncio

    from sqlalchemy import select

    from app.core.database import SessionFactory
    from app.services.followup import run_followups, tenants_with_service

    await asyncio.sleep(120)  # arranque en frío: da tiempo a que todo suba
    while True:
        try:
            async with SessionFactory() as db:
                if await tenants_with_service(db):
                    result = await run_followups(db)
                    if result.round1_sent or result.round2_sent or result.errors:
                        logger.info(
                            "Seguimiento programado: r1=%s r2=%s err=%s",
                            result.round1_sent,
                            result.round2_sent,
                            result.errors,
                        )
        except Exception:
            logger.exception("Falló la ronda programada de seguimiento")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    task = asyncio.create_task(_followup_loop())
    yield
    task.cancel()


app = FastAPI(title="Asistente Personal API", lifespan=lifespan)

app.include_router(api_router, prefix="/api/v1")
app.include_router(ws.router)

@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import sys

    import uvicorn

    loop = "asyncio:SelectorEventLoop" if sys.platform == "win32" else "auto"
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True, loop=loop)
