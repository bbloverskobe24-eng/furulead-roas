"""ふるりーどSPEED Bot — FastAPI エントリ"""
import os
import logging
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import PlainTextResponse, RedirectResponse, JSONResponse
from dotenv import load_dotenv

from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage, QuickReply, QuickReplyItem, MessageAction,
    PushMessageRequest,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent

from app import storage, conversation, member, stripe_handler

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


# ==================================================
# SPEED会員機能（Stripe決済）
# ==================================================
@app.post("/webhook/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    """Stripe Webhook受信エンドポイント。署名検証＋イベント処理。"""
    if not stripe_handler.is_configured():
        raise HTTPException(503, "Stripe未設定")

    payload = await request.body()
    try:
        event = stripe_handler.verify_and_parse_event(payload, stripe_signature)
    except Exception as e:
        log.error(f"stripe signature verify failed: {e}")
        raise HTTPException(400, "invalid signature")

    try:
        result = stripe_handler.handle_event(event)
    except Exception as e:
        log.exception(f"stripe event handling error: {e}")
        # Stripeに5xxを返すと自動リトライされるので500
        raise HTTPException(500, "event processing failed")

    # ステータス変化に応じてLINE通知（active化・解約・支払失敗）
    line_user_id = result.get("line_user_id")
    res_type = result.get("result")
    if line_user_id and res_type:
        try:
            _push_member_notification(line_user_id, res_type, result.get("plan"))
        except Exception as e:
            log.error(f"member push notify failed: {e}")

    return JSONResponse(result)


def _push_member_notification(line_user_id: str, result_type: str, plan: str = None):
    """会員ステータス変化に応じたLINE通知。"""
    text = None
    if result_type == "activated" and plan:
        text = member.welcome_message(plan)
    elif result_type == "canceled":
        text = member.cancel_message()
    elif result_type == "past_due":
        text = member.payment_failed_message()
    elif result_type == "trial_will_end" and plan:
        text = member.trial_ending_message(plan)

    if text:
        _line_api().push_message(PushMessageRequest(
            to=line_user_id,
            messages=[TextMessage(text=text)],
        ))


@app.get("/member/checkout")
def member_checkout(line_user_id: str, plan: str):
    """Stripe Checkout画面のURLを返す（LIFF会員ページから呼び出される）。

    Args:
        line_user_id: LINE user ID（LIFF SDKから取得）
        plan: "light" | "standard"
    """
    if plan not in ("light", "standard"):
        raise HTTPException(400, "plan は light か standard を指定してください")

    if not stripe_handler.is_configured():
        raise HTTPException(503, "Stripe未設定")

    try:
        url = stripe_handler.create_checkout_session(line_user_id, plan)
    except Exception as e:
        log.exception("checkout session creation failed")
        raise HTTPException(500, str(e))

    return RedirectResponse(url, status_code=303)


@app.get("/member/portal")
def member_portal(line_user_id: str):
    """Stripe Customer Portal（解約・カード更新）へリダイレクト。"""
    if not stripe_handler.is_configured():
        raise HTTPException(503, "Stripe未設定")

    try:
        url = stripe_handler.create_portal_session(line_user_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        log.exception("portal session creation failed")
        raise HTTPException(500, str(e))

    return RedirectResponse(url, status_code=303)


@app.get("/member/welcome")
def member_welcome(session_id: str = None):
    """Checkout完了後のリダイレクト先（LIFFから戻る時に表示）"""
    return JSONResponse({
        "status": "ok",
        "message": "ご登録ありがとうございます！LINEのトークルームをご確認ください。",
        "session_id": session_id,
    })


@app.get("/member/cancel")
def member_cancel():
    """Checkoutキャンセル時のリダイレクト先"""
    return JSONResponse({
        "status": "canceled",
        "message": "お手続きを中止しました。",
    })


@app.get("/member/portal_return")
def member_portal_return():
    """Customer Portalから戻ってきた時の表示"""
    return JSONResponse({
        "status": "ok",
        "message": "お手続きありがとうございました。LINEに戻ってご確認ください。",
    })


@app.get("/member/status")
def member_status(line_user_id: str):
    """会員ステータス取得（管理画面・LIFFから）"""
    membership = storage.get_membership(line_user_id) or {}
    return JSONResponse({
        "line_user_id": line_user_id,
        "status": membership.get("status", "none"),
        "plan": membership.get("plan"),
        "current_period_end": str(membership.get("current_period_end") or ""),
        "cancel_at_period_end": membership.get("cancel_at_period_end", False),
    })


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
