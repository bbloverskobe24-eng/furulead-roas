"""Streamlit Community Cloud用 ルートエントリポイント

Streamlit Cloudはリポジトリルート直下のstreamlit_app.pyを自動的に拾う。
このファイルは admin/streamlit_app.py をそのまま読み込むラッパー。
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

# Streamlit Cloud のSecrets機能で設定された値を環境変数に反映
import streamlit as st  # noqa: E402

for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "ADMIN_PASS",
            "CHATWORK_API_TOKEN", "CHATWORK_ROOM_ID"):
    try:
        val = st.secrets.get(key)  # type: ignore[attr-defined]
    except Exception:
        val = None
    if val and not os.environ.get(key):
        os.environ[key] = str(val)

# 本体起動
runpy_target = BASE / "admin" / "streamlit_app.py"
exec(compile(runpy_target.read_text(encoding="utf-8"), str(runpy_target), "exec"))
