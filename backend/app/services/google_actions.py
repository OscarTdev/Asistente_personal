"""Acciones de Google Workspace de alto nivel (spec §15).

Junta las tres piezas: la conexión OAuth del tenant (google_oauth),
el cliente REST (google_api) y los datos del negocio (gastos, citas,
contactos). La usan tanto la API del panel como el orquestador del
chat; así la lógica de negocio vive en un solo lugar.

Regla de producto: enviar un correo a un tercero es irreversible → el
orquestador lo pasa por PendingAction y pide «sí» antes de llamar a
send_email de aquí (spec §8.1).
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Expense, GoogleConnection, Quote, Tenant
from app.services import google_api, google_oauth
from app.services.expenses import _format_cop, monthly_summary

logger = logging.getLogger(__name__)

_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _colombia(dt: datetime) -> datetime:
    """UTC-5 fijo: Colombia no tiene horario de verano."""
    return dt - timedelta(hours=5)


def _month_name(now: datetime) -> str:
    return f"{_MESES[now.month - 1]} {now.year}"


async def connection_status(db: AsyncSession, *, tenant_id: UUID) -> dict:
    """Estado de la conexión del tenant (para el panel y el router)."""
    conn = (
        await db.execute(
            select(GoogleConnection).where(GoogleConnection.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    return {
        "configured": google_oauth.google_configured(),
        "connected": bool(conn and conn.is_active),
        "google_email": conn.google_email if conn and conn.is_active else None,
        "scopes": conn.scopes if conn else [],
    }


async def summarize_inbox(
    db: AsyncSession, *, tenant_id: UUID, max_results: int = 5
) -> list[dict]:
    """Los correos más recientes de la bandeja del dueño."""
    token = await google_oauth.get_access_token(db, tenant_id=tenant_id)
    return await google_api.gmail_recent_messages(token, max_results=max_results)


async def send_email(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    to: str,
    subject: str,
    body: str,
) -> None:
    """Envía un correo DESDE la cuenta Google del dueño."""
    token = await google_oauth.get_access_token(db, tenant_id=tenant_id)
    conn = await google_oauth.get_connection(db, tenant_id=tenant_id)
    await google_api.gmail_send(
        token,
        to=to,
        subject=subject,
        body=body,
        sender=conn.google_email if conn else None,
    )


async def upcoming_events(
    db: AsyncSession, *, tenant_id: UUID, days: int = 7
) -> list[dict]:
    """Eventos del calendario del dueño entre ahora y N días."""
    token = await google_oauth.get_access_token(db, tenant_id=tenant_id)
    now = datetime.now(UTC)
    return await google_api.calendar_events(
        token,
        time_min=now.isoformat(),
        time_max=(now + timedelta(days=days)).isoformat(),
        max_results=10,
    )


async def create_event(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    summary: str,
    start_at: datetime,
    duration_minutes: int = 60,
    description: str | None = None,
) -> dict:
    """Agenda un evento en el calendario principal del dueño."""
    token = await google_oauth.get_access_token(db, tenant_id=tenant_id)
    end_at = start_at + timedelta(minutes=duration_minutes)
    return await google_api.calendar_create_event(
        token,
        summary=summary,
        start_iso=start_at.isoformat(),
        end_iso=end_at.isoformat(),
        description=description,
    )


async def export_expenses_sheet(
    db: AsyncSession, *, tenant: Tenant
) -> dict:
    """Exporta los gastos del mes a una hoja de cálculo nueva."""
    now = datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)

    rows = (
        await db.execute(
            select(Expense)
            .where(
                Expense.tenant_id == tenant.id,
                Expense.expense_date >= start,
                Expense.expense_date < end,
            )
            .order_by(Expense.expense_date.asc())
        )
    ).scalars().all()

    values = [["Fecha", "Descripción", "Categoría", "Valor (COP)"]]
    total = 0
    for e in rows:
        values.append(
            [
                _colombia(e.expense_date).strftime("%d/%m/%Y"),
                e.description,
                e.category,
                f"{e.amount}",
            ]
        )
        total += int(e.amount)
    values.append(["", "", "TOTAL", f"{total}"])

    token = await google_oauth.get_access_token(db, tenant_id=tenant.id)
    sheet = await google_api.sheets_create_spreadsheet(
        token, title=f"Gastos {_month_name(now)} — {tenant.name}"
    )
    await google_api.sheets_write_values(
        token, spreadsheet_id=sheet["spreadsheet_id"], values=values
    )
    return {"url": sheet["url"], "title": sheet["title"], "rows": len(rows)}


async def create_month_report_doc(
    db: AsyncSession, *, tenant: Tenant
) -> dict:
    """Informe del mes en un documento nuevo (gastos + cotizaciones)."""
    now = datetime.now(UTC)
    month_name = _month_name(now)

    # Gastos del mes por categoría
    summary = await monthly_summary(db, tenant_id=tenant.id, month=now)
    lines = [
        f"Informe de {month_name} — {tenant.name}",
        "",
        "Gastos del mes",
        "-------------",
    ]
    if summary["categories"]:
        for category, data in summary["categories"].items():
            lines.append(
                f"• {category}: {_format_cop(data['total'])} ({data['count']} gastos)"
            )
        lines.append(f"TOTAL: {_format_cop(summary['total'])}")
    else:
        lines.append("Sin gastos registrados este mes.")

    # Cotizaciones del mes
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    quote_rows = (
        await db.execute(
            select(Quote.status, func.count())
            .where(
                Quote.tenant_id == tenant.id,
                Quote.created_at >= start,
                Quote.created_at < end,
            )
            .group_by(Quote.status)
        )
    ).all()
    lines += ["", "Cotizaciones del mes", "-------------------"]
    if quote_rows:
        for status, count in quote_rows:
            lines.append(f"• {status}: {count}")
    else:
        lines.append("Sin cotizaciones este mes.")

    text = "\n".join(lines)
    token = await google_oauth.get_access_token(db, tenant_id=tenant.id)
    doc = await google_api.docs_create_document(
        token, title=f"Informe {month_name} — {tenant.name}"
    )
    await google_api.docs_insert_text(
        token, document_id=doc["document_id"], text=text
    )
    return {"url": doc["url"], "title": doc["title"]}


async def drive_recent_files(
    db: AsyncSession, *, tenant_id: UUID, max_results: int = 10
) -> list[dict]:
    """Archivos recientes del Drive del dueño."""
    token = await google_oauth.get_access_token(db, tenant_id=tenant_id)
    return await google_api.drive_list_files(token, max_results=max_results)


async def create_satisfaction_survey(
    db: AsyncSession, *, tenant: Tenant
) -> dict:
    """Encuesta de satisfacción lista para compartir con clientes."""
    token = await google_oauth.get_access_token(db, tenant_id=tenant.id)
    return await google_api.forms_create_satisfaction_survey(
        token,
        title=f"¿Qué tal tu experiencia con {tenant.name}?",
        business_name=tenant.name,
    )
