"""Firestore永続化層（旧SQLiteから移行）

データ構造:
  users/{line_user_id}
    ├── 基本フィールド（display_name, course, status, completeness, ...）
    ├── answers/{question_id}  — 各質問への回答
    └── reports/{report_id}     — 生成レポート
"""
from __future__ import annotations
import os
from datetime import datetime
from typing import Optional
from google.cloud import firestore

PROJECT_ID = os.environ.get("GCP_PROJECT", "furulead-speed-bot")

_db = None


def _client() -> firestore.Client:
    """Firestoreクライアントのシングルトン"""
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT_ID)
    return _db


def init_db():
    """Firestoreは自動作成のため何もしない（インターフェース互換のみ）"""
    pass


def _now():
    return datetime.utcnow()


# ==================================================
# users
# ==================================================
def upsert_user(line_user_id, display_name=None):
    doc = _client().collection("users").document(line_user_id)
    snap = doc.get()
    if not snap.exists:
        doc.set({
            "line_user_id": line_user_id,
            "display_name": display_name,
            "added_at": _now(),
            "last_active": _now(),
            "status": "in_progress",
            "completeness": 0,
            "course": None,
            "current_q": None,
            "email": None,
        })
    else:
        doc.update({"last_active": _now()})


def get_user(line_user_id) -> Optional[dict]:
    snap = _client().collection("users").document(line_user_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    data["line_user_id"] = snap.id
    return data


def update_user(line_user_id, **fields):
    if not fields:
        return
    _client().collection("users").document(line_user_id).update(fields)


def list_sessions(status: Optional[str] = None):
    col = _client().collection("users")
    if status:
        col = col.where("status", "==", status)
    col = col.order_by("last_active", direction=firestore.Query.DESCENDING)
    result = []
    for snap in col.stream():
        data = snap.to_dict()
        data["line_user_id"] = snap.id
        result.append(data)
    return result


# ==================================================
# answers
# ==================================================
def _answers_col(line_user_id):
    return _client().collection("users").document(line_user_id).collection("answers")


def save_answer(line_user_id, question_id, answer_text):
    _answers_col(line_user_id).document(question_id).set({
        "question_id": question_id,
        "answer_text": answer_text,
        "answered_at": _now(),
    })


def clear_answers(line_user_id):
    col = _answers_col(line_user_id)
    batch = _client().batch()
    count = 0
    for snap in col.stream():
        batch.delete(snap.reference)
        count += 1
        if count >= 400:  # Firestore batch limit 500
            batch.commit()
            batch = _client().batch()
            count = 0
    if count > 0:
        batch.commit()


def delete_answer(line_user_id, question_id):
    _answers_col(line_user_id).document(question_id).delete()


def get_answers(line_user_id) -> dict:
    return {
        snap.id: snap.to_dict().get("answer_text", "")
        for snap in _answers_col(line_user_id).stream()
    }


# ==================================================
# reports
# ==================================================
def _reports_col(line_user_id):
    return _client().collection("users").document(line_user_id).collection("reports")


def create_report(line_user_id, pdf_path, pdf_url=None) -> str:
    doc_ref = _reports_col(line_user_id).document()
    doc_ref.set({
        "line_user_id": line_user_id,
        "generated_at": _now(),
        "pdf_path": pdf_path,
        "pdf_url": pdf_url,
    })
    return doc_ref.id


def approve_report(report_id, reviewed_by, line_user_id=None):
    # 旧シグネチャ互換: line_user_id 省略時は全users検索（将来的要修正）
    if line_user_id:
        _reports_col(line_user_id).document(report_id).update({
            "reviewed_by": reviewed_by,
            "approved_at": _now(),
        })


def mark_delivered(report_id, line_user_id=None):
    if line_user_id:
        _reports_col(line_user_id).document(report_id).update({
            "delivered_at": _now(),
        })


# ==================================================
# membership (SPEED会員機能)
# ==================================================
def update_membership(line_user_id: str, **fields):
    """会員情報を user.membership.* に保存。"""
    if not fields:
        return
    user_ref = _client().collection("users").document(line_user_id)
    snap = user_ref.get()
    if not snap.exists:
        # 念のためuserを作成
        upsert_user(line_user_id)
    update_data = {f"membership.{k}": v for k, v in fields.items()}
    update_data["membership.updated_at"] = _now()
    user_ref.update(update_data)


def get_membership(line_user_id: str) -> Optional[dict]:
    user = get_user(line_user_id)
    if not user:
        return None
    return user.get("membership") or {}


def list_active_members(plan: Optional[str] = None) -> list:
    """課金中（active）の会員一覧。月次配信バッチ用。"""
    col = _client().collection("users").where("membership.status", "==", "active")
    if plan:
        col = col.where("membership.plan", "==", plan)
    result = []
    for snap in col.stream():
        data = snap.to_dict()
        data["line_user_id"] = snap.id
        result.append(data)
    return result


def find_user_by_stripe_customer(stripe_customer_id: str) -> Optional[dict]:
    """Stripe customer ID から user を逆引き（webhook処理用）。"""
    snaps = _client().collection("users") \
        .where("membership.stripe_customer_id", "==", stripe_customer_id) \
        .limit(1).stream()
    for snap in snaps:
        data = snap.to_dict()
        data["line_user_id"] = snap.id
        return data
    return None


def save_member_event(event_id: str, event_type: str, line_user_id: Optional[str],
                      raw_data: dict):
    """Stripe webhook イベントの監査ログ。冪等性のため event_id をdoc IDに使用。"""
    _client().collection("member_events").document(event_id).set({
        "event_id": event_id,
        "type": event_type,
        "line_user_id": line_user_id,
        "stripe_event_data": raw_data,
        "processed_at": _now(),
    }, merge=True)


def is_event_already_processed(event_id: str) -> bool:
    snap = _client().collection("member_events").document(event_id).get()
    return snap.exists


def record_member_delivery(line_user_id: str, plan: str, content_type: str,
                            related_url: Optional[str] = None,
                            delivery_status: str = "sent"):
    """月次配信履歴。delivery_id 自動生成（YYYY_MM_uid_type形式）。"""
    now = _now()
    delivery_id = f"{now.strftime('%Y_%m')}_{line_user_id[-8:]}_{content_type}"
    _client().collection("member_deliveries").document(delivery_id).set({
        "delivery_id": delivery_id,
        "line_user_id": line_user_id,
        "plan": plan,
        "content_type": content_type,
        "related_url": related_url,
        "delivery_status": delivery_status,
        "delivered_at": now,
    })
