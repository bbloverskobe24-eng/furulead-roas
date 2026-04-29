"""PDFレポート生成（茂右ヱ門レポートの汎用版）"""
from __future__ import annotations
import os
import re
from datetime import datetime
from typing import Tuple
from app import storage
from app.questions import get_questions

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(BASE, "templates")
OUTPUT_DIR = os.path.join(BASE, "data", "generated_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _render_template(template_path: str, ctx: dict) -> str:
    with open(template_path, encoding="utf-8") as f:
        md = f.read()
    for key, val in ctx.items():
        md = md.replace("{{" + key + "}}", str(val or "（未回答）"))
    return md


def build_context(line_user_id: str) -> dict:
    user = storage.get_user(line_user_id) or {}
    answers = storage.get_answers(line_user_id)

    return {
        "line_user_id": line_user_id,
        "course": user.get("course", "simple"),
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
        # 簡易コース
        "S1": answers.get("S1"), "S2": answers.get("S2"),
        "S3": answers.get("S3"), "S4": answers.get("S4"),
        "S5": answers.get("S5"),
        # 詳細コース
        "D1": answers.get("D1"), "D2": answers.get("D2"),
        "D3": answers.get("D3"), "D4": answers.get("D4"),
        "D5": answers.get("D5"), "D6": answers.get("D6"),
        "D7": answers.get("D7"), "D8": answers.get("D8"),
        "D9": answers.get("D9"), "D10": answers.get("D10"),
        "D11": answers.get("D11"), "D12": answers.get("D12"),
        "D13": answers.get("D13"), "D14": answers.get("D14"),
        "D15": answers.get("D15"),
        # エイリアス（どちらのコースでも埋まるキー）
        "事業者名": answers.get("D1") or answers.get("S1"),
        "所在地": answers.get("D2") or answers.get("S2"),
        "カテゴリ": answers.get("D3") or answers.get("S3"),
        "ストーリー": answers.get("D12") or answers.get("S4"),
        "メール": answers.get("D15") or answers.get("S5"),
    }


def generate_markdown(line_user_id: str) -> str:
    """ユーザーの回答から下書きmdを生成し、パスを返す"""
    user = storage.get_user(line_user_id) or {}
    course = user.get("course", "simple")
    template_name = "template_simple.md" if course == "simple" else "template_full.md"
    template_path = os.path.join(TEMPLATES, template_name)

    ctx = build_context(line_user_id)
    md = _render_template(template_path, ctx)

    out_name = f"draft_{line_user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path = os.path.join(OUTPUT_DIR, out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    return out_path


def generate_pdf(md_path: str) -> str:
    """mdからPDFをビルド（表・箇条書き対応の本格レンダラー）"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))

    FONT = "HeiseiKakuGo-W5"
    FONT_MIN = "HeiseiMin-W3"
    BRAND_DARK = colors.HexColor("#1a5276")
    LIGHT = colors.HexColor("#f4f6f7")
    BORDER = colors.HexColor("#dce3e8")
    DARK = colors.HexColor("#222")

    STYLE_TITLE = ParagraphStyle("title", fontName=FONT, fontSize=18, leading=26,
                                 textColor=BRAND_DARK, spaceAfter=10)
    STYLE_H2 = ParagraphStyle("h2", fontName=FONT, fontSize=13, leading=20,
                              textColor=BRAND_DARK, spaceBefore=12, spaceAfter=6)
    STYLE_H3 = ParagraphStyle("h3", fontName=FONT, fontSize=11, leading=16,
                              textColor=DARK, spaceBefore=8, spaceAfter=4)
    STYLE_BODY = ParagraphStyle("body", fontName=FONT_MIN, fontSize=10, leading=15,
                                textColor=DARK, spaceAfter=3)
    STYLE_CELL = ParagraphStyle("cell", fontName=FONT_MIN, fontSize=9.2, leading=13,
                                textColor=DARK)
    STYLE_CELL_HEAD = ParagraphStyle("cell_head", fontName=FONT, fontSize=9.5,
                                     leading=13, textColor=colors.white)

    def _inline(text: str) -> str:
        text = text.replace("&", "&amp;")
        text = re.sub(r"\*\*(.+?)\*\*", r'<font name="{}">\1</font>'.format(FONT), text)
        text = re.sub(r"`([^`]+)`", r'<font color="#7a3f00">\1</font>', text)
        return text

    def _make_table(rows):
        n = len(rows[0])
        data = [[Paragraph(_inline(c), STYLE_CELL_HEAD if i == 0 else STYLE_CELL)
                 for c in row] for i, row in enumerate(rows)]
        page_w = A4[0] - 40 * mm
        tbl = Table(data, colWidths=[page_w / n] * n, repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(rows)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
        tbl.setStyle(TableStyle(style))
        return tbl

    def _parse_table_block(lines, start):
        rows = []
        i = start
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            row = lines[i].strip().strip("|")
            cells = [c.strip() for c in row.split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in cells):
                i += 1
                continue
            rows.append(cells)
            i += 1
        return rows, i

    pdf_path = md_path.replace(".md", ".pdf")
    with open(md_path, encoding="utf-8") as f:
        md = f.read()
    md = re.sub(r"^---\n.*?\n---\n", "", md, count=1, flags=re.DOTALL)

    lines = md.split("\n")
    flows = []
    i = 0
    in_para = []

    def _flush_para():
        nonlocal in_para
        if in_para:
            text = " ".join(in_para).strip()
            if text:
                flows.append(Paragraph(_inline(text), STYLE_BODY))
            in_para = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            _flush_para()
            i += 1
            continue

        if stripped.startswith("# "):
            _flush_para()
            flows.append(Paragraph(_inline(stripped[2:]), STYLE_TITLE))
            i += 1
            continue
        if stripped.startswith("## "):
            _flush_para()
            flows.append(Paragraph(_inline(stripped[3:]), STYLE_H2))
            i += 1
            continue
        if stripped.startswith("### ") or stripped.startswith("#### "):
            _flush_para()
            txt = stripped[4:] if stripped.startswith("### ") else stripped[5:]
            flows.append(Paragraph(_inline(txt), STYLE_H3))
            i += 1
            continue

        if stripped.startswith("---"):
            _flush_para()
            flows.append(Spacer(1, 8))
            i += 1
            continue

        if stripped.startswith("|"):
            _flush_para()
            rows, i = _parse_table_block(lines, i)
            if rows:
                flows.append(Spacer(1, 4))
                flows.append(_make_table(rows))
                flows.append(Spacer(1, 6))
            continue

        if re.match(r"^[-*]\s+", stripped):
            _flush_para()
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i]))
                i += 1
            for it in items:
                flows.append(Paragraph("・ " + _inline(it), STYLE_BODY))
            continue

        if re.match(r"^\d+\.\s+", stripped):
            _flush_para()
            items = []
            while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
                items.append(re.sub(r"^\s*\d+\.\s+", "", lines[i]))
                i += 1
            for idx, it in enumerate(items, 1):
                flows.append(Paragraph(f"{idx}. " + _inline(it), STYLE_BODY))
            continue

        in_para.append(stripped)
        i += 1

    _flush_para()

    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=15 * mm)
    doc.build(flows)
    return pdf_path


def generate_full_report(line_user_id: str) -> Tuple[str, str]:
    """md→PDF一貫生成。(md_path, pdf_path)を返す"""
    md_path = generate_markdown(line_user_id)
    pdf_path = generate_pdf(md_path)
    storage.create_report(line_user_id, pdf_path)
    return md_path, pdf_path
