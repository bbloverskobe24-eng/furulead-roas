"""Stripe Webhook処理 + Checkout Session生成

主要機能:
- Webhook署名検証 + イベントディスパッチ
- Checkout Session（サブスクリプション）作成
- Customer Portal リダイレクト
- 冪等性（event_id重複排除）
"""
from __future__ import annotations
import os
import logging
from datetime import datetime, timezone
from typing import Optional

import stripe

from app import storage, member

log = logging.getLogger("stripe_handler")

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")

if STRIPE_API_KEY:
    stripe.api_key = STRIPE_API_KEY


def is_configured() -> bool:
    """Stripeが設定されているか（テスト/本番キーがある）"""
    return bool(STRIPE_API_KEY)


def _ts_to_dt(ts: Optional[int]) -> Optional[datetime]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


# ============================================================
# Checkout Session（決済画面URLを返す）
# ============================================================

def create_checkout_session(line_user_id: str, plan: str,
                             user_email: Optional[str] = None) -> str:
    """サブスクリプション用 Stripe Checkout Session を生成し、決済URLを返す。

    Args:
        line_user_id: LINE user ID
        plan: "light" | "standard"
        user_email: 任意（Stripe Customer作成時に紐付け）

    Returns:
        Stripe Checkout のURL
    """
    if not is_configured():
        raise RuntimeError("Stripe未設定: STRIPE_API_KEYを環境変数に設定してください")

    price_id_map = {
        "light": os.environ.get("STRIPE_PRICE_LIGHT"),
        "standard": os.environ.get("STRIPE_PRICE_STANDARD"),
    }
    price_id = price_id_map.get(plan)
    if not price_id:
        raise ValueError(
            f"Unknown plan: {plan}. STRIPE_PRICE_{plan.upper()} が未設定です。"
        )

    # 既存customer取得 or 新規作成
    membership = storage.get_membership(line_user_id) or {}
    customer_id = membership.get("stripe_customer_id")
    if not customer_id:
        customer = stripe.Customer.create(
            email=user_email,
            metadata={"line_user_id": line_user_id},
        )
        customer_id = customer.id
        storage.update_membership(line_user_id, stripe_customer_id=customer_id)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{BASE_URL}/member/welcome?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{BASE_URL}/member/cancel",
        subscription_data={
            "metadata": {"line_user_id": line_user_id},
            # トライアル付与する場合は以下のコメントを外す（例: 7日間）
            # "trial_period_days": 7,
        },
        # 日本円・税込表示等はStripe Dashboard側で設定
    )
    return session.url


def create_portal_session(line_user_id: str) -> str:
    """Customer Portal（解約・カード更新）URLを返す。"""
    if not is_configured():
        raise RuntimeError("Stripe未設定")

    membership = storage.get_membership(line_user_id) or {}
    customer_id = membership.get("stripe_customer_id")
    if not customer_id:
        raise ValueError("Stripe customer未登録のユーザーです")

    portal = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{BASE_URL}/member/portal_return",
    )
    return portal.url


# ============================================================
# Webhook処理
# ============================================================

def verify_and_parse_event(payload: bytes, sig_header: str) -> dict:
    """Stripe webhook署名検証してイベントを返す。検証失敗時は例外。"""
    if not STRIPE_WEBHOOK_SECRET:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET 未設定")
    return stripe.Webhook.construct_event(
        payload, sig_header, STRIPE_WEBHOOK_SECRET
    )


def handle_event(event: dict) -> dict:
    """Webhookイベントを処理。冪等性のため event_id チェック。

    Returns:
        {"status": "ok" | "skipped" | "ignored", "reason": ...}
    """
    event_id = event.get("id", "")
    event_type = event.get("type", "")

    # 冪等性チェック
    if event_id and storage.is_event_already_processed(event_id):
        log.info(f"Stripe event already processed: {event_id}")
        return {"status": "skipped", "reason": "already processed"}

    # ディスパッチ
    handler = _EVENT_HANDLERS.get(event_type)
    if not handler:
        # 監査ログのみ残してスキップ
        storage.save_member_event(event_id, event_type, None, event.get("data", {}))
        return {"status": "ignored", "reason": f"no handler for {event_type}"}

    try:
        result = handler(event)
        storage.save_member_event(
            event_id, event_type, result.get("line_user_id"),
            event.get("data", {})
        )
        return {"status": "ok", **result}
    except Exception as e:
        log.exception(f"Error handling Stripe event {event_id} ({event_type})")
        storage.save_member_event(event_id, event_type, None,
                                   {"error": str(e), "data": event.get("data", {})})
        raise


# ------------------------------------------------------------
# 各イベント別ハンドラ
# ------------------------------------------------------------

def _extract_line_user_id(obj: dict) -> Optional[str]:
    """subscription / invoice オブジェクトから line_user_id を抽出。

    優先順位: metadata.line_user_id → customer の metadata
    """
    metadata = obj.get("metadata") or {}
    if metadata.get("line_user_id"):
        return metadata["line_user_id"]

    # customer ID から逆引き
    customer_id = obj.get("customer")
    if customer_id:
        user = storage.find_user_by_stripe_customer(customer_id)
        if user:
            return user["line_user_id"]

    return None


def _handle_subscription_created(event: dict) -> dict:
    sub = event["data"]["object"]
    line_user_id = _extract_line_user_id(sub)
    if not line_user_id:
        return {"line_user_id": None, "result": "no line_user_id"}

    items = sub.get("items", {}).get("data", [])
    price_id = items[0]["price"]["id"] if items else None
    plan = member.detect_plan_from_price_id(price_id) if price_id else None

    member.activate_membership(
        line_user_id=line_user_id,
        plan=plan or "unknown",
        stripe_customer_id=sub.get("customer", ""),
        stripe_subscription_id=sub.get("id", ""),
        period_start=_ts_to_dt(sub.get("current_period_start")),
        period_end=_ts_to_dt(sub.get("current_period_end")),
        trial_end=_ts_to_dt(sub.get("trial_end")),
    )
    return {"line_user_id": line_user_id, "plan": plan, "result": "activated"}


def _handle_subscription_updated(event: dict) -> dict:
    sub = event["data"]["object"]
    line_user_id = _extract_line_user_id(sub)
    if not line_user_id:
        return {"line_user_id": None, "result": "no line_user_id"}

    member.update_period(
        line_user_id=line_user_id,
        period_start=_ts_to_dt(sub.get("current_period_start")),
        period_end=_ts_to_dt(sub.get("current_period_end")),
        cancel_at_period_end=bool(sub.get("cancel_at_period_end")),
    )
    return {"line_user_id": line_user_id, "result": "updated"}


def _handle_subscription_deleted(event: dict) -> dict:
    sub = event["data"]["object"]
    line_user_id = _extract_line_user_id(sub)
    if not line_user_id:
        return {"line_user_id": None, "result": "no line_user_id"}

    member.mark_canceled(line_user_id)
    return {"line_user_id": line_user_id, "result": "canceled"}


def _handle_invoice_paid(event: dict) -> dict:
    inv = event["data"]["object"]
    line_user_id = _extract_line_user_id(inv)
    return {"line_user_id": line_user_id, "result": "invoice_paid"}


def _handle_invoice_payment_failed(event: dict) -> dict:
    inv = event["data"]["object"]
    line_user_id = _extract_line_user_id(inv)
    if line_user_id:
        member.mark_past_due(line_user_id)
    return {"line_user_id": line_user_id, "result": "past_due"}


def _handle_trial_will_end(event: dict) -> dict:
    sub = event["data"]["object"]
    line_user_id = _extract_line_user_id(sub)
    return {"line_user_id": line_user_id, "result": "trial_will_end"}


_EVENT_HANDLERS = {
    "customer.subscription.created": _handle_subscription_created,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_deleted,
    "invoice.paid": _handle_invoice_paid,
    "invoice.payment_failed": _handle_invoice_payment_failed,
    "customer.subscription.trial_will_end": _handle_trial_will_end,
}
