"""Esquemas de la integración con Google Workspace (spec §15)."""

from pydantic import BaseModel, ConfigDict, Field


class GoogleStatus(BaseModel):
    """Estado de la conexión Google del tenant."""

    configured: bool
    connected: bool
    google_email: str | None = None
    scopes: list[str] = []


class GoogleAuthorizeResult(BaseModel):
    """URL de consentimiento a la que el panel redirige al dueño."""

    authorization_url: str


class GoogleLoginAuthorizeRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)


class GoogleCallbackPayload(BaseModel):
    """Lo que Google devuelve al panel tras el consentimiento."""

    code: str = Field(..., min_length=10, max_length=2000)
    state: str = Field(..., min_length=10, max_length=4000)


class GoogleCallbackResult(BaseModel):
    connected: bool
    google_email: str
    authenticated: bool = False
    access_token: str | None = None
    user: dict | None = None


class GoogleDisconnectResult(BaseModel):
    disconnected: bool


class GmailSummaryItem(BaseModel):
    """Un correo de la bandeja del dueño (solo lectura)."""

    sender: str
    subject: str
    date: str
    snippet: str


class GoogleEventCreatePayload(BaseModel):
    """Evento a agendar en el calendario del dueño."""

    summary: str = Field(..., min_length=1, max_length=200)
    # Fecha/hora de inicio ISO 8601 (naive → America/Bogota, UTC-5)
    start_iso: str = Field(..., min_length=10, max_length=60)
    duration_minutes: int = Field(60, ge=15, le=720)
    description: str | None = Field(None, max_length=1000)


class CalendarEventItem(BaseModel):
    """Un evento del calendario (campos tal cual los devuelve Google)."""

    model_config = ConfigDict(populate_by_name=True)

    summary: str
    start: str
    end: str
    description: str | None = None


class GoogleExportResult(BaseModel):
    """Hoja o documento creado en la cuenta Google del dueño."""

    url: str
    title: str
    rows: int | None = None


class GoogleDriveFile(BaseModel):
    name: str
    mime_type: str
    modified_time: str | None = None
    web_view_link: str | None = None


class GoogleSurveyResult(BaseModel):
    """Encuesta de satisfacción creada con Google Forms."""

    url: str
    edit_url: str
