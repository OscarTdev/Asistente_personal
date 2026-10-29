"""Contactos de Google (People API) → CRM del negocio.

El dueño conecta su cuenta de Google y puede traer sus contactos al mini
CRM: así el bot reconoce nombres («abre una obra para Juan») sin tener que
crear cada cliente a mano.

Solo LECTURA (scope contacts.readonly): el asistente nunca modifica la
libreta de direcciones de Google. La importación solo AGREGA contactos
nuevos y completa campos vacíos; nunca pisa lo que el dueño ya editó.
"""

import logging
import re
from dataclasses import dataclass
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact
from app.services import google_oauth

logger = logging.getLogger(__name__)

PEOPLE_CONNECTIONS_URL = "https://people.googleapis.com/v1/people/me/connections"
CONTACTS_SCOPE = "https://www.googleapis.com/auth/contacts.readonly"
_PAGE_SIZE = 1000
_MAX_PAGES = 10  # tope: 10.000 contactos por importación


class GoogleContactsError(Exception):
    """Falla mostrable al dueño (mensaje en español, sin detalles técnicos)."""


class GoogleContactsScopeMissing(GoogleContactsError):
    """La cuenta se conectó antes de existir el permiso de contactos."""


@dataclass
class ImportResult:
    total: int = 0          # contactos que trae Google
    created: int = 0        # contactos nuevos en el CRM
    updated: int = 0        # existentes a los que se les completó algún dato
    unchanged: int = 0      # ya estaban completos
    skipped_no_phone: int = 0  # sin teléfono válido (no se pueden contactar)


def normalize_phone(raw: str) -> str | None:
    """Teléfono de Google → solo dígitos con indicativo (Colombia por defecto).

    «300 123 4567» → 573001234567 · «+57 300 123 4567» → 573001234567 ·
    «+1 305 555 0100» → 13055550100 · «123» → None (no es un teléfono).
    """
    text = (raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    if not text.startswith("+") and digits.startswith("00"):
        digits = digits[2:]
    elif not text.startswith("+") and len(digits) == 10:
        digits = "57" + digits  # número nacional colombiano
    if not 11 <= len(digits) <= 15:
        return None
    return digits


def _first_phone(person: dict) -> str | None:
    """El primer teléfono utilizable de la persona (prefiere el celular)."""
    phones = person.get("phoneNumbers") or []
    ordered = sorted(
        phones, key=lambda p: 0 if str(p.get("type", "")).lower() == "mobile" else 1
    )
    for phone in ordered:
        normalized = normalize_phone(str(phone.get("value", "")))
        if normalized:
            return normalized
    return None


async def _fetch_people(access_token: str) -> list[dict]:
    """Todas las conexiones del usuario (paginado)."""
    people: list[dict] = []
    page_token: str | None = None
    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(_MAX_PAGES):
            params = {
                "personFields": "names,phoneNumbers,emailAddresses,addresses",
                "pageSize": str(_PAGE_SIZE),
            }
            if page_token:
                params["pageToken"] = page_token
            resp = await client.get(
                PEOPLE_CONNECTIONS_URL,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code == 403:
                body = resp.text
                if "SERVICE_DISABLED" in body or "has not been used" in body:
                    raise GoogleContactsError(
                        "La API de Google Contactos (People API) no está habilitada "
                        "en el proyecto de Google Cloud de la plataforma."
                    )
                raise GoogleContactsScopeMissing(
                    "Falta el permiso de contactos. Reconecta tu cuenta de Google "
                    "y acepta el acceso a tus contactos."
                )
            if resp.status_code == 401:
                raise google_oauth.GoogleAuthError(
                    "Tu conexión con Google expiró. Reconecta tu cuenta desde el panel."
                )
            if resp.status_code != 200:
                logger.warning("People API respondió HTTP %s", resp.status_code)
                raise GoogleContactsError(
                    "Google no respondió bien al pedir tus contactos. Intenta de nuevo."
                )
            data = resp.json()
            people.extend(data.get("connections") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    return people


async def import_google_contacts(
    db: AsyncSession, *, tenant_id: UUID
) -> ImportResult:
    """Trae los contactos de Google al CRM del negocio. Idempotente."""
    conn = await google_oauth.get_connection(db, tenant_id=tenant_id)
    if conn is None:
        raise google_oauth.GoogleNotConnected(
            "Aún no has conectado tu cuenta de Google. Hazlo desde el panel: "
            "Mi negocio → Conectar Google."
        )
    if CONTACTS_SCOPE not in (conn.scopes or []):
        raise GoogleContactsScopeMissing(
            "Tu cuenta de Google se conectó antes de que existiera el acceso a "
            "contactos. Reconéctala desde el panel y acepta ese permiso."
        )

    access_token = await google_oauth.get_access_token(db, tenant_id=tenant_id)
    people = await _fetch_people(access_token)

    existing = {
        c.wa_id: c
        for c in (
            await db.execute(select(Contact).where(Contact.tenant_id == tenant_id))
        )
        .scalars()
        .all()
    }

    result = ImportResult(total=len(people))
    seen: set[str] = set()
    for person in people:
        wa_id = _first_phone(person)
        if wa_id is None:
            result.skipped_no_phone += 1
            continue
        if wa_id in seen:
            continue  # dos contactos de Google con el mismo teléfono
        seen.add(wa_id)

        name = ((person.get("names") or [{}])[0].get("displayName") or "").strip()
        email = ((person.get("emailAddresses") or [{}])[0].get("value") or "").strip()
        address = (
            (person.get("addresses") or [{}])[0].get("formattedValue") or ""
        ).strip()

        contact = existing.get(wa_id)
        if contact is None:
            db.add(
                Contact(
                    tenant_id=tenant_id,
                    wa_id=wa_id,
                    name=name[:100] or None,
                    email=email[:120] or None,
                    address=address or None,
                )
            )
            result.created += 1
            continue

        # Existente: solo completa lo que está vacío (nunca pisa ediciones)
        changed = False
        if name and not contact.name:
            contact.name = name[:100]
            changed = True
        if email and not contact.email:
            contact.email = email[:120]
            changed = True
        if address and not contact.address:
            contact.address = address
            changed = True
        if changed:
            result.updated += 1
        else:
            result.unchanged += 1

    await db.commit()
    logger.info(
        "Contactos de Google importados (tenant %s): %s nuevos, %s actualizados",
        tenant_id,
        result.created,
        result.updated,
    )
    return result
