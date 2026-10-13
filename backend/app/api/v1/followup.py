"""Router del seguimiento de cotizaciones: pendientes y ejecución manual."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.channels import get_channel
from app.core.database import get_db
from app.models import Contact, FollowUp, Message, Quote, TenantModule, User
from app.schemas.followup import FollowUpPendingItem, FollowUpPendingPage, FollowUpRunResult
from app.services.followup import run_followups

logger = logging.getLogger(__name__)
router = APIRouter()


async def _service_enabled(db: AsyncSession, tenant_id: UUID) -> bool:
    result = await db.execute(
        select(TenantModule.is_enabled).where(
            TenantModule.tenant_id == tenant_id,
            TenantModule.module_key == "follow_up",
        )
    )
    return bool(result.scalar_one_or_none())


@router.get("/pending", response_model=FollowUpPendingPage)
async def pending_quotes(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FollowUpPendingPage:
    """Cotizaciones enviadas con su estado de seguimiento (incluye respondidas)."""
    tenant_id = current_user.tenant_id

    total = (
        await db.execute(
            select(func.count())
            .select_from(Quote)
            .where(Quote.tenant_id == tenant_id, Quote.status == "sent")
        )
    ).scalar_one()

    quotes = (
        (
            await db.execute(
                select(Quote)
                .where(Quote.tenant_id == tenant_id, Quote.status == "sent")
                .order_by(Quote.created_at.asc())
                .offset(skip)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    now = datetime.now(UTC)
    items: list[FollowUpPendingItem] = []
    for quote in quotes:
        contact = (
            await db.execute(select(Contact).where(Contact.id == quote.contact_id))
        ).scalar_one_or_none() if quote.contact_id else None
        follow_ups = (
            await db.execute(select(FollowUp).where(FollowUp.quote_id == quote.id))
        ).scalars().all()
        rounds = {follow_up.round: follow_up for follow_up in follow_ups}

        replied_row = (
            await db.execute(
                select(func.count()).select_from(Message).where(
                    Message.conversation_id == quote.conversation_id,
                    Message.direction == "in",
                    Message.created_at > quote.created_at,
                )
            )
        ).scalar_one()

        items.append(
            FollowUpPendingItem(
                quote_id=quote.id,
                contact_name=contact.name if contact else None,
                contact_wa_id=contact.wa_id if contact else "—",
                total=str(quote.total),
                sent_at=quote.created_at,
                days_elapsed=(now - quote.created_at).days,
                round1_sent_at=rounds[1].created_at if 1 in rounds else None,
                round2_sent_at=rounds[2].created_at if 2 in rounds else None,
                replied=replied_row > 0,
            )
        )

    return FollowUpPendingPage(items=items, total=total)


@router.post("/run", response_model=FollowUpRunResult)
async def run_now(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> FollowUpRunResult:
    """Ejecuta una ronda de seguimiento AHORA para este tenant."""
    if not await _service_enabled(db, current_user.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El servicio de seguimiento está apagado. Enciéndelo en Servicios.",
        )
    return await run_followups(
        db, tenant_ids=[current_user.tenant_id], channel=get_channel("evolution")
    )
