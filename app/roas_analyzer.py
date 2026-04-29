"""ROAS分析エンジン — 事業者情報をAI（Claude）が分析しJSON出力"""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

# .env を 2 段階で読む（bot自身 → ai_agents全体）
_BASE = Path(__file__).resolve().parent.parent
load_dotenv(_BASE / ".env")
_AI_AGENTS_ENV = _BASE.parent / ".env"
if _AI_AGENTS_ENV.exists():
    load_dotenv(_AI_AGENTS_ENV, override=False)

PLANS_PATH = _BASE / "data" / "plans.yaml"


def load_plans() -> dict:
    with open(PLANS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["plans"]


def recommend_plan(fit_total: float, revenue_range: str, monthly_supply: int) -> str:
    """プラン推奨ロジック（依頼書 §3-2）"""
    low_revenue = revenue_range in ("1000万未満", "1000-5000万")
    high_revenue = revenue_range in ("1-5億", "5億以上")

    if fit_total < 5.0 or low_revenue or monthly_supply < 200:
        return "silver"
    if fit_total >= 8.0 and high_revenue and monthly_supply >= 1000:
        return "platinum"
    return "gold"


def _system_prompt() -> str:
    plans = load_plans()
    plan_summary = "\n".join(
        f"- {p['name']}: {p['description']} / 想定初年度寄付額 "
        f"{p['expected_first_year_donation']:,}〜{p['expected_first_year_donation_max']:,}円"
        for p in plans.values()
    )
    return f"""あなたはふるさと納税参入支援サービス「ふるりーど」のAI分析エンジンです。
事業者情報を受け取り、参入適性・売上見込み・推奨プランを科学的根拠とともに分析してください。

【ふるりーどのプラン】
{plan_summary}

【出力形式】
必ず以下のJSONスキーマ通りに、JSON単体で出力してください。前後に説明文を付けないでください。

{{
  "executive_summary": "3〜5行のエグゼクティブサマリ",
  "business_profile": {{
    "summary": "事業者プロファイル（200字）",
    "strengths": ["強み1", "強み2", "強み3"],
    "challenges": ["課題1", "課題2"]
  }},
  "market_benchmark": {{
    "category_avg_donation": 3500000000,
    "category_growth_rate": 12.3,
    "competitor_count": 245,
    "narrative": "市場分析テキスト（300字）"
  }},
  "fit_score": {{
    "scores": {{
      "商品力": 8, "ストーリー性": 9, "価格帯適合": 7, "供給能力": 6,
      "自治体連携": 5, "競合優位性": 8, "オペ負荷の低さ": 7, "地場産品要件適合度": 9
    }},
    "benchmark": {{
      "商品力": 6, "ストーリー性": 5, "価格帯適合": 7, "供給能力": 6,
      "自治体連携": 5, "競合優位性": 5, "オペ負荷の低さ": 6, "地場産品要件適合度": 6
    }},
    "total_score": 7.4,
    "narrative": "適性分析テキスト（300字）"
  }},
  "revenue_forecast": {{
    "conservative": {{ "year1": 5000000, "year2": 12000000, "year3": 25000000 }},
    "moderate":     {{ "year1": 10000000, "year2": 30000000, "year3": 60000000 }},
    "aggressive":   {{ "year1": 20000000, "year2": 60000000, "year3": 120000000 }},
    "narrative": "売上予測の根拠（300字）"
  }},
  "product_recommendations": [
    {{ "name": "U-1 蒲焼1尾", "rarity_score": 4, "donation_price": 18000, "category": "メイン商品", "rationale": "..." }}
  ],
  "roas_simulation": {{
    "monthly_ad_spend": 500000,
    "expected_donation_per_month": 3500000,
    "platform_fee_rate": 0.10,
    "production_cost_rate": 0.30,
    "net_profit_per_month": 1750000,
    "roas": 7.0,
    "payback_months": 0.3,
    "narrative": "ROAS分析テキスト（300字）"
  }},
  "plan_recommendation": {{
    "recommended": "ゴールド",
    "rationale": "推奨理由（200字）",
    "comparison": {{
      "シルバー": {{ "fit": 60, "expected_revenue": 5000000, "ng_reason": "供給力に対して機会損失" }},
      "ゴールド": {{ "fit": 90, "expected_revenue": 30000000, "ng_reason": null }},
      "プラチナ": {{ "fit": 70, "expected_revenue": 50000000, "ng_reason": "初期投資回収に時間要する" }}
    }}
  }},
  "next_actions": [
    "アクション1：自治体への正式相談（5/15まで）",
    "アクション2：返礼品撮影（5/末）",
    "アクション3：寄付ポータル掲載準備（6月）"
  ]
}}

【ルール】
- 数値はすべて根拠を持って算定すること
- 「ストーリー性」は unique_story / awards / media_coverage を加味
- 「自治体連携」は municipality_relation の値で減点／加点
- 「供給能力」は monthly_supply × retail_price で算定
- 「商品力」「価格帯適合」「競合優位性」は カテゴリ・価格・ストーリーから推論
- ROAS = 月間寄付額 ÷ 月間広告費（自治体手数料・原価控除前）
- 純利益 = 月間寄付額 × (1 - platform_fee_rate - production_cost_rate)
- product_recommendations は3〜6件
- 不確実な箇所は narrative 内で明示すること
- 必ずJSON単体で出力（前後にコードフェンスや説明を付けない）
"""


def _build_user_prompt(form: dict) -> str:
    return f"""以下の事業者情報を分析してください。

【事業者基本情報】
- 事業者名: {form.get('business_name')}
- 代表者: {form.get('representative')}
- 所在地: {form.get('prefecture')} {form.get('city')}
- 業種: {form.get('business_type')}
- 創業年数: {form.get('years_in_business')}年
- Webサイト: {form.get('website_url') or 'なし'}

【商品情報】
{json.dumps(form.get('main_products', []), ensure_ascii=False, indent=2)}

【ふるさと納税の現状】
- ステータス: {form.get('furusato_status')}
- 現在の年間寄付額: {form.get('current_donation_amount', 0):,}円
- 想定自治体: {form.get('target_municipality')}
- 自治体との関係: {form.get('municipality_relation')}

【事業規模】
- 年商レンジ: {form.get('annual_revenue_range')}
- 従業員数: {form.get('employees')}名

【差別化要素】
- ストーリー: {form.get('unique_story')}
- 受賞歴: {form.get('awards') or 'なし'}
- メディア掲載: {form.get('media_coverage') or 'なし'}

【広告予算】
- 月間広告予算: {form.get('marketing_budget_monthly', 0):,}円

上記をもとに、JSON単体で分析結果を出力してください。
"""


def _extract_json(text: str) -> dict:
    """AI出力からJSON部分を抽出"""
    text = text.strip()
    # ```json ... ``` を剥がす
    text = re.sub(r"^```(?:json)?\s*\n", "", text)
    text = re.sub(r"\n```\s*$", "", text)
    text = text.strip()
    # 最外側 { ... } を探す
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
    return json.loads(text)


def analyze(form: dict, model: Optional[str] = None) -> dict:
    """事業者情報フォームをAIに渡しJSON分析結果を返す"""
    from anthropic import Anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY が環境変数にありません。.env を確認してください。")

    client = Anthropic(api_key=api_key)
    model_id = model or os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    msg = client.messages.create(
        model=model_id,
        max_tokens=4096,
        system=_system_prompt(),
        messages=[{"role": "user", "content": _build_user_prompt(form)}],
    )

    text = "".join(b.text for b in msg.content if hasattr(b, "text"))
    analysis = _extract_json(text)

    # プラン推奨を機械判定で補強（AI判定とのダブルチェック）
    fit_total = float(analysis.get("fit_score", {}).get("total_score", 0))
    revenue_range = form.get("annual_revenue_range", "1000万未満")
    monthly_supply = sum(
        int(p.get("monthly_supply", 0)) for p in form.get("main_products", [])
    )
    rule_based = recommend_plan(fit_total, revenue_range, monthly_supply)
    analysis["_rule_based_plan"] = rule_based
    return analysis
