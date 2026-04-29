"""Streamlit用 簡易パスワード認証

ADMIN_PASS（環境変数 or st.secrets）の値で照合。
"""
from __future__ import annotations
import os

import streamlit as st


def _expected_password() -> str | None:
    pw = os.environ.get("ADMIN_PASS")
    if pw and pw != "change_me":
        return pw
    try:
        return st.secrets.get("ADMIN_PASS")  # type: ignore[attr-defined]
    except Exception:
        return None


def require_login() -> None:
    """ログイン済みでなければパスワード入力を促し、未認証ならst.stop()"""
    expected = _expected_password()
    if not expected:
        st.warning("⚠️ ADMIN_PASS 未設定のため認証なしで動作中（開発モード）")
        return

    if st.session_state.get("auth_ok"):
        return

    st.title("🔒 ふるりーど 管理画面")
    st.caption("商談・分析用ツールです。共有パスワードを入力してください。")

    pw = st.text_input("パスワード", type="password", key="login_pw_input")
    if st.button("ログイン", type="primary"):
        if pw == expected:
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    st.stop()
