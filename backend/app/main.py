import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import ws
from app.api.v1 import api_router

logger = logging.getLogger(__name__)


async def _followup_loop() -> None:
    """Seguimiento programado: una ronda por hora (ARQ en producción)."""
    import asyncio

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


async def _subscriptions_loop() -> None:
    """Vence suscripciones premium, envía recordatorios y el resumen diario."""
    import asyncio

    from app.core.database import SessionFactory
    from app.services.entitlements import expire_subscriptions
    from app.services.notes import due_reminders, mark_reminder_sent

    await asyncio.sleep(180)  # arranque en frío
    _last_daily_summary = None  # fecha del último resumen enviado
    while True:
        try:
            async with SessionFactory() as db:
                # 1) Suscripciones vencidas
                expired = await expire_subscriptions(db)
                if expired:
                    logger.info("Suscripciones vencidas: %d", expired)

                # 2) Recordatorios que ya llegaron a su hora
                for reminder in await due_reminders(db):
                    try:
                        from sqlalchemy import select

                        from app.channels import get_channel
                        from app.models import Contact, Tenant

                        tenant = (
                            await db.execute(
                                select(Tenant).where(Tenant.id == reminder.tenant_id)
                            )
                        ).scalar_one()
                        # Buscar el contacto del dueño (wa_id del tenant)
                        if not tenant.wa_id:
                            continue
                        owner_contact = (
                            await db.execute(
                                select(Contact).where(
                                    Contact.tenant_id == tenant.id,
                                    Contact.wa_id == tenant.wa_id,
                                )
                            )
                        ).scalar_one_or_none()
                        if owner_contact is None:
                            continue

                        channel = get_channel("evolution")
                        await channel.send_text(
                            owner_contact.wa_id,
                            f"⏰ Recordatorio: {reminder.content}",
                        )
                        await mark_reminder_sent(db, reminder)
                        logger.info(
                            "Recordatorio %s enviado (tenant %s)",
                            reminder.id, tenant.slug,
                        )
                    except Exception:
                        logger.exception(
                            "No se pudo enviar el recordatorio %s", reminder.id
                        )

                # 3) Resumen diario proactivo (adendo: el módulo que hace
                #    volver al usuario) — solo una vez al día, en la mañana
                from datetime import UTC, datetime

                from app.services.daily_summary import send_daily_summaries

                now = datetime.now(UTC)
                # UTC-5 Colombia: 12:00 UTC = 7:00am. Ventana: 12-13 UTC.
                if (
                    12 <= now.hour < 13
                    and _last_daily_summary != now.date()
                ):
                    from app.channels import get_channel as _gc

                    sent = await send_daily_summaries(
                        db, channel=_gc("evolution")
                    )
                    if sent:
                        logger.info(
                            "Resumen diario enviado a %d negocios", sent
                        )
                    _last_daily_summary = now.date()
        except Exception:
            logger.exception("Falló el ciclo de suscripciones/recordatorios")
        await asyncio.sleep(300)  # cada 5 minutos


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    task = asyncio.create_task(_followup_loop())
    subscriptions_task = asyncio.create_task(_subscriptions_loop())
    yield
    task.cancel()
    subscriptions_task.cancel()


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
