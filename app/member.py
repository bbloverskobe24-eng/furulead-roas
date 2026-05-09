"""SPEED会員管理ロジック

- 会員ステータス遷移（active / past_due / canceled）
- LINE への通知メッセージ生成
- プラン判定・期間管理
"""
from __future__ import annotations
import os
from datetime import datetime
from typing import Optional

from app import storage

# ============================================================
# プラン判定
# ============================================================

PRICE_TO_PLAN = {
    # 環境変数からPrice ID → 内部プラン名へのマッピング
    # 例: STRIPE_PRICE_LIGHT="price_xxx" / STRIPE_PRICE_STANDARD="price_yyy"
    os.environ.get("STRIPE_PRICE_LIGHT", "price_speed_light_monthly"): "speed_light",
    os.environ.get("STRIPE_PRICE_STANDARD", "price_speed_standard_monthly"): "speed_standard",
}

PLAN_DISPLAY_NAMES = {
    "speed_light": "SPEED Light",
    "speed_standard": "SPEED Standard",
}


def detect_plan_from_price_id(price_id: str) -> Optional[str]:
    """Stripe Price ID から内部プラン名（speed_light/speed_standard）を判定。"""
    return PRICE_TO_PLAN.get(price_id)


def get_display_name(plan: str) -> str:
    return PLAN_DISPLAY_NAMES.get(plan, plan)


# ============================================================
# 会員ステータス遷移
# ============================================================

def activate_membership(line_user_id: str, plan: str,
                        stripe_customer_id: str, stripe_subscription_id: str,
                        period_start: datetime, period_end: datetime,
                        trial_end: Optional[datetime] = None):
    """新規会員を active 状態にする（Stripe webhook受信時）"""
    storage.update_membership(
        line_user_id,
        status="trialing" if trial_end else "active",
        plan=plan,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        current_period_start=period_start,
        current_period_end=period_end,
        trial_end=trial_end,
        cancel_at_period_end=False,
        registered_at=datetime.utcnow(),
        canceled_at=None,
    )


def update_period(line_user_id: str, period_start: datetime, period_end: datetime,
                  cancel_at_period_end: bool = False):
    """課金期間更新（毎月の自動更新時）"""
    storage.update_membership(
        line_user_id,
        current_period_start=period_start,
        current_period_end=period_end,
        cancel_at_period_end=cancel_at_period_end,
    )


def mark_past_due(line_user_id: str):
    """支払い失敗"""
    storage.update_membership(line_user_id, status="past_due")


def mark_canceled(line_user_id: str):
    """解約完了（期間終了時）"""
    storage.update_membership(
        line_user_id,
        status="canceled",
        canceled_at=datetime.utcnow(),
    )


def is_active(line_user_id: str) -> bool:
    """課金有効な会員か（active or trialing）"""
    membership = storage.get_membership(line_user_id) or {}
    return membership.get("status") in ("active", "trialing")


def get_plan(line_user_id: str) -> Optional[str]:
    """現在のプラン（speed_light / speed_standard / None）"""
    membership = storage.get_membership(line_user_id) or {}
    if membership.get("status") in ("active", "trialing"):
        return membership.get("plan")
    return None


# ============================================================
# LINE通知メッセージ生成
# ============================================================

def welcome_message(plan: str) -> str:
    name = get_display_name(plan)
    if plan == "speed_light":
        return (
            f"🎉 {name} へようこそ！\n\n"
            "ご登録ありがとうございます。本日から下記の特典をご利用いただけます。\n\n"
            "📊 月1回の適正度スコア診断\n"
            "🔍 5サイトベンチマーク調査\n"
            "💡 AIによる改善提案\n"
            "📚 LINE限定コンテンツ\n\n"
            "毎月15日に最新レポートをお届けします。\n"
            "ご質問はこちらのトークから直接送ってください。"
        )
    if plan == "speed_standard":
        return (
            f"🎉 {name} へようこそ！\n\n"
            "ご登録ありがとうございます。Light の全機能に加え、以下が追加されます。\n\n"
            "📊 適正度スコア診断 月3回（5日・15日・25日）\n"
            "📈 商品名・SEOキーワード改善案\n"
            "🏆 競合上位10商品の詳細分析\n"
            "💬 オンラインサロン質問・コメント可\n"
            "🎙 月1回 グループQ&Aセッション（Zoom）\n\n"
            "本格活用をぜひお楽しみください。"
        )
    return f"{name} へのご登録ありがとうございます。"


def cancel_message() -> str:
    return (
        "ご利用ありがとうございました。\n"
        "解約手続きを承りました。現在の課金期間終了まではコンテンツ閲覧可能です。\n\n"
        "またのご利用を心よりお待ちしております。"
    )


def payment_failed_message() -> str:
    return (
        "⚠️ 決済が確認できませんでした。\n\n"
        "カード情報の更新をお願いいたします。\n"
        "更新後は自動的にサービスをご利用いただけます。\n\n"
        "数日経ってもご決済が確認できない場合、サービス提供を一時停止させていただきますのでご了承ください。"
    )


def trial_ending_message(plan: str) -> str:
    name = get_display_name(plan)
    return (
        f"🔔 {name} のトライアル期間が3日後に終了します。\n\n"
        "継続をご希望の場合、特別な操作は不要です。トライアル終了後、自動的に課金が開始されます。\n"
        "解約をご希望の場合は、リッチメニューの「マイページ」から手続きいただけます。"
    )
