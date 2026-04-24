"""Render a briefing markdown string to a one-page A4 PDF with an embedded QR code."""

from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _qr_image(url: str, size_cm: float = 2.8) -> Image:
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Image(buf, width=size_cm * cm, height=size_cm * cm)


# -- tiny markdown → reportlab flowables --------------------------------------


_BOLD_RE = re.compile(r"\*\*([^\*]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^\*]+)\*(?!\*)")


def _inline_md_to_html(s: str) -> str:
    """Convert inline **bold** and *italic* to reportlab's HTML subset."""
    s = _BOLD_RE.sub(r"<b>\1</b>", s)
    s = _ITALIC_RE.sub(r"<i>\1</i>", s)
    return s


def _md_to_flowables(markdown: str, styles):
    flow = []
    for raw in markdown.split("\n"):
        line = raw.rstrip()
        if not line:
            flow.append(Spacer(1, 0.18 * cm))
            continue
        if line.startswith("### "):
            flow.append(Paragraph(_inline_md_to_html(line[4:]), styles["H3"]))
        elif line.startswith("## "):
            flow.append(Paragraph(_inline_md_to_html(line[3:]), styles["H2"]))
        elif line.startswith("# "):
            flow.append(Paragraph(_inline_md_to_html(line[2:]), styles["H1"]))
        elif line.startswith(("- ", "* ")):
            flow.append(Paragraph("• " + _inline_md_to_html(line[2:]), styles["Bullet"]))
        elif line.strip().startswith(tuple(f"{n}." for n in range(1, 10))):
            flow.append(Paragraph(_inline_md_to_html(line), styles["Bullet"]))
        else:
            flow.append(Paragraph(_inline_md_to_html(line), styles["Body"]))
    return flow


def _styles():
    base = getSampleStyleSheet()
    s = {
        "Title": ParagraphStyle(
            "Title", parent=base["Title"], fontSize=18, leading=22, spaceAfter=4
        ),
        "Subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#555"),
            spaceAfter=10,
        ),
        "H1": ParagraphStyle(
            "H1", parent=base["Heading1"], fontSize=14, leading=18, spaceBefore=10, spaceAfter=4
        ),
        "H2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontSize=12,
            leading=16,
            spaceBefore=8,
            spaceAfter=3,
            textColor=colors.HexColor("#1f3d7a"),
        ),
        "H3": ParagraphStyle(
            "H3", parent=base["Heading3"], fontSize=11, leading=14, spaceBefore=6, spaceAfter=2
        ),
        "Body": ParagraphStyle(
            "Body", parent=base["Normal"], fontSize=10, leading=13, spaceAfter=3
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontSize=10,
            leading=13,
            leftIndent=12,
            spaceAfter=2,
        ),
        "Footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#777"),
        ),
    }
    return s


def render_briefing_pdf(
    *,
    markdown: str,
    qr_url: str,
    family_label: str,
    output_path: Path,
    window_days: int = 42,
) -> Path:
    """Render a one-page briefing PDF at output_path. Returns the path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.5 * cm,
        title="AI-Care GP briefing",
        author="AI-Care",
    )
    styles = _styles()

    flow = []

    # Header: title + subtitle
    flow.append(Paragraph("AI-Care — GP briefing", styles["Title"]))
    sub = (
        f"<b>{family_label}</b> · Last {window_days} days · "
        f"Generated {datetime.now().strftime('%d %b %Y %H:%M')}"
    )
    flow.append(Paragraph(sub, styles["Subtitle"]))

    # Body from markdown
    flow.extend(_md_to_flowables(markdown, styles))

    # Spacer + footer row with QR on the right
    flow.append(Spacer(1, 0.4 * cm))

    qr_img = _qr_image(qr_url, size_cm=2.8)
    footer_text = (
        "Scan to view this briefing on a phone.<br/>"
        "Compiled from medication confirmations + parent voice-diary events. "
        "Not medical advice; please interpret clinically."
    )
    footer_tbl = Table(
        [
            [
                Paragraph(footer_text, styles["Footer"]),
                qr_img,
            ]
        ],
        colWidths=[None, 3.2 * cm],
    )
    footer_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.4, colors.HexColor("#ccc")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    flow.append(footer_tbl)

    doc.build(flow)
    return output_path
