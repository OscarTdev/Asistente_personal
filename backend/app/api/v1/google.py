"""Router de la integración con Google Workspace (spec §15).

El dueño conecta SU cuenta de Google desde el panel (Mi negocio →
Google) y desde ahí el asistente puede resumirle el correo, agendar
en su Calendar, exportar gastos a Sheets y generar informes en Docs.

Endpoints de conexión (admin del tenant):
    GET    /api/v1/google/status          → ¿conectado? ¿configurado?
    POST   /api/v1/google/authorize       → URL de consentimiento
    POST   /api/v1/google/callback        → canjea el code y guarda tokens
    DELETE /api/v1/google/disconnect      → revoca y borra

Endpoints de uso (admin del tenant):
    GET    /api/v1/google/gmail/summary         → correos recientes
    GET    /api/v1/google/calendar/upcoming     → agenda de N días
    POST   /api/v1/google/calendar/events       → agendar evento
    POST   /api/v1/google/sheets/export-expenses→ gastos del mes → hoja
    POST   /api/v1/google/docs/month-report     → informe del mes → doc
    GET    /api/v1/google/drive/files            → archivos recientes
    POST   /api/v1/google/forms/satisfaction-survey → encuesta de satisfacción
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.database import get_db
from app.models import User
from app.schemas.google import (
    CalendarEventItem,
    GmailSummaryItem,
    GoogleAuthorizeResult,
    GoogleCallbackPayload,
    GoogleCallbackResult,
    GoogleDisconnectResult,
    GoogleDriveFile,
    GoogleEventCreatePayload,
    GoogleExportResult,
    GoogleStatus,
    GoogleSurveyResult,
)
from app.services import google_actions, google_api, google_oauth

logger = logging.getLogger(__name__)
router = APIRouter()
_require_admin = require_role("admin")


def _parse_start_iso(raw: str) -> datetime:
    """ISO 8601; sin zona → America/Bogota (UTC-5, Colombia no tiene DST)."""
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Fecha inválida: usa ISO 8601 (ej: 2026-10-20T15:00:00)",
        ) from exc
    if parsed.tzinfo is None:
        # Naive = hora Colombia (UTC-5): 15:00 Bogotá → 20:00 UTC
        parsed = (parsed + timedelta(hours=5)).replace(tzinfo=UTC)
    return parsed


@router.get("/status", response_model=GoogleStatus)
async def google_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GoogleStatus:
    """¿El tenant tiene su cuenta Google conectada?"""
    data = await google_actions.connection_status(db, tenant_id=current_user.tenant_id)
    return GoogleStatus(**data)


@router.post("/authorize", response_model=GoogleAuthorizeResult)
async def google_authorize(
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> GoogleAuthorizeResult:
    """Inicia el flujo OAuth: devuelve la URL de consentimiento de Google."""
    if not google_oauth.google_configured():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "La plataforma aún no tiene credenciales de Google "
                "(GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)."
            ),
        )
    state = google_oauth.build_state_token(current_user.tenant_id)
    return GoogleAuthorizeResult(
        authorization_url=google_oauth.build_authorization_url(state)
    )


@router.post("/callback", response_model=GoogleCallbackResult)
async def google_callback(
    body: GoogleCallbackPayload,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> GoogleCallbackResult:
    """Google volvió con el code: verificar state, canjear y guardar."""
    # El state ata el consentimiento al tenant que lo inició: nadie puede
    # conectar la cuenta de otro negocio (ni cross-tenant ni CSRF).
    try:
        state_tenant = google_oauth.verify_state_token(body.state)
    except google_oauth.GoogleAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    if state_tenant != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este enlace de conexión pertenece a otra cuenta.",
        )

    tokens = await google_oauth.exchange_code(body.code)
    google_email = await google_oauth.fetch_user_email(tokens["access_token"])
    if not google_email:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google no devolvió el correo de la cuenta.",
        )
    await google_oauth.upsert_connection(
        db,
        tenant_id=current_user.tenant_id,
        google_email=google_email,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_in=tokens["expires_in"],
        scope=tokens["scope"],
    )
    logger.info(
        "Tenant %s conectó su cuenta Google (%s)",
        current_user.tenant_id, google_email,
    )
    return GoogleCallbackResult(connected=True, google_email=google_email)


@router.delete("/disconnect", response_model=GoogleDisconnectResult)
async def google_disconnect(
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> GoogleDisconnectResult:
    """Revoca los tokens en Google y borra la conexión del tenant."""
    removed = await google_oauth.disconnect(db, tenant_id=current_user.tenant_id)
    return GoogleDisconnectResult(disconnected=removed)


@router.get("/gmail/summary", response_model=list[GmailSummaryItem])
async def gmail_summary(
    max_results: int = Query(5, ge=1, le=20),
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[GmailSummaryItem]:
    """Los correos más recientes de la bandeja del dueño (solo lectura)."""
    try:
        messages = await google_actions.summarize_inbox(
            db, tenant_id=current_user.tenant_id, max_results=max_results
        )
    except google_oauth.GoogleNotConnected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_oauth.GoogleAuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_api.GoogleApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [
        GmailSummaryItem(
            sender=m["from"], subject=m["subject"], date=m["date"], snippet=m["snippet"]
        )
        for m in messages
    ]


@router.get("/calendar/upcoming", response_model=list[CalendarEventItem])
async def calendar_upcoming(
    days: int = Query(7, ge=1, le=31),
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[CalendarEventItem]:
    """La agenda del dueño entre hoy y N días."""
    try:
        events = await google_actions.upcoming_events(
            db, tenant_id=current_user.tenant_id, days=days
        )
    except google_oauth.GoogleNotConnected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_oauth.GoogleAuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_api.GoogleApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    items: list[CalendarEventItem] = []
    for ev in events:
        items.append(
            CalendarEventItem(
                summary=ev.get("summary", "(sin título)"),
                start=ev.get("start", {}).get("dateTime")
                or ev.get("start", {}).get("date", ""),
                end=ev.get("end", {}).get("dateTime")
                or ev.get("end", {}).get("date", ""),
                description=ev.get("description"),
            )
        )
    return items


@router.post("/calendar/events", response_model=CalendarEventItem)
async def calendar_create_event(
    body: GoogleEventCreatePayload,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> CalendarEventItem:
    """Agenda un evento en el calendario principal del dueño."""
    start = _parse_start_iso(body.start_iso)
    try:
        event = await google_actions.create_event(
            db,
            tenant_id=current_user.tenant_id,
            summary=body.summary,
            start_at=start,
            duration_minutes=body.duration_minutes,
            description=body.description,
        )
    except google_oauth.GoogleNotConnected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_oauth.GoogleAuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_api.GoogleApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return CalendarEventItem(
        summary=event.get("summary", body.summary),
        start=event.get("start", {}).get("dateTime", ""),
        end=event.get("end", {}).get("dateTime", ""),
        description=event.get("description"),
    )


@router.post("/sheets/export-expenses", response_model=GoogleExportResult)
async def sheets_export_expenses(
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> GoogleExportResult:
    """Exporta los gastos del mes a una hoja de cálculo nueva."""
    from sqlalchemy import select

    from app.models import Tenant

    tenant = (
        await db.execute(
            select(Tenant).where(Tenant.id == current_user.tenant_id)
        )
    ).scalar_one()
    try:
        result = await google_actions.export_expenses_sheet(db, tenant=tenant)
    except google_oauth.GoogleNotConnected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_oauth.GoogleAuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_api.GoogleApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return GoogleExportResult(**result)


@router.post("/docs/month-report", response_model=GoogleExportResult)
async def docs_month_report(
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> GoogleExportResult:
    """Genera el informe del mes en un documento nuevo de Google Docs."""
    from sqlalchemy import select

    from app.models import Tenant

    tenant = (
        await db.execute(
            select(Tenant).where(Tenant.id == current_user.tenant_id)
        )
    ).scalar_one()
    try:
        result = await google_actions.create_month_report_doc(db, tenant=tenant)
    except google_oauth.GoogleNotConnected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_oauth.GoogleAuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_api.GoogleApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return GoogleExportResult(**result)


@router.get("/drive/files", response_model=list[GoogleDriveFile])
async def drive_files(
    max_results: int = Query(10, ge=1, le=50),
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[GoogleDriveFile]:
    """Archivos recientes del Drive del dueño."""
    try:
        files = await google_actions.drive_recent_files(
            db, tenant_id=current_user.tenant_id, max_results=max_results
        )
    except google_oauth.GoogleNotConnected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_oauth.GoogleAuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_api.GoogleApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [
        GoogleDriveFile(
            name=f.get("name", ""),
            mime_type=f.get("mimeType", ""),
            modified_time=f.get("modifiedTime"),
            web_view_link=f.get("webViewLink"),
        )
        for f in files
    ]


@router.post("/forms/satisfaction-survey", response_model=GoogleSurveyResult)
async def forms_satisfaction_survey(
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> GoogleSurveyResult:
    """Crea una encuesta de satisfacción lista para compartir."""
    from sqlalchemy import select

    from app.models import Tenant

    tenant = (
        await db.execute(
            select(Tenant).where(Tenant.id == current_user.tenant_id)
        )
    ).scalar_one()
    try:
        result = await google_actions.create_satisfaction_survey(db, tenant=tenant)
    except google_oauth.GoogleNotConnected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_oauth.GoogleAuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except google_api.GoogleApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return GoogleSurveyResult(**result)

