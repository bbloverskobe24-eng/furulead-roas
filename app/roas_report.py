"""ROAS分析レポート生成 — フォーム入力 → AI分析 → md → PDF"""
from __future__ import annotations
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Tuple

import yaml

from app import roas_analyzer, roas_charts, report_generator

_BASE = Path(__file__).resolve().parent.parent
_TEMPLATES = {
    "internal": _BASE / "templates" / "template_roas.md",
    "lead": _BASE / "templates" / "template_roas_lead.md",
    "sales": _BASE / "templates" / "template_roas_sales.md",
}
_PLANS_PATH = _BASE / "data" / "plans.yaml"
_OUTPUT_DIR = _BASE / "data" / "generated_reports"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _safe_name(s: str) -> str:
    s = re.sub(r"[^\w぀-ヿ一-鿿_-]", "_", s)
    return s[:40] or "session"


def _yen(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "—"


def _man(n) -> str:
    try:
        return f"{int(int(n) / 10000):,}"
    except (TypeError, ValueError):
        return "—"


def _oku(n) -> str:
    """円 → 億円（小数点1桁）。1億未満でも丸まらず表示できる。"""
    try:
        v = float(n) / 100_000_000
        if v >= 100:
            return f"{v:,.0f}"
        return f"{v:,.1f}"
    except (TypeError, ValueError):
        return "—"


def _pct(rate) -> str:
    try:
        return f"{float(rate) * 100:.1f}"
    except (TypeError, ValueError):
        return "—"


def _bullets(items) -> str:
    if not items:
        return "（情報なし）"
    return "\n".join(f"- {i}" for i in items)


def _product_table(items) -> str:
    if not items:
        return "（推奨商品データなし）"
    rows = ["| 商品名 | 想定寄付額 | 希少性 | カテゴリ | コメント |",
            "|---|---|---|---|---|"]
    for it in items:
        rows.append(
            f"| {it.get('name', '—')} "
            f"| {_yen(it.get('donation_price', 0))}円 "
            f"| {it.get('rarity_score', '—')}/10 "
            f"| {it.get('category', '—')} "
            f"| {it.get('rationale', '—')} |"
        )
    return "\n".join(rows)


def _plan_comparison_table(comparison: dict) -> str:
    if not comparison:
        return "（プラン比較データなし）"
    rows = ["| プラン | 適合度 | 想定寄付額 | コメント |",
            "|---|---|---|---|"]
    for plan_name, info in comparison.items():
        rows.append(
            f"| {plan_name} "
            f"| {info.get('fit', '—')}% "
            f"| {_yen(info.get('expected_revenue', 0))}円 "
            f"| {info.get('ng_reason') or 'マッチ良好'} |"
        )
    return "\n".join(rows)


def _load_plans() -> dict:
    try:
        with open(_PLANS_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f).get("plans", {}) or {}
    except Exception:
        return {}


def _plan_profit_table(annual_donation_yen: float, producer_share_rate: float) -> str:
    """各コンサルプランで事業者の手元に残る金額を試算したMarkdownテーブル。

    手元残金 = 年間寄付額 × 事業者取り分率
              - (月額×12 + 初期費用)
              - 年間寄付額 × 成果報酬率

    SPEED系（自走支援）はコンサル契約とは別建てなので除外。
    """
    plans = _load_plans()
    if not plans:
        return "（プランデータが見つかりません）"

    consult_plans = {k: p for k, p in plans.items() if p.get("category") == "consult"}
    if not consult_plans:
        return "（コンサルプランデータが見つかりません）"

    rows = [
        "| プラン | 月額 | 初期費用 | 成果報酬 | 想定寄付額 | 事業者取り分 | ふるりーど料金合計(年) | **手元残金(年)** |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for key, p in consult_plans.items():
        monthly = int(p.get("monthly_fee", 0))
        setup = int(p.get("setup_fee", 0))
        success_pct = float(p.get("success_fee_pct", 0))
        success_fee = annual_donation_yen * (success_pct / 100.0)
        annual_furulead_fee = monthly * 12 + setup + success_fee
        producer_share = annual_donation_yen * producer_share_rate
        net = producer_share - annual_furulead_fee
        rows.append(
            f"| **{p.get('name', key)}**（{p.get('plan_subtitle', '')}） "
            f"| {_yen(monthly)}円/月 "
            f"| {_yen(setup)}円 "
            f"| {success_pct:.0f}% "
            f"| {_yen(annual_donation_yen)}円 "
            f"| {_yen(producer_share)}円 "
            f"| {_yen(annual_furulead_fee)}円 "
            f"| **{_yen(net)}円** |"
        )
    return "\n".join(rows)


def _render(template: str, ctx: dict) -> str:
    out = template
    for k, v in ctx.items():
        out = out.replace("{{" + k + "}}", str(v if v is not None else "—"))
    return out


def _build_md_context(form: dict, analysis: dict, chart_paths: dict,
                      usage: dict | None = None) -> dict:
    fit = analysis.get("fit_score", {})
    rev = analysis.get("revenue_forecast", {})
    cons = rev.get("conservative", {})
    mod = rev.get("moderate", {})
    agg = rev.get("aggressive", {})
    mkt = analysis.get("market_benchmark", {})
    prof = analysis.get("business_profile", {})
    roas = analysis.get("roas_simulation", {})
    plan = analysis.get("plan_recommendation", {})

    # 推奨プランの想定寄付額（中位シナリオ1年目をデフォルト）
    recommended_name = plan.get("recommended", "—")
    expected_year1_revenue = mod.get("year1", 0)
    plan_comp = plan.get("comparison", {}) or {}
    for key, info in plan_comp.items():
        if key == recommended_name:
            expected_year1_revenue = info.get("expected_revenue", expected_year1_revenue)
            break

    usage = usage or {}

    # プラン別手元残金計算用：事業者取り分率 = 1 - プラットフォーム手数料率 - 制作・配送コスト率
    platform_fee_rate = float(roas.get("platform_fee_rate", 0) or 0)
    production_cost_rate = float(roas.get("production_cost_rate", 0) or 0)
    producer_share_rate = max(0.0, 1.0 - platform_fee_rate - production_cost_rate)
    annual_donation_yen = float(mod.get("year1", 0) or 0)
    plan_profit_table = _plan_profit_table(annual_donation_yen, producer_share_rate)

    return {
        "business_name": form.get("business_name", "—"),
        "location": f"{form.get('prefecture', '')} {form.get('city', '')}".strip(),
        "business_type": form.get("business_type", "—"),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "executive_summary": analysis.get("executive_summary", "—"),
        "business_profile_summary": prof.get("summary", "—"),
        "strengths_list": _bullets(prof.get("strengths", [])),
        "challenges_list": _bullets(prof.get("challenges", [])),
        "category_avg_donation": _oku(mkt.get("category_avg_donation", 0)),
        "category_growth_rate": mkt.get("category_growth_rate", "—"),
        "competitor_count": mkt.get("competitor_count", "—"),
        "market_narrative": mkt.get("narrative", "—"),
        "total_score": fit.get("total_score", "—"),
        "fit_narrative": fit.get("narrative", "—"),
        "cons_y1": _man(cons.get("year1", 0)),
        "cons_y2": _man(cons.get("year2", 0)),
        "cons_y3": _man(cons.get("year3", 0)),
        "mod_y1": _man(mod.get("year1", 0)),
        "mod_y2": _man(mod.get("year2", 0)),
        "mod_y3": _man(mod.get("year3", 0)),
        "agg_y1": _man(agg.get("year1", 0)),
        "agg_y2": _man(agg.get("year2", 0)),
        "agg_y3": _man(agg.get("year3", 0)),
        "revenue_narrative": rev.get("narrative", "—"),
        "product_table": _product_table(analysis.get("product_recommendations", [])),
        "monthly_ad_spend": _yen(roas.get("monthly_ad_spend", 0)),
        "expected_donation_per_month": _yen(roas.get("expected_donation_per_month", 0)),
        "platform_fee_rate_pct": _pct(roas.get("platform_fee_rate", 0)),
        "production_cost_rate_pct": _pct(roas.get("production_cost_rate", 0)),
        "net_profit_per_month": _yen(roas.get("net_profit_per_month", 0)),
        "roas": roas.get("roas", "—"),
        "payback_months": roas.get("payback_months", "—"),
        "roas_narrative": roas.get("narrative", "—"),
        "recommended_plan": recommended_name,
        "recommended_plan_revenue_man": _man(expected_year1_revenue),
        "plan_rationale": plan.get("rationale", "—"),
        "plan_comparison_table": _plan_comparison_table(plan.get("comparison", {})),
        "plan_profit_table": plan_profit_table,
        "producer_share_pct": f"{producer_share_rate * 100:.1f}",
        "next_actions_list": _bullets(analysis.get("next_actions", [])),
        "usage_model": usage.get("model", "—"),
        "usage_input_tokens": f"{usage.get('input_tokens', 0):,}",
        "usage_output_tokens": f"{usage.get('output_tokens', 0):,}",
        "usage_cost_usd": f"{usage.get('cost_usd', 0):.4f}",
        "usage_cost_jpy": f"{usage.get('cost_jpy', 0):.2f}",
        "usage_fx_rate": f"{usage.get('fx_rate', 0):.1f}",
        "usage_input_price": f"{usage.get('input_price_usd_per_mtok', 0):.2f}",
        "usage_output_price": f"{usage.get('output_price_usd_per_mtok', 0):.2f}",
    }


def generate(form: dict, mode: str = "internal") -> Tuple[str, str, dict, dict]:
    """事業者情報フォーム → AI分析 → MD → PDF を生成。

    Args:
        form: 事業者情報フォーム
        mode: "internal"(社内全項目) / "lead"(興味付け版) / "sales"(一次営業版)

    Returns:
        md_path, pdf_path, analysis(JSON), usage(消費トークン・コスト)
    """
    if mode not in _TEMPLATES:
        raise ValueError(f"unknown mode: {mode}. choose from {list(_TEMPLATES)}")

    analysis, usage = roas_analyzer.analyze(form)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"roas_{mode}_{_safe_name(form.get('business_name', 'session'))}_{stamp}"
    work_dir = _OUTPUT_DIR / base_name
    work_dir.mkdir(parents=True, exist_ok=True)

    chart_paths = roas_charts.generate_all(
        analysis, form.get("business_name", "事業者"), str(work_dir)
    )

    with open(_TEMPLATES[mode], encoding="utf-8") as f:
        template = f.read()
    ctx = _build_md_context(form, analysis, chart_paths, usage)
    md_text = _render(template, ctx)

    md_path = work_dir / f"{base_name}.md"
    md_path.write_text(md_text, encoding="utf-8")

    pdf_path = _build_pdf_with_images(str(md_path), chart_paths)
    return str(md_path), pdf_path, analysis, usage


def generate_with_existing_analysis(
    form: dict, analysis: dict, usage: dict, mode: str
) -> Tuple[str, str]:
    """既存の分析結果を使って別modeのレポートを再生成（AI再呼び出しなし）。

    Returns: md_path, pdf_path
    """
    if mode not in _TEMPLATES:
        raise ValueError(f"unknown mode: {mode}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"roas_{mode}_{_safe_name(form.get('business_name', 'session'))}_{stamp}"
    work_dir = _OUTPUT_DIR / base_name
    work_dir.mkdir(parents=True, exist_ok=True)

    chart_paths = roas_charts.generate_all(
        analysis, form.get("business_name", "事業者"), str(work_dir)
    )

    with open(_TEMPLATES[mode], encoding="utf-8") as f:
        template = f.read()
    ctx = _build_md_context(form, analysis, chart_paths, usage or {})
    md_text = _render(template, ctx)

    md_path = work_dir / f"{base_name}.md"
    md_path.write_text(md_text, encoding="utf-8")

    pdf_path = _build_pdf_with_images(str(md_path), chart_paths)
    return str(md_path), pdf_path


def _build_pdf_with_images(md_path: str, chart_paths: dict) -> str:
    """画像埋め込み対応PDF生成（report_generator.generate_pdf を画像対応で拡張）"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
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

    md_dir = os.path.dirname(md_path)
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

    page_w = A4[0] - 40 * mm

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            _flush_para()
            i += 1
            continue

        # 画像 ![alt](path)
        img_match = re.match(r"^!\[(.*?)\]\((.+?)\)$", stripped)
        if img_match:
            _flush_para()
            img_path = img_match.group(2)
            if not os.path.isabs(img_path):
                img_path = os.path.join(md_dir, img_path)
            if os.path.exists(img_path):
                img = Image(img_path, width=page_w * 0.85, height=page_w * 0.55,
                            kind="proportional")
                flows.append(Spacer(1, 4))
                flows.append(img)
                flows.append(Spacer(1, 6))
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
