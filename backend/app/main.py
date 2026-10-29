import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ws
from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.database import engine

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

                # 2) Mantenimientos preventivos vencidos
                from app.channels import get_channel
                from app.services.maintenance import send_maintenance_reminders
                mt_sent = await send_maintenance_reminders(
                    db, channel=get_channel("evolution")
                )
                if mt_sent:
                    logger.info("Mantenimientos enviados: %d", mt_sent)

                # 3) Recordatorios: principal + pre-notificaciones (2h y 30min antes)
                for reminder, notif_type in await due_reminders(db):
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

                        # Mensaje según tipo de notificación
                        if notif_type == "2h":
                            msg = f"⏰ Recordatorio en 2 horas: {reminder.content}"
                        elif notif_type == "30m":
                            msg = f"⏰ Recordatorio en 30 minutos: {reminder.content}"
                        else:  # main
                            msg = f"⏰ Recordatorio: {reminder.content}"

                        await channel.send_text(owner_contact.wa_id, msg)
                        await mark_reminder_sent(db, reminder, notif_type)
                        logger.info(
                            "Recordatorio %s enviado tipo %s (tenant %s)",
                            reminder.id, notif_type, tenant.slug,
                        )
                    except Exception:
                        logger.exception(
                            "No se pudo enviar el recordatorio %s", reminder.id
                        )

                # 4) Resumen diario proactivo (adendo: el módulo que hace
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


async def _guardian_loop() -> None:
    """Guardián LLM: monitorea salud de proveedores IA cada 10 min."""
    import asyncio

    from app.core.database import SessionFactory
    from app.workers.guardian import guardian_task

    await asyncio.sleep(240)  # arranque en frío: da tiempo a que todo suba
    while True:
        try:
            async with SessionFactory():
                # Simular contexto ARQ
                ctx = {}
                result = await guardian_task(ctx)
                if result.get("applied"):
                    logger.info("🛡️ Guardián aplicó cambios: %s", result["applied"])
                elif result.get("status") == "completed":
                    logger.debug("🛡️ Guardián: chequeo OK, sin acciones")
        except Exception:
            logger.exception("Falló el ciclo del guardián IA")
        await asyncio.sleep(600)  # cada 10 minutos


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    # Verificar sincronización NTP sin bloquear el arranque (los
    # servidores NTP pueden tardar hasta 20s si hay firewall).
    from app.services.ntp_sync import sync_system_time_if_needed
    ntp_task = asyncio.create_task(sync_system_time_if_needed())

    task = asyncio.create_task(_followup_loop())
    subscriptions_task = asyncio.create_task(_subscriptions_loop())
    guardian_task = asyncio.create_task(_guardian_loop())
    yield
    ntp_task.cancel()
    task.cancel()
    subscriptions_task.cancel()
    guardian_task.cancel()


app = FastAPI(title="Asistente Personal API", lifespan=lifespan)

# CORS: permitir panel local y túneles (ngrok, cloudflared)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.panel_base_url,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=r"https://.*\.ngrok-free\.app|https://.*\.trycloudflare\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(ws.router)


@app.get("/health")
async def health():
    """Health check real: verifica DB y Redis."""
    from redis.asyncio import Redis, from_url
    from sqlalchemy import text

    from app.core.config import get_settings

    # Check DB
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        print(f"DB error: {e}")
        db_ok = False

    # Check Redis
    try:
        redis: Redis = from_url(get_settings().redis_url, decode_responses=True)
        try:
            result = await redis.ping()
            print(f"Redis ping result: {result}")
            redis_ok = True
        finally:
            await redis.aclose()
    except Exception as e:
        print(f"Redis error: {e}")
        redis_ok = False

    status = "ok" if db_ok and redis_ok else "degraded"
    return {
        "status": status,
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }


if __name__ == "__main__":
    import sys

    import uvicorn

    loop = "asyncio:SelectorEventLoop" if sys.platform == "win32" else "auto"
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True, loop=loop)
