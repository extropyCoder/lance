#!/usr/bin/env python3
"""Render submission/executive-summary.md to submission/executive-summary.pdf.

The Markdown file is the only source of text. This script supports just the
markup that file uses:

  <!-- meta: key = value -->   pdf_title, footer (may hold one [text](url) link)
  # / ## / ###                 title, headline, section heading
  @@ text                      kicker line under the title
  > text                       lede paragraph
  - item                       bullet (continuation lines are joined)
  | a | b |                    table (second line is the separator row)
  <!-- pagebreak -->           start a new page
  **bold**, `code`             inline markup

Requires reportlab (pypdf and pypdfium2 are only needed to check the result).
Install into a scratch directory, not into the project:

  pip3 install --target /tmp/opencode/lance-summary.XXXXXX/deps reportlab pypdf pypdfium2

Build, from the repository root:

  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/opencode/lance-summary.XXXXXX/deps \
      python3 submission/build_executive_summary.py

Fonts: Lato and DejaVu Sans Mono from the system font directory, falling back
to DejaVu Sans when Lato is missing. The build fails if the PDF is not 1 to 4
pages, and prints the page count.
"""

import html
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "executive-summary.md"
OUTPUT = HERE / "executive-summary.pdf"

NAVY = colors.HexColor("#14213D")
TEAL = colors.HexColor("#0F7C84")
INK = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#5B6572")
RULE = colors.HexColor("#CBD5DC")
TINT = colors.HexColor("#EEF6F7")

MARGIN_X = 20 * mm
MARGIN_TOP = 17 * mm
MARGIN_BOTTOM = 19 * mm
BODY_SIZE = 10.5

FONT_SETS = (
    (
        Path("/usr/share/fonts/truetype/lato"),
        {
            "Body": "Lato-Regular.ttf",
            "Body-Bold": "Lato-Bold.ttf",
            "Body-Italic": "Lato-Italic.ttf",
            "Body-BoldItalic": "Lato-BoldItalic.ttf",
        },
    ),
    (
        Path("/usr/share/fonts/truetype/dejavu"),
        {
            "Body": "DejaVuSans.ttf",
            "Body-Bold": "DejaVuSans-Bold.ttf",
            "Body-Italic": "DejaVuSans.ttf",
            "Body-BoldItalic": "DejaVuSans-Bold.ttf",
        },
    ),
)
MONO = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")


def register_fonts() -> None:
    for directory, files in FONT_SETS:
        if all((directory / name).is_file() for name in files.values()):
            for face, name in files.items():
                pdfmetrics.registerFont(TTFont(face, str(directory / name)))
            break
    else:
        sys.exit("error: no usable font set found (Lato or DejaVu Sans)")
    if not MONO.is_file():
        sys.exit(f"error: missing font {MONO}")
    pdfmetrics.registerFont(TTFont("Mono", str(MONO)))
    pdfmetrics.registerFontFamily(
        "Body", normal="Body", bold="Body-Bold", italic="Body-Italic", boldItalic="Body-BoldItalic"
    )


def make_styles() -> dict[str, ParagraphStyle]:
    body = ParagraphStyle(
        "body", fontName="Body", fontSize=BODY_SIZE, leading=13.7, textColor=INK,
        alignment=TA_LEFT, spaceAfter=5,
    )
    return {
        "body": body,
        "title": ParagraphStyle(
            "title", parent=body, fontName="Body-Bold", fontSize=30, leading=34,
            textColor=NAVY, spaceAfter=0,
        ),
        "kicker": ParagraphStyle(
            "kicker", parent=body, fontName="Body-Bold", fontSize=11, leading=14,
            textColor=TEAL, spaceBefore=1, spaceAfter=9,
        ),
        "headline": ParagraphStyle(
            "headline", parent=body, fontName="Body-Bold", fontSize=16, leading=20,
            textColor=NAVY, spaceAfter=7,
        ),
        "lede": ParagraphStyle(
            "lede", parent=body, fontSize=11, leading=15.2, textColor=NAVY,
            leftIndent=10, borderPadding=0, spaceAfter=3,
        ),
        "h3": ParagraphStyle(
            "h3", parent=body, fontName="Body-Bold", fontSize=12.5, leading=15,
            textColor=NAVY, spaceBefore=8, spaceAfter=2.5, keepWithNext=1,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=body, leftIndent=13, bulletIndent=1, spaceAfter=3.2,
        ),
        "cell": ParagraphStyle(
            "cell", parent=body, fontSize=9, leading=11.4, spaceAfter=0,
        ),
        "cellhead": ParagraphStyle(
            "cellhead", parent=body, fontName="Body-Bold", fontSize=9, leading=11.4,
            textColor=colors.white, spaceAfter=0,
        ),
    }


def inline(text: str) -> str:
    """Escape text for Paragraph and apply **bold** and `code`."""
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r'<font name="Mono" size="8.6">\1</font>', out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)
    return out


def code_words(text: str) -> str:
    """Set known identifiers, such as os.system or shell=True, in monospace."""
    pattern = r"\b(os\.system|os\.popen|subprocess|shell=True|execute|executemany|eval|exec|pickle\.loads|yaml\.load|yaml\.safe_load)\b"
    parts = re.split(r"(<[^>]+>)", text)
    result = []
    in_font = 0
    for part in parts:
        if part.startswith("<"):
            if part.startswith("<font"):
                in_font += 1
            elif part.startswith("</font"):
                in_font -= 1
            result.append(part)
        elif in_font:
            result.append(part)
        else:
            result.append(re.sub(pattern, r'<font name="Mono" size="8.6">\1</font>', part))
    return "".join(result)


def parse_table(lines: list[str], styles: dict[str, ParagraphStyle], width: float) -> Table:
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    header, body = rows[0], rows[2:]
    ncols = len(header)
    if ncols == 3 and header[1] == "Count":
        fractions = [0.20, 0.14, 0.66]
    else:
        fractions = [0.22, 0.50, 0.28]
    data = [[Paragraph(inline(c), styles["cellhead"]) for c in header]]
    for row in body:
        data.append([
            Paragraph(code_words(inline(c)) if i else f"<b>{inline(c)}</b>", styles["cell"])
            for i, c in enumerate(row)
        ])
    table = Table(data, colWidths=[width * f for f in fractions], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, TINT]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]))
    return table


def build_story(text: str, styles: dict[str, ParagraphStyle], width: float):
    meta: dict[str, str] = {}
    story: list = []
    lines = text.splitlines()
    paragraph: list[str] = []
    i = 0

    def flush() -> None:
        if paragraph:
            story.append(Paragraph(code_words(inline(" ".join(paragraph))), styles["body"]))
            paragraph.clear()

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        m = re.match(r"<!--\s*meta:\s*(\w+)\s*=\s*(.*?)\s*-->$", stripped)
        if m:
            meta[m.group(1)] = m.group(2)
        elif stripped == "<!-- pagebreak -->":
            flush()
            story.append(PageBreak())
        elif not stripped:
            flush()
        elif line.startswith("# "):
            flush()
            story.append(Paragraph(inline(line[2:]), styles["title"]))
        elif line.startswith("@@ "):
            flush()
            story.append(Paragraph(inline(line[3:]), styles["kicker"]))
            story.append(HRFlowable(width="100%", thickness=1.4, color=TEAL, spaceAfter=10))
        elif line.startswith("## "):
            flush()
            story.append(Paragraph(inline(line[3:]), styles["headline"]))
        elif line.startswith("### "):
            flush()
            story.append(Paragraph(inline(line[4:]), styles["h3"]))
        elif line.startswith("> "):
            flush()
            lede = Table([[Paragraph(code_words(inline(line[2:])), styles["lede"])]], colWidths=[width])
            lede.setStyle(TableStyle([
                ("LINEBEFORE", (0, 0), (0, -1), 2.2, TEAL),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]))
            story.append(lede)
        elif line.startswith("- "):
            flush()
            item = [line[2:]]
            while i + 1 < len(lines) and lines[i + 1].startswith("  "):
                i += 1
                item.append(lines[i].strip())
            story.append(Paragraph(code_words(inline(" ".join(item))), styles["bullet"], bulletText="\u2022"))
        elif line.startswith("|"):
            flush()
            block = [line]
            while i + 1 < len(lines) and lines[i + 1].startswith("|"):
                i += 1
                block.append(lines[i])
            story.append(Spacer(1, 2))
            story.append(parse_table(block, styles, width))
            story.append(Spacer(1, 6))
        else:
            paragraph.append(stripped)
        i += 1
    flush()
    return meta, story


def make_page_decorator(footer: str):
    def decorate(canvas, doc) -> None:
        width, height = A4
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_X, MARGIN_BOTTOM - 4 * mm, width - MARGIN_X, MARGIN_BOTTOM - 4 * mm)
        canvas.setFont("Body", 8)
        canvas.setFillColor(MUTED)
        y = MARGIN_BOTTOM - 8.5 * mm
        link = re.search(r"\[([^\]]+)\]\(([^)]+)\)", footer)
        if link:
            before, after = footer[: link.start()], footer[link.end():]
            text, url = link.group(1), link.group(2)
            canvas.drawString(MARGIN_X, y, before)
            x = MARGIN_X + pdfmetrics.stringWidth(before, "Body", 8)
            link_width = pdfmetrics.stringWidth(text, "Body", 8)
            canvas.setFillColor(TEAL)
            canvas.drawString(x, y, text)
            canvas.setStrokeColor(TEAL)
            canvas.setLineWidth(0.4)
            canvas.line(x, y - 1.2, x + link_width, y - 1.2)
            canvas.linkURL(url, (x, y - 2.5, x + link_width, y + 7), relative=0, thickness=0)
            canvas.setFillColor(MUTED)
            canvas.drawString(x + link_width, y, after)
        else:
            canvas.drawString(MARGIN_X, y, footer)
        canvas.drawRightString(width - MARGIN_X, y, f"Page {doc.page}")
        canvas.setFillColor(TEAL)
        canvas.rect(0, height - 4.5 * mm, width, 4.5 * mm, stroke=0, fill=1)
        canvas.restoreState()
    return decorate


def main() -> int:
    register_fonts()
    styles = make_styles()
    width = A4[0] - 2 * MARGIN_X
    meta, story = build_story(SOURCE.read_text(encoding="utf-8"), styles, width)
    title = meta.get("pdf_title", "Lance - Executive summary")
    footer = meta.get("footer", "")

    doc = BaseDocTemplate(
        str(OUTPUT), pagesize=A4, title=title, subject="Executive summary",
        creator="submission/build_executive_summary.py",
        leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOTTOM,
    )
    frame = Frame(MARGIN_X, MARGIN_BOTTOM, width, A4[1] - MARGIN_TOP - MARGIN_BOTTOM,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=make_page_decorator(footer))])
    doc.build(story)

    pages = doc.page
    print(f"wrote {OUTPUT} ({pages} pages)")
    if not 1 <= pages <= 4:
        OUTPUT.unlink()
        sys.exit(f"error: expected 1 to 4 pages, got {pages}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
