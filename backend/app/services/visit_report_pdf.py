"""Generador de informe de visita técnica en PDF.

PDF con hallazgos y recomendaciones listo para compartir con el cliente.
Incluye: negocio, técnico, cliente, fecha, descripción del trabajo,
hallazgos, recomendaciones y espacio para fotos (si se agregan).
"""

import io
from datetime import UTC, datetime
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from app.models import Contact, Tenant


def _format_cop(val: float | int | None) -> str:
    if val is None or val <= 0:
        return ""
    return f"${float(val):,.0f}".replace(",", ".")


def generate_visit_report_pdf(
    *,
    tenant: Tenant,
    contact: Contact | None,
    report_number: str,
    description: str,
    findings: list[str],
    recommendations: list[str],
) -> io.BytesIO:
    """Genera un informe de visita técnica en PDF."""
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

    story: list[Any] = []

    # Encabezado
    business_lines = [escape(tenant.name)]
    if getattr(tenant, "nit", None):
        business_lines.append(f"NIT: {escape(tenant.nit)}")

    now = datetime.now(UTC)
    date_str = now.strftime("%d/%m/%Y")

    story.append(Paragraph("<br/>".join(business_lines), title))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"<b>{report_number}</b> · Informe de Visita Técnica",
        sub,
    ))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=border, spaceAfter=14))

    # Cliente
    client_name = escape(contact.name) if contact and contact.name else "Cliente"
    client_phone = contact.wa_id if contact and contact.wa_id else "-"
    story.append(Paragraph("<b>CLIENTE:</b>", h2))
    story.append(Paragraph(f"<b>{client_name}</b><br/>Tel: {client_phone}", body))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>FECHA:</b> {date_str}", body))
    story.append(Spacer(1, 14))

    # Descripción del trabajo
    story.append(Paragraph("<b>TRABAJO REALIZADO:</b>", h2))
    story.append(Paragraph(escape(description), body))
    story.append(Spacer(1, 14))

    # Hallazgos
    if findings:
        story.append(Paragraph("<b>HALLAZGOS:</b>", h2))
        for i, finding in enumerate(findings, 1):
            story.append(Paragraph(f"{i}. {escape(finding)}", body))
        story.append(Spacer(1, 14))

    # Recomendaciones
    if recommendations:
        story.append(Paragraph("<b>RECOMENDACIONES:</b>", h2))
        for rec in recommendations:
            story.append(Paragraph(f"• {escape(rec)}", body))
        story.append(Spacer(1, 14))

    # Pie
    story.append(Spacer(1, 40))
    story.append(HRFlowable(width="40%", thickness=0.5, color=border, spaceAfter=4))
    story.append(Paragraph(f"Firma: {escape(tenant.name)}", sub))
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", thickness=0.5, color=border, spaceAfter=8))
    story.append(Paragraph(
        f"Informe emitido por {escape(tenant.name)} a través de "
        f"su Asistente {escape(tenant.bot_name)}.",
        sub,
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer
