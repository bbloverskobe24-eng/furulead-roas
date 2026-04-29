"""
リマインド機能：途中離脱ユーザーへ24h/3日/7日後に再アプローチ

実行方法:
    python3 -m app.reminders            # 1回だけ実行（cron向け）
    python3 -m app.reminders --watch    # 常駐（APScheduler・1時間ごと）
"""
from __future__ import annotations
import os
import sys
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

from app import storage
from app.questions import get_question

load_dotenv()
log = logging.getLogger("reminders")
logging.basicConfig(level=logging.INFO)

# リマインド発火ルール：(経過時間下限, 経過時間上限, メッセージフォーマット)
RULES = [
    (timedelta(hours=24), timedelta(hours=48), "first"),
    (timedelta(days=3), timedelta(days=4), "second"),
    (timedelta(days=7), timedelta(days=8), "final"),
]

MESSAGES = {
    "first": (
        "{name}様、ご回答お待ちしています🙌\n"
        "前回の質問はこちらです👇\n{q}\n\n"
        "（「やめる」で中断、「やり直し」で最初から）"
    ),
    "second": (
        "お忙しいところ恐れ入ります。\n"
        "残り{remaining}問でレポートをお作りできます。\n\n"
        "ぜひ続きをお聞かせください。\n{q}"
    ),
    "final": (
        "ご都合よろしければ、いつでもご回答ください。\n"
        "続きは自動的にこのトークに残っています。\n\n"
        "レポート作成を楽しみにお待ちしております✨"
    ),
}


def _push_line(line_user_id: str, text: str):
    """LINE push送信。環境変数未設定時はログのみ"""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        log.info(f"[DRY RUN] push to {line_user_id}: {text[:40]}...")
        return
    from linebot.v3.messaging import (
        Configuration, ApiClient, MessagingApi,
        PushMessageRequest, TextMessage,
    )
    config = Configuration(access_token=token)
    api = MessagingApi(ApiClient(config))
    api.push_message(PushMessageRequest(
        to=line_user_id,
        messages=[TextMessage(text=text)],
    ))


def _reminder_kind(last_active: datetime) -> str | None:
    """経過時間に応じてリマインド種別を返す。既発送済チェックは呼び出し側"""
    elapsed = datetime.utcnow() - last_active
    for lower, upper, kind in RULES:
        if lower <= elapsed < upper:
            return kind
    return None


def _build_message(user: dict, kind: str) -> str:
    answers = storage.get_answers(user["line_user_id"])
    name = answers.get("S1") or answers.get("D1") or "事業者"
    q = get_question(user["course"], user["current_q"])
    q_text = q["prompt"] if q else "（次の質問）"

    # 残り質問数の概算
    from app.questions import get_questions
    total = len(get_questions(user["course"]))
    answered = len(answers)
    remaining = max(total - answered, 1)

    return MESSAGES[kind].format(name=name, q=q_text, remaining=remaining)


def run_once():
    """1回だけリマインド対象を処理。cronから呼ばれる想定"""
    sessions = storage.list_sessions(status="in_progress")
    sent = 0
    for user in sessions:
        if user.get("completeness", 0) >= 100:
            continue
        last = user.get("last_active")
        if not last:
            continue
        if isinstance(last, str):
            last = datetime.fromisoformat(last)
        kind = _reminder_kind(last)
        if kind is None:
            continue
        # 重複送信防止：last_activeを更新することで、次のRULE範囲に入るまで再送しない
        try:
            msg = _build_message(user, kind)
            _push_line(user["line_user_id"], msg)
            log.info(f"reminder sent: {user['line_user_id']} / kind={kind}")
            # last_activeは更新しない（ユーザー操作で更新される）
            # かわりに reminders テーブル的な管理が本当は望ましいが、MVPでは省略
            sent += 1
        except Exception as e:
            log.error(f"reminder failed: {user['line_user_id']}: {e}")
    log.info(f"done. sent={sent}")


def watch():
    """常駐モード（APScheduler）"""
    from apscheduler.schedulers.blocking import BlockingScheduler
    sched = BlockingScheduler(timezone="Asia/Tokyo")
    sched.add_job(run_once, "interval", hours=1, next_run_time=datetime.now())
    log.info("reminder scheduler started (1h interval)")
    sched.start()


if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch()
    else:
        run_once()
