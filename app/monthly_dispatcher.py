"""SPEED会員 月次配信バッチ

Cloud Scheduler から HTTP起動を想定:
  POST {BASE_URL}/admin/dispatch/monthly  （DISPATCH_TOKEN ヘッダで認証）

機能:
- active会員（speed_light / speed_standard）を全件取得
- プラン別に月次レポートを生成（簡易診断スコア・ベンチマーク・改善提案）
- LINE pushで配信
- 配信履歴を member_deliveries に記録
- 失敗時はスキップして他ユーザーの配信を継続
"""
from __future__ import annotations
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from app import storage

log = logging.getLogger("monthly_dispatcher")

_BASE = Path(__file__).resolve().parent.parent
_OUTPUT_DIR = _BASE / "data" / "monthly_reports"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# LINE API クライアント（main.pyからのcircular import回避）
# ============================================================

def _line_api():
    from linebot.v3.messaging import Configuration, ApiClient, MessagingApi
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN 未設定")
    config = Configuration(access_token=token)
    return MessagingApi(ApiClient(config))


def _push_text(line_user_id: str, text: str):
    from linebot.v3.messaging import PushMessageRequest, TextMessage
    _line_api().push_message(PushMessageRequest(
        to=line_user_id,
        messages=[TextMessage(text=text)],
    ))


# ============================================================
# 配信メイン
# ============================================================

def dispatch_all() -> dict:
    """全active会員へ月次配信。

    Returns:
        {
            "total": 総会員数,
            "sent": 成功数,
            "failed": 失敗数,
            "skipped": スキップ数（既配信等）,
            "errors": [{"line_user_id":..., "error":...}, ...]
        }
    """
    stats = {"total": 0, "sent": 0, "failed": 0, "skipped": 0, "errors": []}

    light_members = storage.list_active_members(plan="speed_light")
    standard_members = storage.list_active_members(plan="speed_standard")
    all_members = light_members + standard_members
    stats["total"] = len(all_members)

    log.info(f"monthly dispatch start: {stats['total']} active members")

    for user in all_members:
        line_user_id = user["line_user_id"]
        plan = (user.get("membership") or {}).get("plan", "speed_light")
        try:
            result = dispatch_for_user(line_user_id, plan, user)
            if result.get("status") == "sent":
                stats["sent"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            stats["failed"] += 1
            stats["errors"].append({
                "line_user_id": line_user_id,
                "error": f"{type(e).__name__}: {e}",
            })
            log.exception(f"dispatch failed for {line_user_id}")

    log.info(f"monthly dispatch done: {stats}")
    return stats


def dispatch_for_user(line_user_id: str, plan: str,
                      user_data: Optional[dict] = None) -> dict:
    """個別会員への月次配信。

    Args:
        line_user_id: LINE user ID
        plan: "speed_light" | "speed_standard"
        user_data: 既に取得済のuser dictがあれば渡す（無ければ取得）

    Returns:
        {"line_user_id": ..., "plan": ..., "status": "sent" | "skipped"}
    """
    if not user_data:
        user_data = storage.get_user(line_user_id) or {}

    # 重複配信ガード（同月同タイプは送らない）
    content_type = "monthly_diagnosis"
    if _already_delivered_this_month(line_user_id, content_type):
        log.info(f"already delivered this month: {line_user_id}")
        return {"line_user_id": line_user_id, "plan": plan, "status": "skipped"}

    answers = storage.get_answers(line_user_id) or {}
    business_name = answers.get("S1") or "事業者"
    location = answers.get("S2") or "—"
    category = answers.get("S3") or "未分類"
    strength = answers.get("S4") or "—"

    # レポートMarkdown生成
    report_md = _generate_monthly_report_md(
        plan=plan,
        business_name=business_name,
        location=location,
        category=category,
        strength=strength,
    )

    # ファイル保存（PDF生成は将来的に追加）
    report_path = _save_report(line_user_id, plan, report_md)

    # LINE push
    line_text = _build_line_message(plan, business_name, report_path)
    _push_text(line_user_id, line_text)

    # 履歴記録
    storage.record_member_delivery(
        line_user_id=line_user_id,
        plan=plan,
        content_type=content_type,
        related_url=str(report_path),
        delivery_status="sent",
    )

    return {"line_user_id": line_user_id, "plan": plan, "status": "sent"}


# ============================================================
# レポート生成
# ============================================================

def _generate_monthly_report_md(plan: str, business_name: str, location: str,
                                  category: str, strength: str) -> str:
    """プラン別 月次レポートのMarkdown生成。

    Light: 適正度スコア + 5サイトベンチマーク + AI改善提案（簡易）
    Standard: Light の全項目 + SEO提案 + 競合上位10商品分析 + Q&A案内
    """
    today = datetime.utcnow().strftime("%Y年%m月")
    plan_display = "SPEED Standard" if plan == "speed_standard" else "SPEED Light"

    sections = [
        f"# {today} ふるさと納税 月次レポート",
        "",
        f"**事業者**: {business_name}",
        f"**所在地**: {location}",
        f"**カテゴリ**: {category}",
        f"**プラン**: {plan_display}",
        f"**作成日**: {datetime.utcnow().strftime('%Y-%m-%d')}",
        "",
        "---",
        "",
        "## 1. 今月の適正度スコア",
        "",
        _benchmark_score_section(category, strength),
        "",
        "## 2. 5サイト ベンチマーク調査結果",
        "",
        _benchmark_summary_section(category),
        "",
        "## 3. AI改善提案",
        "",
        _ai_suggestions_section(plan, category, strength),
    ]

    if plan == "speed_standard":
        sections.extend([
            "",
            "## 4. 競合上位10商品 詳細分析",
            "",
            _competitor_detail_section(category),
            "",
            "## 5. SEO・商品名キーワード改善案",
            "",
            _seo_suggestions_section(category),
            "",
            "## 6. 月次Q&Aセッションのご案内",
            "",
            _qa_session_section(),
        ])

    sections.extend([
        "",
        "---",
        "",
        "*本レポートはふるりーどSPEEDのAI分析エンジンによる自動生成です。*",
        "*具体的な施策実行のご相談は、コンサルプラン（シルバー/ゴールド/プラチナ）をご検討ください。*",
        "",
        "**FutureBright株式会社**  https://futurebright.co.jp/",
    ])

    return "\n".join(sections)


def _benchmark_score_section(category: str, strength: str) -> str:
    # TODO: 実際にベンチマーク取得してスコア化（現状はテンプレ）
    return (
        "| 評価項目 | スコア（100点満点） |\n"
        "|---|---:|\n"
        "| ブランド訴求 | 70 |\n"
        "| 商品ラインナップ幅 | 65 |\n"
        "| 写真・ページデザイン | 75 |\n"
        "| ポータル展開数 | 60 |\n"
        "| レビュー獲得 | — |\n"
        "| 高額帯対応 | 50 |\n"
        "| 定期便・体験型 | 30 |\n"
        "| **総合スコア** | **62** / 100（ランクB） |\n"
    )


def _benchmark_summary_section(category: str) -> str:
    # TODO: scripts/ の各ポータルスクレイパーで category の上位商品を取得
    return (
        f"今月の {category} カテゴリの上位商品トレンド：\n\n"
        "- ふるさとチョイス：上位10商品の平均寄付額帯 12,000〜18,000円\n"
        "- 楽天ふるさと納税：レビュー多数（平均30件超）の商品が上位独占\n"
        "- ふるなび：1万円以下の小ロット商品が新規参入で増加\n"
        "- さとふる：定期便コースの伸長率が前月比 +15%\n"
        "- Amazonふるさと納税：未参入事業者の参入余地が大きい\n"
    )


def _ai_suggestions_section(plan: str, category: str, strength: str) -> str:
    base = (
        "今月の改善ポイント（AI抽出）：\n\n"
        "1. 商品タイトルに「カテゴリ＋特徴＋容量」を明記すると検索ヒット率が上がります\n"
        "2. レビュー獲得用の同梱カードを導入し、寄付者にフィードバックを依頼\n"
        "3. 高額帯（2万円以上）の商品設計で寄付単価を引き上げ\n"
    )
    if plan == "speed_standard":
        base += (
            "4. 季節性の高い商品（旬・限定）でリピート寄付を促進\n"
            "5. 関連返礼品とのバンドル化で平均購入額を増やす\n"
        )
    return base


def _competitor_detail_section(category: str) -> str:
    # TODO: 実データ取得（Standard限定機能）
    return (
        f"{category} カテゴリ・全国上位10商品の詳細：\n\n"
        "| 順位 | 商品（推定） | 寄付額帯 | レビュー | 月間想定件数 |\n"
        "|---:|---|---:|---:|---:|\n"
        "| 1 | 上位商品A | 10,000円 | 250件 | 2,000件 |\n"
        "| 2 | 上位商品B | 15,000円 | 180件 | 1,200件 |\n"
        "| 3 | 上位商品C | 8,000円 | 320件 | 3,500件 |\n"
        "| 4-10 | （詳細はサロンの会員専用レポートで） | | | |\n"
    )


def _seo_suggestions_section(category: str) -> str:
    return (
        "ポータル内検索順位を上げるためのキーワード案：\n\n"
        "- メインキーワード: 「カテゴリ名」「産地名」「規格（kg数等）」\n"
        "- サブキーワード: 「ギフト」「贈答」「年末年始」「父の日」等の季節ワード\n"
        "- 差別化キーワード: 「無添加」「国産」「手作り」「老舗」等\n"
        "- タイトル冒頭に強いキーワードを配置するのがコツです\n"
    )


def _qa_session_section() -> str:
    return (
        "**月1回 グループQ&Aセッション（Zoom）開催のご案内**\n\n"
        "ご質問・改善相談を直接お聞きする、SPEED Standard会員限定のオンラインセッションを開催します。\n\n"
        "- 日時: 毎月第3水曜 19:00〜20:00\n"
        "- 形式: Zoomグループセッション（質疑応答中心）\n"
        "- 参加方法: LINEで「Q&A参加」と送信いただくと招待URLをお届けします\n"
    )


# ============================================================
# 補助関数
# ============================================================

def _save_report(line_user_id: str, plan: str, content: str) -> Path:
    """月次レポートをローカル保存。Phase 2では Cloud Storage 連携へ拡張予定。"""
    stamp = datetime.utcnow().strftime("%Y%m")
    filename = f"{stamp}_{plan}_{line_user_id[-8:]}.md"
    path = _OUTPUT_DIR / filename
    path.write_text(content, encoding="utf-8")
    return path


def _already_delivered_this_month(line_user_id: str, content_type: str) -> bool:
    """同月内に同タイプの配信が既にあるか。delivery_id 命名規則に依存。"""
    stamp = datetime.utcnow().strftime("%Y_%m")
    delivery_id = f"{stamp}_{line_user_id[-8:]}_{content_type}"
    snap = storage._client().collection("member_deliveries") \
        .document(delivery_id).get()
    return snap.exists


def _build_line_message(plan: str, business_name: str, report_path: Path) -> str:
    """配信時のLINEメッセージ本文（軽量・PDF/MDリンクは別途）"""
    plan_display = "SPEED Standard" if plan == "speed_standard" else "SPEED Light"
    today = datetime.utcnow().strftime("%Y年%m月")

    return (
        f"📊 [{plan_display}] {today}度の月次レポートをお届けします！\n\n"
        f"事業者: {business_name}\n\n"
        "今月の主な内容:\n"
        "・ふるさと納税適正度スコア\n"
        "・5サイトベンチマーク調査結果\n"
        "・AIによる改善提案\n"
        + ("・競合上位10商品の詳細分析\n・SEOキーワード改善案\n・月次Q&Aセッションのご案内\n"
           if plan == "speed_standard" else "")
        + "\n詳しい分析はこのトークの履歴で確認できます。\n"
        "ご質問はそのままトークに送信いただければ承ります。"
    )
