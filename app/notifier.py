"""Chatwork通知"""
import os
import requests

CHATWORK_API = "https://api.chatwork.com/v2"


def notify_cso_report_ready(user_name: str, user_location: str,
                            course: str, line_user_id: str,
                            base_url: str):
    token = os.environ.get("CHATWORK_API_TOKEN")
    room_id = os.environ.get("CHATWORK_ROOM_ID", "326433964")
    if not token:
        print("[notifier] CHATWORK_API_TOKEN未設定のためスキップ")
        return

    body = f"""[info][title]🚨 ふるりーどSPEED 新規レポート生成依頼[/title]
事業者名：{user_name}
所在地：{user_location}
コース：{"簡易（5問）" if course == "simple" else "詳細（15問）"}
LINE User ID：{line_user_id}

▼ 管理画面で確認
{base_url}/admin/session/{line_user_id}
[/info]"""

    try:
        r = requests.post(
            f"{CHATWORK_API}/rooms/{room_id}/messages",
            headers={"X-ChatWorkToken": token},
            data={"body": body},
            timeout=10,
        )
        r.raise_for_status()
        print(f"[notifier] Chatwork通知OK: {r.status_code}")
    except Exception as e:
        print(f"[notifier] Chatwork通知失敗: {e}")
