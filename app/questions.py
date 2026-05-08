"""
ふるりーどSPEED 質問定義（v2.0 簡易5問のみ）

役割: Phase 1（リード獲得・興味付け）の最低限項目を取得。
詳細項目（複数商品・年商・代表者名等）はメール経由のヒアリングシートで取得。
設計書: CSO_sales/ふるりーどSPEED/03_質問フロー詳細.md
ヒアリングシート: templates/hearing_template.md
"""
from __future__ import annotations
from typing import Optional

# 簡易コース（5問）— 業種選択肢を管理画面ROAS分析と統一（食品/工芸/宿泊・体験/その他）
SIMPLE_QUESTIONS = [
    {
        "id": "S1", "type": "text", "weight": 15,
        "prompt": "まず、事業者名・屋号を教えてください。",
        "validate": None,
    },
    {
        "id": "S2", "type": "text", "weight": 20,
        "prompt": "次に、所在地を教えてください（例：福井県若狭町）",
        "validate": None,
    },
    {
        "id": "S3", "type": "button", "weight": 20,
        "prompt": "主力商品のカテゴリを選んでください。",
        "choices": ["食品", "工芸", "宿泊・体験", "その他"],
    },
    {
        "id": "S4", "type": "text", "weight": 25,
        "prompt": "他と違う強み・ストーリーを一言で教えてください（100字程度）\n"
                  "例：三代続く老舗蔵元／天然うなぎに特化／若手職人による新ブランド など",
        "validate": None,
    },
    {
        "id": "S5", "type": "email", "weight": 20,
        "prompt": "最後の質問です。\nレポート送付先のメールアドレスを教えてください📧",
        "validate": "email",
    },
]

# 詳細コース（15問）— DEPRECATED（v2.0以降）
# Phase 2 のヒアリングシート（templates/hearing_template.md）に役割を移譲。
# 既存セッションの互換性維持のため定義は残しているが、新規セッションでは使用しない。
# on_follow() で簡易コースのみを案内するよう conversation.py を修正済。
DETAILED_QUESTIONS = [
    {"id": "D1",  "type": "text",   "weight": 5,
     "prompt": "事業者名・屋号を教えてください。"},
    {"id": "D2",  "type": "text",   "weight": 10,
     "prompt": "所在地を教えてください（例：福井県若狭町）"},
    {"id": "D3",  "type": "button", "weight": 5,
     "prompt": "業種を選んでください。",
     "choices": ["食品（農産）", "食品（畜産）", "食品（水産）",
                 "食品加工・酒類", "宿泊・体験", "工芸・雑貨", "その他"]},
    {"id": "D4",  "type": "text",   "weight": 5,
     "prompt": "Webサイト・SNS・ECサイトのURLを教えてください。\n"
               "複数ある場合は改行して貼り付けてください。（なければ「なし」）"},
    {"id": "D5",  "type": "text",   "weight": 10,
     "prompt": "主力商品の概要を教えてください（200字程度）。\n"
               "※ECサイトの商品ページURLや商品紹介ページのリンクでも大丈夫です。"},
    {"id": "D6",  "type": "button", "weight": 5,
     "prompt": "メイン商材の小売価格帯を選んでください。",
     "choices": ["3,000円未満", "3,000〜10,000円",
                 "10,000〜30,000円", "30,000円以上"]},
    {"id": "D7",  "type": "text",   "weight": 10,
     "prompt": "月間の供給可能量を教えてください（例：500食／300本／10組）"},
    {"id": "D8",  "type": "button", "weight": 5,
     "prompt": "商品の配送形態を選んでください。",
     "choices": ["常温配送可", "冷蔵", "冷凍", "真空パック対応", "未整備・相談したい"]},
    {"id": "D9",  "type": "button", "weight": 10,
     "prompt": "ふるさと納税の現状を教えてください。",
     "choices": ["未掲載（これから）", "掲載中", "検討中／準備中"]},
    {"id": "D10", "type": "button", "weight": 5,
     "prompt": "法人形態を選んでください。",
     "choices": ["法人（株式会社等）", "個人事業主", "組合・協同組合", "その他"]},
    {"id": "D11", "type": "button", "weight": 5,
     "prompt": "年商レンジを選んでください（非公開・統計利用のみ）",
     "choices": ["〜1,000万", "1,000〜5,000万",
                 "5,000万〜1億", "1〜10億",
                 "10〜50億", "50億以上", "非公開"]},
    {"id": "D12", "type": "text",   "weight": 10,
     "prompt": "他と違うストーリー・強みを教えてください（300字程度）"},
    {"id": "D13", "type": "text",   "weight": 5,
     "prompt": "受賞歴・メディア掲載があれば教えてください。\n"
               "※URL（記事リンク・受賞発表ページなど）の共有でOKです。"
               "なければ「なし」と送信。"},
    {"id": "D14", "type": "button", "weight": 5,
     "prompt": "所在地の自治体との関係性を教えてください。",
     "choices": ["すでにふるさと納税で連携", "相談中／検討中",
                 "未接触", "わからない"]},
    {"id": "D15", "type": "email",  "weight": 5,
     "prompt": "最後の質問です。\nレポート送付先のメールアドレスを教えてください📧",
     "validate": "email"},
]


def get_questions(course: str):
    return SIMPLE_QUESTIONS if course == "simple" else DETAILED_QUESTIONS


def get_question(course: str, qid: str):
    for q in get_questions(course):
        if q["id"] == qid:
            return q
    return None


def next_question_id(course: str, current_qid: Optional[str]):
    qs = get_questions(course)
    if current_qid is None:
        return qs[0]["id"]
    for i, q in enumerate(qs):
        if q["id"] == current_qid and i + 1 < len(qs):
            return qs[i + 1]["id"]
    return None  # 全質問完了


def next_unanswered_question_id(course: str, answered_qids: set):
    """既回答スキップで次の質問IDを返す（簡易→詳細引継ぎ用）"""
    for q in get_questions(course):
        if q["id"] not in answered_qids:
            return q["id"]
    return None
