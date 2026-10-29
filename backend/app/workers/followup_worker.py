"""Worker ARQ para follow-up programado."""
from arq import cron

from app.core.database import SessionFactory
from app.services.followup import run_followups, tenants_with_service


async def followup_task(ctx):
    async with SessionFactory() as db:
        if await tenants_with_service(db):
            result = await run_followups(db)
            return {
                "sent_r1": result.round1_sent,
                "sent_r2": result.round2_sent,
                "errors": result.errors,
            }
    return {"sent_r1": False, "sent_r2": False, "errors": 0}


# Registro ARQ (cron job) para Fase F
cron_job = cron(followup_task, name="followup_task", hour={0}, minute={0})
