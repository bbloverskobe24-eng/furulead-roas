"""ふるりーどSPEED CSO管理画面"""
import os
import sys
import pandas as pd
import streamlit as st

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from app import storage, report_generator, uploader  # noqa
from admin import auth, roas_tab  # noqa

st.set_page_config(page_title="ふるりーどSPEED 管理画面", layout="wide")

auth.require_login()

storage.init_db()

st.title("🚀 ふるりーどSPEED 管理画面")
st.caption("CSO用：回答レビュー・PDF生成・承認・配信 / ROAS分析")

tab1, tab2, tab3, tab4 = st.tabs(
    ["📋 セッション一覧", "📄 個別レビュー", "📊 統計", "🎯 ROAS分析"]
)

# ==================================================
# タブ1：セッション一覧
# ==================================================
with tab1:
    try:
        sessions = storage.list_sessions()
        if not sessions:
            st.info("まだセッションがありません。")
        else:
            df = pd.DataFrame(sessions)
            df = df[["line_user_id", "display_name", "course", "status",
                     "completeness", "last_active"]]
            st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"⚠️ Firestore未接続です。GCPサービスアカウント設定後に再デプロイで復活します。\n\n{type(e).__name__}: {e}")

# ==================================================
# タブ2：個別レビュー
# ==================================================
with tab2:
    try:
        sessions = storage.list_sessions()
    except Exception as e:
        st.error(f"⚠️ Firestore未接続です。GCPサービスアカウント設定後に再デプロイで復活します。\n\n{type(e).__name__}: {e}")
        sessions = []
    completed = [s for s in sessions if s["completeness"] >= 100]
    if not completed:
        st.info("レビュー対象（100%回答完了）のセッションはまだありません。")
    else:
        opts = {
            f"{s.get('display_name') or s['line_user_id'][:8]} ({s['course']}) — {s['status']}":
            s["line_user_id"]
            for s in completed
        }
        selected_label = st.selectbox("レビュー対象を選択", list(opts.keys()))
        uid = opts[selected_label]

        user = storage.get_user(uid)
        answers = storage.get_answers(uid)

        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader("ユーザー情報")
            st.write(f"**LINE ID**: `{uid}`")
            st.write(f"**コース**: {user['course']}")
            st.write(f"**Status**: {user['status']}")
            st.write(f"**充足度**: {user['completeness']}%")
            st.write(f"**メール**: {user.get('email') or '未取得'}")

            st.subheader("回答一覧")

            def _qid_key(qid):
                # "D1", "S10" 等を (prefix, numeric) で自然順ソート
                return (qid[0], int(qid[1:]))

            for qid, ans in sorted(answers.items(), key=lambda kv: _qid_key(kv[0])):
                st.write(f"**{qid}**: {ans}")

        with col2:
            st.subheader("アクション")
            if st.button("📄 PDF下書き生成", use_container_width=True):
                with st.spinner("生成中..."):
                    md_path, pdf_path = report_generator.generate_full_report(uid)
                    st.success(f"生成しました: {os.path.basename(pdf_path)}")
                    st.session_state["last_pdf"] = pdf_path
                    st.session_state["last_md"] = md_path

            if "last_pdf" in st.session_state and os.path.exists(st.session_state["last_pdf"]):
                with open(st.session_state["last_pdf"], "rb") as f:
                    st.download_button(
                        "⬇️ PDFダウンロード",
                        f.read(),
                        file_name=os.path.basename(st.session_state["last_pdf"]),
                        mime="application/pdf",
                        use_container_width=True,
                    )
                with open(st.session_state["last_md"], encoding="utf-8") as f:
                    md_content = f.read()
                with st.expander("📝 mdドラフトをプレビュー・編集"):
                    edited = st.text_area("", md_content, height=400)
                    if st.button("💾 md変更を保存"):
                        with open(st.session_state["last_md"], "w", encoding="utf-8") as f:
                            f.write(edited)
                        st.success("保存しました。『PDF再生成』で再ビルドしてください。")

            st.divider()
            st.subheader("配信")

            # Google Driveへ自動アップロード
            auto_upload = st.checkbox("Google Driveへ自動アップロード", value=True)
            pdf_url = st.text_input(
                "PDF配信URL（自動アップロード時は空欄可）",
                key="pdf_url_input",
            )

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("✅ 承認＆LINE配信", use_container_width=True, type="primary"):
                    if auto_upload and "last_pdf" in st.session_state:
                        with st.spinner("Google Driveへアップロード中..."):
                            try:
                                pdf_url = uploader.upload(st.session_state["last_pdf"])
                                st.info(f"アップロード完了: {pdf_url}")
                            except Exception as e:
                                st.error(f"アップロード失敗: {e}")
                                st.stop()

                    if not pdf_url:
                        st.error("PDF配信URLを入力してください")
                    else:
                        import requests
                        base_url = os.environ.get("BASE_URL", "http://localhost:8080")
                        try:
                            r = requests.post(
                                f"{base_url}/admin/session/{uid}/deliver",
                                params={"pdf_url": pdf_url},
                                timeout=10,
                            )
                            if r.status_code == 200:
                                st.success("配信完了しました！")
                            else:
                                st.error(f"配信失敗: {r.status_code} {r.text}")
                        except Exception as e:
                            st.error(f"配信失敗: {e}")
            with col_b:
                if st.button("🚫 ブロック", use_container_width=True):
                    storage.update_user(uid, status="blocked")
                    st.warning("ブロックしました。")

# ==================================================
# タブ3：統計ダッシュボード
# ==================================================
with tab3:
    try:
        sessions = storage.list_sessions()
    except Exception as e:
        st.error(f"⚠️ Firestore未接続です。GCPサービスアカウント設定後に再デプロイで復活します。\n\n{type(e).__name__}: {e}")
        sessions = []
    if not sessions:
        st.info("データがありません。")
    else:
        df = pd.DataFrame(sessions)
        total = len(df)
        by_status = df["status"].fillna("unknown").value_counts()
        completed_n = int(by_status.get("completed", 0) + by_status.get("reviewing", 0)
                          + by_status.get("delivered", 0))
        delivered_n = int(by_status.get("delivered", 0))
        avg_completeness = float(df["completeness"].fillna(0).mean())

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("総セッション数", f"{total}")
        c2.metric("回答完了数", f"{completed_n}", f"{completed_n / total * 100:.0f}% CVR")
        c3.metric("配信済", f"{delivered_n}",
                  f"{delivered_n / total * 100:.0f}% 配信率" if total else "-")
        c4.metric("平均充足度", f"{avg_completeness:.0f}%")
        c5.metric("ブロック", f"{int(by_status.get('blocked', 0))}")

        st.divider()

        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("ステータス別")
            st.bar_chart(by_status)
        with col_r:
            st.subheader("コース別")
            by_course = df["course"].fillna("(未選択)").value_counts()
            st.bar_chart(by_course)

        st.divider()
        st.subheader("日次 新規友だち追加")
        if "added_at" in df.columns:
            added = pd.to_datetime(df["added_at"], errors="coerce", utc=True)
            added = added.dt.tz_convert("Asia/Tokyo").dt.date
            daily = added.value_counts().sort_index()
            if not daily.empty:
                st.line_chart(daily)
            else:
                st.caption("日次データなし")

# ==================================================
# タブ4：ROAS分析（事業者情報入力 → AI → PDF）
# ==================================================
with tab4:
    roas_tab.render()
