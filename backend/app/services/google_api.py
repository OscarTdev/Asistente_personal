"""Cliente REST de las APIs de Google (sin SDK, solo httpx).

Funciones puras: reciben un access_token y devuelven dicts/str. Toda la
autenticación y los tokens viven en google_oauth; esta capa no toca la
base de datos, lo que facilita testearla con mocks.

URLs oficiales (REST v1 de cada servicio); cualquier error >= 400 se
convierte en GoogleApiError con un mensaje accionable en español.
"""

import base64
import logging
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR_BASE = "https://www.googleapis.com/calendar/v3/calendars/primary"
SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
DOCS_BASE = "https://docs.googleapis.com/v1/documents"
DRIVE_BASE = "https://www.googleapis.com/drive/v3/files"
FORMS_BASE = "https://forms.googleapis.com/v1/forms"
PEOPLE_BASE = "https://people.googleapis.com/v1"

COLOMBIA_TZ = "America/Bogota"


class GoogleApiError(Exception):
    """Google respondió con error (4xx/5xx)."""


async def _request(
    method: str,
    url: str,
    access_token: str,
    *,
    params: dict | None = None,
    json: dict | None = None,
) -> dict:
    """Una sola puerta HTTP: fácil de parchear en tests."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method,
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            json=json,
        )
    if resp.status_code >= 400:
        detail = resp.text[:200]
        logger.warning("Google API %s %s → %s", method, url, resp.status_code)
        raise GoogleApiError(
            f"Google respondió {resp.status_code}: {detail}"
        )
    if resp.status_code == 204 or not resp.content:
        return {}
    return resp.json()


# ── Gmail ──────────────────────────────────────────────────────────────────


def _header(message: dict, name: str) -> str:
    """Un header del payload de Gmail (From, Subject, Date...)."""
    for item in message.get("payload", {}).get("headers", []):
        if item.get("name", "").lower() == name.lower():
            return item.get("value", "")
    return ""


async def gmail_recent_messages(
    access_token: str, *, query: str = "in:inbox", max_results: int = 5
) -> list[dict]:
    """Los N mensajes más recientes que cumplen el query."""
    listing = await _request(
        "GET",
        f"{GMAIL_BASE}/messages",
        access_token,
        params={"maxResults": max_results, "q": query},
    )
    messages: list[dict] = []
    for item in listing.get("messages", []):
        detail = await _request(
            "GET",
            f"{GMAIL_BASE}/messages/{item['id']}",
            access_token,
            params={
                "format": "metadata",
                "metadataHeaders": ["From", "Subject", "Date"],
            },
        )
        messages.append(
            {
                "from": _header(detail, "From"),
                "subject": _header(detail, "Subject"),
                "date": _header(detail, "Date"),
                "snippet": (detail.get("snippet") or "")[:120],
            }
        )
    return messages


async def gmail_send(
    access_token: str, *, to: str, subject: str, body: str, sender: str | None = None
) -> str:
    """Envía un correo y devuelve el id del mensaje creado."""
    msg = EmailMessage()
    msg["To"] = to
    if sender:
        msg["From"] = formataddr(("Aura", sender))
    msg["Subject"] = subject
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    result = await _request(
        "POST", f"{GMAIL_BASE}/messages/send", access_token, json={"raw": raw}
    )
    return result.get("id", "")


# ── Calendar ────────────────────────────────────────────────────────────────


async def calendar_events(
    access_token: str, *, time_min: str, time_max: str | None = None, max_results: int = 10
) -> list[dict]:
    """Eventos del calendario principal en orden de inicio."""
    params: dict[str, Any] = {
        "timeMin": time_min,
        "maxResults": max_results,
        "orderBy": "startTime",
        "singleEvents": "true",
    }
    if time_max:
        params["timeMax"] = time_max
    data = await _request("GET", f"{CALENDAR_BASE}/events", access_token, params=params)
    return data.get("items", [])


async def calendar_create_event(
    access_token: str,
    *,
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str | None = None,
) -> dict:
    """Crea un evento en el calendario principal del dueño."""
    event: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start_iso, "timeZone": COLOMBIA_TZ},
        "end": {"dateTime": end_iso, "timeZone": COLOMBIA_TZ},
    }
    if description:
        event["description"] = description
    return await _request(
        "POST", f"{CALENDAR_BASE}/events", access_token, json=event
    )


async def calendar_update_event(
    access_token: str,
    *,
    event_id: str,
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str | None = None,
) -> dict:
    """Actualiza un evento creado por Aura."""
    event: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start_iso, "timeZone": COLOMBIA_TZ},
        "end": {"dateTime": end_iso, "timeZone": COLOMBIA_TZ},
    }
    if description:
        event["description"] = description
    return await _request(
        "PUT",
        f"{CALENDAR_BASE}/events/{event_id}",
        access_token,
        json=event,
    )


async def calendar_delete_event(access_token: str, *, event_id: str) -> None:
    """Elimina el evento externo asociado a un recordatorio."""
    await _request(
        "DELETE",
        f"{CALENDAR_BASE}/events/{event_id}",
        access_token,
    )


# ── Keep / Docs notes ──────────────────────────────────────────────────────

KEEP_BASE = "https://keep.googleapis.com/v1"


async def keep_create_note(
    access_token: str, *, title: str, text: str
) -> dict:
    """Crea una nota de texto en Google Keep (Workspace compatible)."""
    return await _request(
        "POST",
        f"{KEEP_BASE}/notes",
        access_token,
        json={"title": title, "body": {"text": {"text": text}}},
    )


# ── Sheets ──────────────────────────────────────────────────────────────────


async def sheets_create_spreadsheet(access_token: str, *, title: str) -> dict:
    """Hoja de cálculo nueva en el Drive del dueño."""
    data = await _request(
        "POST", SHEETS_BASE, access_token, json={"properties": {"title": title}}
    )
    return {
        "spreadsheet_id": data.get("spreadsheetId", ""),
        "url": data.get("spreadsheetUrl", ""),
        "title": data.get("properties", {}).get("title", title),
    }


async def sheets_write_values(
    access_token: str, *, spreadsheet_id: str, values: list[list[str]]
) -> None:
    """Escribe un bloque 2D empezando en A1 (primera fila = encabezados).

    RAW y no USER_ENTERED: el contenido dictado por el dueño es DATOS,
    nunca fórmulas que Google deba evaluar (regla anti inyección).
    """
    await _request(
        "PUT",
        f"{SHEETS_BASE}/{spreadsheet_id}/values/A1",
        access_token,
        params={"valueInputOption": "RAW"},
        json={"values": values},
    )


# ── Docs ────────────────────────────────────────────────────────────────────


async def docs_create_document(access_token: str, *, title: str) -> dict:
    """Documento nuevo en el Drive del dueño."""
    data = await _request("POST", DOCS_BASE, access_token, json={"title": title})
    doc_id = data.get("documentId", "")
    return {"document_id": doc_id, "title": title, "url": _docs_url(doc_id)}


def _docs_url(doc_id: str) -> str:
    return f"https://docs.google.com/document/d/{doc_id}/edit"


async def docs_insert_text(access_token: str, *, document_id: str, text: str) -> None:
    """Inserta el texto al COMIENZO del documento (index 1: en un doc
    recién creado el título es metadata y el body empieza vacío)."""
    await _request(
        "POST",
        f"{DOCS_BASE}/{document_id}:batchUpdate",
        access_token,
        json={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1},
                        "text": text,
                    }
                }
            ]
        },
    )


# ── Drive ──────────────────────────────────────────────────────────────────


async def drive_list_files(access_token: str, *, max_results: int = 10) -> list[dict]:
    """Archivos del Drive creados/abiertos por la app (scope drive.file
    — así funciona: NO lista todo el Drive del dueño)."""
    data = await _request(
        "GET",
        DRIVE_BASE,
        access_token,
        params={
            "pageSize": max_results,
            "orderBy": "modifiedTime desc",
            "fields": "files(id,name,mimeType,modifiedTime,webViewLink)",
        },
    )
    return data.get("files", [])


# ── Forms ───────────────────────────────────────────────────────────────────


async def forms_create_satisfaction_survey(
    access_token: str, *, title: str, business_name: str
) -> dict:
    """Encuesta de satisfacción lista para enviar (calificación 1-5 + comentario)."""
    data = await _request(
        "POST", FORMS_BASE, access_token, json={"info": {"title": title}}
    )
    form_id = data.get("formId", "")
    # Agregar la pregunta de calificación 1 a 5
    await _request(
        "POST",
        f"{FORMS_BASE}/{form_id}:batchUpdate",
        access_token,
        json={
            "requests": [
                {
                    "createItem": {
                        "item": {
                            "title": f"¿Qué tal tu experiencia con {business_name}?",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "ratingQuestion": {"ratingScaleLevel": 5},
                                }
                            },
                        },
                        "location": {"index": 0},
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "¿Qué podemos mejorar? (opcional)",
                            "questionItem": {
                                "question": {"required": False, "textQuestion": {}}
                            },
                        },
                        "location": {"index": 1},
                    }
                },
            ]
        },
    )
    return {
        "form_id": form_id,
        "url": data.get("responderUri", ""),
        "edit_url": f"https://docs.google.com/forms/d/{form_id}/edit",
    }


# ── People (Contacts) ─────────────────────────────────────────────────────────


async def people_list_connections(
    access_token: str,
    *,
    page_size: int = 500,
    person_fields: str = "names,phoneNumbers,emailAddresses",
) -> list[dict]:
    """Lista los contactos del dueño (People API).

    Requiere scope: https://www.googleapis.com/auth/contacts.readonly
    """
    data = await _request(
        "GET",
        f"{PEOPLE_BASE}/people/me/connections",
        access_token,
        params={
            "pageSize": page_size,
            "personFields": person_fields,
        },
    )
    return data.get("connections", [])
