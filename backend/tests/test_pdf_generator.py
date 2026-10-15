"""Tests del generador de PDF de cotizaciones.

Antes de este archivo, ninguna prueba tocaba el PDF: el bug de
contact.phone_number y la inyección de marcado pasaban inadvertidos.
"""

import io
import uuid
from datetime import UTC, datetime

from app.models import Contact, Quote, QuoteItem, Tenant
from app.services.pdf_generator import generate_quote_pdf


def _tenant() -> Tenant:
    return Tenant(
        id=uuid.uuid4(),
        name="Taller Eléctrico Gómez",
        slug="taller",
        bot_name="Aura",
        is_active=True,
    )


def _contact(name: str = "Juliana Pérez", wa_id: str = "573001112233") -> Contact:
    return Contact(tenant_id=uuid.uuid4(), wa_id=wa_id, name=name)


def _quote(tenant: Tenant, contact: Contact) -> Quote:
    return Quote(
        tenant_id=tenant.id,
        contact_id=contact.id,
        conversation_id=None,
        status="sent",
        total=45000,
        created_at=datetime.now(UTC),
    )


def _items(quote: Quote, description: str = "Tomacorriente doble") -> list[QuoteItem]:
    return [
        QuoteItem(
            tenant_id=quote.tenant_id,
            quote_id=quote.id,
            catalog_item_id=None,
            description=description,
            quantity=3,
            unit_price=15000,
            line_total=45000,
            position=0,
        )
    ]


def test_pdf_with_real_contact():
    """C1: un contacto real (wa_id, no phone_number) no rompe el PDF."""
    tenant = _tenant()
    contact = _contact()
    quote = _quote(tenant, contact)

    buffer = generate_quote_pdf(quote, _items(quote), tenant=tenant, contact=contact)

    assert isinstance(buffer, io.BytesIO)
    data = buffer.getvalue()
    assert data[:5] == b"%PDF-"


def test_pdf_with_logo():
    """El logo (PNG en bytes) se incrusta en el encabezado sin romper nada."""
    import io as io_mod

    from PIL import Image

    logo_buffer = io_mod.BytesIO()
    Image.new("RGBA", (200, 80), (15, 23, 42, 255)).save(logo_buffer, format="PNG")
    logo_bytes = logo_buffer.getvalue()

    tenant = _tenant()
    quote = _quote(tenant, _contact())

    buffer = generate_quote_pdf(
        quote, _items(quote), tenant=tenant, logo_bytes=logo_bytes
    )

    data = buffer.getvalue()
    assert data[:5] == b"%PDF-"
    # El PNG va incrustado en el PDF
    assert logo_bytes[:8] in data or b"Image" in data


def test_pdf_with_corrupt_logo_does_not_break():
    """Un logo corrupto jamás debe romper la cotización (fallback a texto)."""
    tenant = _tenant()
    quote = _quote(tenant, _contact())

    buffer = generate_quote_pdf(
        quote, _items(quote), tenant=tenant, logo_bytes=b"no-es-un-png"
    )

    assert buffer.getvalue()[:5] == b"%PDF-"


def test_pdf_without_contact():
    """Sin contacto sigue funcionando (regresión)."""
    tenant = _tenant()
    quote = _quote(tenant, _contact())

    buffer = generate_quote_pdf(quote, _items(quote), tenant=tenant, contact=None)

    assert buffer.getvalue()[:5] == b"%PDF-"


def test_pdf_with_malicious_text():
    """M4: texto con marcado sin cerrar del cliente/IA no rompe el PDF.

    El nombre del contacto viene del pushName de WhatsApp (lo controla el
    cliente) y las descripciones vienen de la IA: hay que escaparlas.
    """
    tenant = _tenant()
    tenant.name = "Taller <b>Gómez"
    contact = _contact(name="Juan <unclosed> & Cía")
    quote = _quote(tenant, contact)

    buffer = generate_quote_pdf(
        quote,
        _items(quote, description="Cable <b>12 & <tag sin cerrar"),
        tenant=tenant,
        contact=contact,
    )

    assert buffer.getvalue()[:5] == b"%PDF-"


def test_pdf_without_notes():
    """Sin notas el PDF también sale (regresión)."""
    tenant = _tenant()
    contact = _contact()
    quote = _quote(tenant, contact)
    quote.notes = None

    buffer = generate_quote_pdf(quote, _items(quote), tenant=tenant, contact=contact)

    assert buffer.getvalue()[:5] == b"%PDF-"
