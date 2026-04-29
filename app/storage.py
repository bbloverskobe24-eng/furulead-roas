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
