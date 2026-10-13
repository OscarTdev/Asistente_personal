"""Generador de cotizaciones en formato PDF usando ReportLab.

Diseñado para ser ligero, robusto y sin dependencias del sistema operativo.
Retorna un buffer BytesIO listo para ser servido como StreamingResponse.
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


def _format_currency(val: Decimal | float | int | None) -> str:
    if val is None:
        return "$0"
    try:
        # Formato COP / decimal con separador de miles
        return f"${float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"${val}"


def generate_quote_pdf(
    quote: Quote,
    items: list[QuoteItem],
    tenant: Tenant | None = None,
    contact: Contact | None = None,
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

    # Custom colors
    primary_color = colors.HexColor("#0f172a")  # Slate 900
    accent_color = colors.HexColor("#2563eb")   # Blue 600
    text_muted = colors.HexColor("#64748b")     # Slate 500
    border_color = colors.HexColor("#e2e8f0")   # Slate 200

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=primary_color,
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
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

    right_title_style = ParagraphStyle(
        "RightTitle",
        parent=title_style,
        alignment=2,
        fontSize=16,
        leading=20,
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

    # ── Encabezado ────────────────────────────────────────────────────────────
    company_name = tenant.name if tenant else "Asistente Personal"
    bot_name = getattr(tenant, "bot_name", "Aura") or "Aura"

    date_str = quote.created_at.strftime("%d/%m/%Y") if quote.created_at else "-"
    valid_str = quote.valid_until.strftime("%d/%m/%Y") if quote.valid_until else "15 días"

    header_data = [
        [
            Paragraph(f"<b>{escape(company_name)}</b>", title_style),
            Paragraph(
                f"<b>COTIZACIÓN</b><br/>"
                f"<font color='#64748b'>ID: #{str(quote.id)[:8].upper()}</font>",
                right_title_style,
            ),
        ],
        [
            Paragraph(f"Asistente: {escape(bot_name)}", subtitle_style),
            Paragraph(
                f"Fecha: {date_str}<br/>Válida hasta: {valid_str}",
                right_sub_style,
            ),
        ],
    ]
    header_table = Table(header_data, colWidths=[3.5 * inch, 4.0 * inch])
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
    # wa_id (no phone_number): el campo real del modelo Contact.
    # Todo texto que no escribimos nosotros se escapa (el nombre viene del
    # pushName de WhatsApp, que controla el cliente).
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

    # ── Resumen de Totales ────────────────────────────────────────────────────
    totals_data = [
        [
            "",
            Paragraph("<b>TOTAL:</b>", tot_lbl),
            Paragraph(f"<b>{_format_currency(quote.total)}</b>", tot_val),
        ]
    ]
    totals_table = Table(totals_data, colWidths=[4.5 * inch, 1.5 * inch, 1.5 * inch])
    totals_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
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
