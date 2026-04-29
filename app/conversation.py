"""Step返信のコアロジック"""
from __future__ import annotations
import re
from app.questions import (
    get_question, next_question_id, next_unanswered_question_id, get_questions,
)
from app.scoring import calculate_completeness, progress_bar
from app import storage

# 簡易→詳細コースへ引継ぐ回答マッピング（同じ質問内容のもの）
SIMPLE_TO_DETAILED_MAP = {
    "S1": "D1",   # 事業者名
    "S2": "D2",   # 所在地
    "S4": "D12",  # ストーリー
    "S5": "D15",  # メール
}

EMAIL_RE = re.compile(r"^[\w\.\-\+]+@[\w\.\-]+\.\w+$")
EDIT_RE = re.compile(r"^(\d+)\s*問目修正$")


def _progress_line(pct: int) -> str:
    return f"📊 情報充足度：{progress_bar(pct)} {pct}%"


def _format_question(q: dict, pct: int) -> dict:
    """{'text': ..., 'quick_reply': [...]} を返す。"""
    text = f"{q['prompt']}\n\n{_progress_line(pct)}"
    quick = q.get("choices") if q["type"] == "button" else None
    return {"text": text, "quick_reply": quick}


def on_follow(line_user_id: str, display_name: str = None):
    """友だち追加時"""
    storage.upsert_user(line_user_id, display_name)
    return {
        "text": (
            "はじめまして！\n"
            "「ふるりーどSPEED」にご登録ありがとうございます📮\n\n"
            "ふるさと納税への参入を検討されている事業者様向けに、\n"
            '"あなた専用" の参入予測レポートを【無料】でお作りします。\n\n'
            "ご希望の診断コースを選んでください👇"
        ),
        "quick_reply": ["簡易診断（5問・3分）", "詳細診断（15問・10分）"],
    }


def on_message(line_user_id: str, text: str, display_name: str = None):
    """メッセージ受信時の主処理"""
    storage.upsert_user(line_user_id, display_name)
    user = storage.get_user(line_user_id) or {}
    text = (text or "").strip()

    # コース未選択
    if not user.get("course"):
        if "簡易" in text:
            storage.update_user(line_user_id, course="simple", current_q=None, status="in_progress")
            return _send_next_question(line_user_id, "simple", course_start=True, simple=True)
        if "詳細" in text:
            storage.update_user(line_user_id, course="detailed", current_q=None, status="in_progress")
            return _send_next_question(line_user_id, "detailed", course_start=True, simple=False)
        return {
            "text": "どちらの診断コースをご希望ですか？👇",
            "quick_reply": ["簡易診断（5問・3分）", "詳細診断（15問・10分）"],
        }

    course = user["course"]

    # コマンド類
    if text in ("やり直し", "やり直す"):
        storage.clear_answers(line_user_id)
        storage.update_user(line_user_id, course=None, current_q=None,
                            completeness=0, status="in_progress")
        return {
            "text": "診断をリセットしました。もう一度コースを選んでください👇",
            "quick_reply": ["簡易診断（5問・3分）", "詳細診断（15問・10分）"],
        }
    if text == "簡易に変更":
        storage.clear_answers(line_user_id)
        storage.update_user(line_user_id, course="simple", current_q=None,
                            completeness=0, status="in_progress")
        return _send_next_question(line_user_id, "simple", course_start=True, simple=True)
    if text == "詳細に変更":
        # 簡易コースの回答を詳細コースへ引き継ぐ
        old_answers = storage.get_answers(line_user_id)
        storage.clear_answers(line_user_id)
        for src, dst in SIMPLE_TO_DETAILED_MAP.items():
            if src in old_answers:
                storage.save_answer(line_user_id, dst, old_answers[src])
        # 引継いだ分で充足度を再計算
        carried = set(SIMPLE_TO_DETAILED_MAP[k] for k in old_answers if k in SIMPLE_TO_DETAILED_MAP)
        pct = calculate_completeness("detailed", carried)
        storage.update_user(line_user_id, course="detailed", current_q=None,
                            completeness=pct, status="in_progress")
        return _send_next_question(line_user_id, "detailed", course_start=True,
                                   simple=False, carried=len(carried))

    # 「N問目修正」コマンド（completedまでは許可、reviewing/delivered/blockedは拒否）
    m_edit = EDIT_RE.match(text)
    if m_edit:
        if user.get("status") in ("reviewing", "delivered", "blocked"):
            return {
                "text": (
                    "レポート作成フェーズに入っているため、\n"
                    "回答の修正は受け付けられません🙏\n"
                    "内容変更のご相談は、このトークにメッセージをお願いします。"
                ),
            }
        n = int(m_edit.group(1))
        qs = get_questions(course)
        if not (1 <= n <= len(qs)):
            label = "簡易" if course == "simple" else "詳細"
            return {
                "text": (
                    f"{label}診断は{len(qs)}問までです。\n"
                    f"例：「3問目修正」と送ってください。"
                ),
            }
        target = qs[n - 1]
        storage.delete_answer(line_user_id, target["id"])
        answered = set(storage.get_answers(line_user_id).keys())
        pct = calculate_completeness(course, answered)
        storage.update_user(
            line_user_id,
            current_q=target["id"],
            completeness=pct,
            status="in_progress",
        )
        reply = _format_question(target, pct)
        reply["text"] = (
            f"{n}問目（{target['id']}）を修正します。もう一度ご回答ください👇\n\n"
            + reply["text"]
        )
        return reply

    # 完了済み
    if user.get("status") in ("completed", "reviewing", "delivered"):
        return {
            "text": (
                "既にご回答いただいています。\n"
                "レポートをお送りするまでお待ちください。\n\n"
                "（再度やり直す場合は「やり直し」と送ってください。\n"
                "　特定の質問だけ修正する場合は「3問目修正」のように送ってください）"
            ),
        }

    # 現在の質問を特定
    current_qid = user.get("current_q")
    if current_qid is None:
        return _send_next_question(line_user_id, course, course_start=True,
                                   simple=(course == "simple"))

    q = get_question(course, current_qid)
    if q is None:
        return {"text": "エラー：質問が見つかりませんでした。"}

    # バリデーション
    if q.get("validate") == "email":
        if not EMAIL_RE.match(text):
            return {
                "text": (
                    "メールアドレスの形式が正しくないようです📧\n"
                    "もう一度お試しください（例：taro@example.com）"
                ),
            }

    if q["type"] == "button":
        choices = q.get("choices", [])
        if text not in choices:
            return {
                "text": "以下から選んでください👇",
                "quick_reply": choices,
            }

    # 回答保存
    storage.save_answer(line_user_id, current_qid, text)
    if q["id"] in ("S5", "D15"):
        storage.update_user(line_user_id, email=text)

    # 充足度更新
    answered = set(storage.get_answers(line_user_id).keys())
    pct = calculate_completeness(course, answered)
    storage.update_user(line_user_id, completeness=pct)

    # 次の質問（既回答はスキップ）
    answered = set(storage.get_answers(line_user_id).keys())
    next_qid = next_unanswered_question_id(course, answered)
    if next_qid is None:
        # 完了
        storage.update_user(line_user_id, status="completed", current_q=None,
                            completeness=100)
        _trigger_cso_notification(line_user_id)
        return _completion_message(course)

    storage.update_user(line_user_id, current_q=next_qid)
    next_q = get_question(course, next_qid)
    return _format_question(next_q, pct)


def _send_next_question(line_user_id, course, course_start, simple, carried: int = 0):
    # 既回答をスキップして最初の未回答質問を探す
    answered = set(storage.get_answers(line_user_id).keys())
    first_qid = next_unanswered_question_id(course, answered)
    if first_qid is None:
        # 引継いだ質問で既に全部埋まっている場合（まれ）
        storage.update_user(line_user_id, status="completed",
                            current_q=None, completeness=100)
        _trigger_cso_notification(line_user_id)
        return _completion_message(course)

    first = get_question(course, first_qid)
    storage.update_user(line_user_id, current_q=first_qid)

    intro = ""
    if course_start:
        if simple:
            intro = ("ありがとうございます！簡易診断スタートです💨\n"
                     "（途中で変更したい場合は「やり直し」と送ってください）\n\n")
        elif carried > 0:
            intro = (f"詳細診断に切り替えました💨\n"
                     f"簡易診断の回答{carried}件を引き継ぎました。\n"
                     f"残りの質問にお答えください。\n\n")
        else:
            intro = ("詳細診断スタートです💨\n"
                     "途中で中断しても、再度メッセージを送ればその続きから再開できます。\n\n")

    pct = calculate_completeness(course, answered)
    reply = _format_question(first, pct)
    reply["text"] = intro + reply["text"]
    return reply


def _completion_message(course):
    bar = progress_bar(100)
    if course == "simple":
        return {
            "text": (
                "🎉 ご回答ありがとうございました！\n\n"
                f"📊 情報充足度：{bar} 100%\n\n"
                "CSO担当が内容を拝見し、\n"
                "【3営業日以内】に参入予測レポートPDFをお送りします。\n\n"
                "届くまでしばらくお待ちください✨\n\n"
                "👉 詳細診断（15問版）に切り替えて、\n"
                "より本格的なレポートをご希望の場合は\n"
                "「詳細に変更」と送ってください。"
            ),
        }
    return {
        "text": (
            "🎉 全問ご回答ありがとうございました！\n\n"
            f"📊 情報充足度：{bar} 100%\n\n"
            "CSO担当が内容を詳細に分析し、\n"
            "【3営業日以内】に専用レポートをPDFでお送りします。\n\n"
            "本格的な分析レポート（10〜15ページ）をお楽しみに✨"
        ),
    }


def _trigger_cso_notification(line_user_id):
    """CSOへChatwork通知"""
    import os
    from app import notifier
    user = storage.get_user(line_user_id) or {}
    answers = storage.get_answers(line_user_id)
    course = user.get("course", "simple")

    name = answers.get("S1") or answers.get("D1") or "（未回答）"
    loc = answers.get("S2") or answers.get("D2") or "（未回答）"
    base_url = os.environ.get("BASE_URL", "http://localhost:8080")

    try:
        notifier.notify_cso_report_ready(
            user_name=name, user_location=loc, course=course,
            line_user_id=line_user_id, base_url=base_url,
        )
    except Exception as e:
        print(f"[conversation] 通知失敗: {e}")
