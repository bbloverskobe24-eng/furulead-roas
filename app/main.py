"""ふるりーどSPEED Bot — FastAPI エントリ"""
import os
import logging
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, MessageAction,
    PushMessageRequest,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent

from app import storage, conversation

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
CHANNEL_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")

storage.init_db()

app = FastAPI(title="ふるりーどSPEED Bot")
parser = WebhookParser(CHANNEL_SECRET) if CHANNEL_SECRET else None


def _line_api():
    config = Configuration(access_token=CHANNEL_TOKEN)
    return MessagingApi(ApiClient(config))


def _build_messages(reply: dict):
    text = reply.get("text", "")
    quick = reply.get("quick_reply")
    msg = TextMessage(text=text)
    if quick:
        msg.quick_reply = QuickReply(items=[
            QuickReplyItem(action=MessageAction(label=c[:20], text=c))
            for c in quick
        ])
    return [msg]


@app.get("/")
def health():
    return {"status": "ok", "service": "furulead-speed-bot"}


@app.post("/line/webhook")
async def webhook(request: Request, x_line_signature: str = Header(None)):
    if not parser:
        raise HTTPException(500, "LINE_CHANNEL_SECRET未設定")
    body = (await request.body()).decode("utf-8")
    try:
        events = parser.parse(body, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(400, "invalid signature")

    for event in events:
        if isinstance(event, FollowEvent):
            _handle_follow(event)
        elif isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
            _handle_message(event)

    return PlainTextResponse("OK")


def _handle_follow(event: FollowEvent):
    uid = event.source.user_id
    reply = conversation.on_follow(uid)
    try:
        _line_api().reply_message(ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=_build_messages(reply),
        ))
    except Exception as e:
        log.error(f"follow reply failed: {e}")


def _handle_message(event: MessageEvent):
    uid = event.source.user_id
    text = event.message.text
    reply = conversation.on_message(uid, text)
    try:
        _line_api().reply_message(ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=_build_messages(reply),
        ))
    except Exception as e:
        log.error(f"message reply failed: {e}")


# ==================================================
# 管理画面配信トリガ
# ==================================================
@app.post("/admin/session/{line_user_id}/deliver")
def deliver_report(line_user_id: str, pdf_url: str):
    """CSO承認後、PDF DLリンクをLINEへPUSH配信"""
    user = storage.get_user(line_user_id)
    if not user:
        raise HTTPException(404, "user not found")
    answers = storage.get_answers(line_user_id)
    name = answers.get("S1") or answers.get("D1") or "事業者"

    text = (
        f"お待たせしました！\n"
        f"「{name}様 ふるさと納税参入予測レポート」が完成しました📄\n\n"
        f"こちらからダウンロードできます👇\n{pdf_url}\n"
        f"（リンク有効期限：7日間）\n\n"
        "---\n"
        "💬 ご質問・相談は、このトークに直接メッセージください。\n"
        "📅 無料相談会をご希望の場合は「相談会希望」と送ってください。"
    )

    try:
        _line_api().push_message(PushMessageRequest(
            to=line_user_id,
            messages=[TextMessage(text=text)],
        ))
        storage.update_user(line_user_id, status="delivered")
        return {"status": "delivered"}
    except Exception as e:
        log.error(f"push failed: {e}")
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
