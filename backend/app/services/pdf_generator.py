"""Generador de cotizaciones en formato PDF usando ReportLab.

Diseñado para ser ligero, robusto y sin dependencias del sistema operativo.
Retorna un buffer BytesIO listo para ser servido como StreamingResponse.

El encabezado lleva los datos del negocio del registro (nombre, NIT,
correo, ciudad) y el consecutivo legible (COT-0001). El total en letras
usa num2words con es_CO.
"""

import io
from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import Contact, Quote, QuoteItem, Tenant
from app.services.documents import total_in_letters


def _format_currency(val: Decimal | float | int | None) -> str:
    if val is None:
        return "$0"
    try:
        # Formato COP / decimal con separador de miles
        return f"${float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"${val}"


def _safe_int(value) -> int:
    """Convierte a int de forma segura (Decimal, float, str)."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def generate_quote_pdf(
    quote: Quote,
    items: list[QuoteItem],
    tenant: Tenant | None = None,
    contact: Contact | None = None,
    doc_number: str | None = None,
) -> io.BytesIO:
    """Genera un archivo PDF con la cotización formateada y lo retorna en un BytesIO."""
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    primary_color = colors.HexColor("#0f172a")
    accent_color = colors.HexColor("#2563eb")
    text_muted = colors.HexColor("#64748b")
    border_color = colors.HexColor("#e2e8f0")

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=primary_color,
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=text_muted,
    )

    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=accent_color,
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=primary_color,
    )

    body_bold = ParagraphStyle(
        "BodyBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=primary_color,
    )

    right_sub_style = ParagraphStyle(
        "RightSub",
        parent=subtitle_style,
        alignment=2,
    )

    h_right = ParagraphStyle("HRight", parent=body_bold, alignment=2)
    c_right = ParagraphStyle("CRight", parent=body_style, alignment=2)
    p_right = ParagraphStyle("PRight", parent=body_style, alignment=2)
    t_right = ParagraphStyle("TRight", parent=body_bold, alignment=2)
    tot_lbl = ParagraphStyle("TotLbl", parent=body_bold, fontSize=12, alignment=2)
    tot_val = ParagraphStyle(
        "TotVal",
        parent=body_bold,
        fontSize=13,
        alignment=2,
        textColor=accent_color,
    )

    story: list[Any] = []

    # ── Encabezado: negocio a la izquierda, documento a la derecha ───────
    company_name = tenant.name if tenant else "Asistente Personal"
    bot_name = getattr(tenant, "bot_name", "Aura") or "Aura"

    # Datos del negocio del registro (NIT, correo, ciudad)
    business_lines = [escape(company_name)]
    if tenant and getattr(tenant, "nit", None):
        business_lines.append(f"NIT: {escape(tenant.nit)}")
    if tenant and getattr(tenant, "account_type", "personal") == "business":
        pass  # NIT ya está arriba

    date_str = quote.created_at.strftime("%d/%m/%Y") if quote.created_at else "-"
    valid_str = quote.valid_until.strftime("%d/%m/%Y") if quote.valid_until else "15 días"

    # Número del documento: consecutivo legible o fallback al UUID
    doc_label = doc_number or f"COT-{str(quote.id)[:8].upper()}"

    header_right_parts = [f"<b>{doc_label}</b>"]
    header_right_parts.append(f"<font color='#64748b'>Fecha: {date_str}</font>")
    header_right_parts.append(f"<font color='#64748b'>Válida hasta: {valid_str}</font>")

    header_data = [
        [
            Paragraph("<br/>".join(business_lines), title_style),
            Paragraph(
                "<br/>".join(header_right_parts),
                right_sub_style,
            ),
        ],
        [
            Paragraph(f"Asistente: {escape(bot_name)}", subtitle_style),
            Paragraph("", right_sub_style),
        ],
    ]
    header_table = Table(header_data, colWidths=[4.5 * inch, 3.0 * inch])
    header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ])
    )
    story.append(header_table)
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1, color=border_color, spaceAfter=14))

    # ── Cliente / Contacto ───────────────────────────────────────────────────
    client_name = escape(contact.name) if contact and contact.name else "Cliente particular"
    client_phone = contact.wa_id if contact and contact.wa_id else "-"

    client_data = [
        [Paragraph("<b>DIRIGIDO A:</b>", h2_style)],
        [Paragraph(f"<b>{client_name}</b><br/>Tel: {client_phone}", body_style)],
    ]
    client_table = Table(client_data, colWidths=[7.5 * inch])
    client_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ])
    )
    story.append(client_table)
    story.append(Spacer(1, 14))

    # ── Tabla de Ítems ────────────────────────────────────────────────────────
    table_headers = [
        Paragraph("<b>#</b>", body_bold),
        Paragraph("<b>Descripción</b>", body_bold),
        Paragraph("<b>Cant.</b>", h_right),
        Paragraph("<b>P. Unitario</b>", h_right),
        Paragraph("<b>Total</b>", h_right),
    ]

    items_rows = [table_headers]
    for idx, it in enumerate(items, start=1):
        qty_formatted = f"{float(it.quantity):.2f}".rstrip("0").rstrip(".")
        items_rows.append([
            Paragraph(str(idx), body_style),
            Paragraph(escape(it.description), body_style),
            Paragraph(qty_formatted, c_right),
            Paragraph(_format_currency(it.unit_price), p_right),
            Paragraph(_format_currency(it.line_total), t_right),
        ])

    items_table = Table(
        items_rows,
        colWidths=[0.4 * inch, 3.8 * inch, 0.9 * inch, 1.2 * inch, 1.2 * inch],
    )
    items_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
            ("LINEBELOW", (0, 0), (-1, 0), 1.5, primary_color),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, border_color),
        ])
    )
    story.append(items_table)
    story.append(Spacer(1, 14))

    # ── Total en cifras y en letras ──────────────────────────────────────────
    letters = total_in_letters(quote.total)

    totals_data = [
        [
            "",
            Paragraph("<b>TOTAL:</b>", tot_lbl),
            Paragraph(f"<b>{_format_currency(quote.total)}</b>", tot_val),
        ],
        [
            "",
            Paragraph(
                f"<font color='#64748b'><b>En letras:</b> {escape(letters)}</font>",
                subtitle_style,
            ),
            Paragraph("", subtitle_style),
        ],
    ]
    totals_table = Table(totals_data, colWidths=[3.5 * inch, 2.0 * inch, 2.0 * inch])
    totals_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 1), (-1, 1), 2),
            ("LINEABOVE", (1, 0), (-1, 0), 1.5, primary_color),
        ])
    )
    story.append(totals_table)
    story.append(Spacer(1, 20))

    # ── Notas / Términos ──────────────────────────────────────────────────────
    if quote.notes:
        story.append(Paragraph("<b>Notas y Condiciones:</b>", h2_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph(escape(quote.notes).replace("\n", "<br/>"), body_style))
        story.append(Spacer(1, 16))

    # ── Pie de página ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=border_color, spaceAfter=8))
    footer_text = (
        f"Cotización emitida por {escape(company_name)} a través de "
        f"su Asistente {escape(bot_name)}."
    )
    story.append(Paragraph(footer_text, subtitle_style))

    doc.build(story)
    buffer.seek(0)
    return buffer
