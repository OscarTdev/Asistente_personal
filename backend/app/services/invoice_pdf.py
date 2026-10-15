"""Generador de cuenta de cobro (CC-0001) en PDF.

Documento que envía un independiente o empresa NO obligada a facturar
electrónicamente para cobrar por servicios prestados. Incluye total en
letras (obligatorio) y datos bancarios si están configurados.
NO reemplaza la factura electrónica si el negocio sí está obligado.
"""

import io
from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import (
    Image as RLImage,
)

from app.models import Contact, Tenant
from app.services.documents import total_in_letters


def _format_currency(val: Decimal | float | int | None) -> str:
    if val is None:
        return "$0"
    try:
        return f"${float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"${val}"


def generate_invoice_pdf(
    *,
    tenant: Tenant,
    contact: Contact | None,
    doc_number: str,
    description: str,
    amount: Decimal,
    bank_details: dict | None = None,
    logo_bytes: bytes | None = None,
) -> io.BytesIO:
    """Genera una cuenta de cobro en PDF y la devuelve en un BytesIO."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    primary = colors.HexColor("#0f172a")
    accent = colors.HexColor("#2563eb")
    muted = colors.HexColor("#64748b")
    border = colors.HexColor("#e2e8f0")

    title = ParagraphStyle(
        "T", parent=styles["Heading1"], fontName="Helvetica-Bold",
        fontSize=18, leading=22, textColor=primary,
    )
    sub = ParagraphStyle(
        "S", parent=styles["Normal"], fontName="Helvetica",
        fontSize=9, leading=13, textColor=muted,
    )
    h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=12, leading=16, textColor=accent,
    )
    body = ParagraphStyle(
        "B", parent=styles["Normal"], fontName="Helvetica",
        fontSize=9, leading=13, textColor=primary,
    )
    bold = ParagraphStyle(
        "BB", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=9, leading=13, textColor=primary,
    )
    tot_lbl = ParagraphStyle("TL", parent=bold, fontSize=12, alignment=2)
    tot_val = ParagraphStyle(
        "TV", parent=bold, fontSize=13, alignment=2, textColor=accent,
    )

    story: list[Any] = []

    # Logo del negocio (si está configurado): escala a una caja de 110x48pt
    if logo_bytes:
        try:
            reader = ImageReader(io.BytesIO(logo_bytes))
            img_w, img_h = reader.getSize()
            if img_w > 0 and img_h > 0:
                scale = min(110.0 / img_w, 48.0 / img_h)
                story.append(
                    RLImage(reader, width=img_w * scale, height=img_h * scale)
                )
                story.append(Spacer(1, 8))
        except Exception:
            pass  # un logo corrupto jamás debe romper la cuenta de cobro

    # Encabezado
    business_lines = [escape(tenant.name)]
    if getattr(tenant, "nit", None):
        business_lines.append(f"NIT: {escape(tenant.nit)}")

    story.append(Paragraph("<br/>".join(business_lines), title))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>{doc_number}</b> · Cuenta de Cobro", sub))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=border, spaceAfter=14))

    # Cliente
    client_name = escape(contact.name) if contact and contact.name else "Cliente"
    client_phone = contact.wa_id if contact and contact.wa_id else "-"
    story.append(Paragraph("<b>DIRIGIDO A:</b>", h2))
    story.append(Paragraph(f"<b>{client_name}</b><br/>Tel: {client_phone}", body))
    story.append(Spacer(1, 14))

    # Concepto
    story.append(Paragraph("<b>CONCEPTO:</b>", h2))
    story.append(Paragraph(escape(description), body))
    story.append(Spacer(1, 14))

    # Total
    letters = total_in_letters(amount)
    totals = Table(
        [
            [
                "",
                Paragraph("<b>TOTAL A PAGAR:</b>", tot_lbl),
                Paragraph(f"<b>{_format_currency(amount)}</b>", tot_val),
            ],
            [
                "",
                Paragraph(
                    f"<font color='#64748b'>"
                    f"<b>En letras:</b> {escape(letters)}</font>",
                    sub,
                ),
                "",
            ],
        ],
        colWidths=[3.5 * inch, 2.0 * inch, 2.0 * inch],
    )
    totals.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
        ("LINEABOVE", (1, 0), (-1, 0), 1.5, primary),
    ]))
    story.append(totals)
    story.append(Spacer(1, 20))

    # Datos bancarios
    if bank_details:
        story.append(Paragraph("<b>PARA SU PAGO:</b>", h2))
        bank_lines = []
        if bank_details.get("bank"):
            bank_lines.append(f"Banco: {escape(bank_details['bank'])}")
        if bank_details.get("account_type"):
            bank_lines.append(f"Tipo de cuenta: {escape(bank_details['account_type'])}")
        if bank_details.get("account_number"):
            bank_lines.append(f"Número: {escape(bank_details['account_number'])}")
        if bank_details.get("account_holder"):
            bank_lines.append(f"Titular: {escape(bank_details['account_holder'])}")
        story.append(Paragraph("<br/>".join(bank_lines), body))
        story.append(Spacer(1, 20))

    # Firma
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="40%", thickness=0.5, color=border, spaceAfter=4))
    story.append(Paragraph(f"Firma: {escape(tenant.name)}", sub))

    # Pie
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", thickness=0.5, color=border, spaceAfter=8))
    footer_text = (
        f"Cuenta de cobro emitida por {escape(tenant.name)} "
        f"a través de su Asistente {escape(tenant.bot_name)}. "
        "Este documento no reemplaza la factura electrónica."
    )
    story.append(Paragraph(footer_text, sub))

    doc.build(story)
    buffer.seek(0)
    return buffer
