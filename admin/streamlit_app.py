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


def _firestore_available() -> bool:
    """GCP認証情報が利用可能かを即座に判定（Firestore接続試行はしない）"""
    try:
        import google.auth
        google.auth.default()
        return True
    except Exception:
        return False


_FIRESTORE_OK = _firestore_available()
_FIRESTORE_ERR = "⚠️ Firestore未接続です。GCPサービスアカウント設定後に再デプロイで復活します。"

st.title("🚀 ふるりーどSPEED 管理画面")
st.caption("CSO用：回答レビュー・PDF生成・承認・配信 / ROAS分析")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📋 セッション一覧", "📄 個別レビュー", "📊 統計", "🎯 ROAS分析", "⚡ SPEED会員管理"]
)

# ==================================================
# タブ1：セッション一覧
# ==================================================
with tab1:
    if not _FIRESTORE_OK:
        st.error(_FIRESTORE_ERR)
    else:
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
            st.error(f"{_FIRESTORE_ERR}\n\n{type(e).__name__}: {e}")

# ==================================================
# タブ2：個別レビュー
# ==================================================
with tab2:
    if not _FIRESTORE_OK:
        st.error(_FIRESTORE_ERR)
        sessions = []
    else:
        try:
            sessions = storage.list_sessions()
        except Exception as e:
            st.error(f"{_FIRESTORE_ERR}\n\n{type(e).__name__}: {e}")
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
    if not _FIRESTORE_OK:
        st.error(_FIRESTORE_ERR)
        sessions = []
    else:
        try:
            sessions = storage.list_sessions()
        except Exception as e:
            st.error(f"{_FIRESTORE_ERR}\n\n{type(e).__name__}: {e}")
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

# ==================================================
# タブ5：SPEED会員管理
# ==================================================
with tab5:
    st.subheader("⚡ SPEED会員管理")
    st.caption(
        "公式LINE有料会員（SPEED Light / Standard）の一覧・配信履歴・手動配信操作"
    )

    if not _FIRESTORE_OK:
        st.error(_FIRESTORE_ERR)
    else:
        from datetime import datetime, timedelta

        # ----- 会員一覧取得 -----
        try:
            db = storage._client()
            all_users = []
            for snap in db.collection("users").stream():
                data = snap.to_dict()
                membership = data.get("membership") or {}
                if membership.get("plan"):
                    data["line_user_id"] = snap.id
                    all_users.append(data)
        except Exception as e:
            st.error(f"会員データ取得失敗: {type(e).__name__}: {e}")
            all_users = []

        # ----- KPIサマリ -----
        st.markdown("##### 📈 KPIサマリ")
        active_users = [u for u in all_users if (u.get("membership") or {}).get("status") in ("active", "trialing")]
        light = [u for u in active_users if (u.get("membership") or {}).get("plan") == "speed_light"]
        standard = [u for u in active_users if (u.get("membership") or {}).get("plan") == "speed_standard"]
        canceled = [u for u in all_users if (u.get("membership") or {}).get("status") == "canceled"]
        past_due = [u for u in all_users if (u.get("membership") or {}).get("status") == "past_due"]

        mrr_yen = len(light) * 4980 + len(standard) * 9800

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Active会員", f"{len(active_users)}名")
        c2.metric("├ Light", f"{len(light)}名", f"¥{len(light)*4980:,}")
        c3.metric("└ Standard", f"{len(standard)}名", f"¥{len(standard)*9800:,}")
        c4.metric("MRR（月次経常収益）", f"¥{mrr_yen:,}", "税別")
        c5.metric("解約/支払失敗", f"{len(canceled)+len(past_due)}名",
                  f"({len(past_due)} past_due)")

        st.divider()

        # ----- フィルター付き会員一覧 -----
        st.markdown("##### 👥 会員一覧")
        if not all_users:
            st.info("まだ会員はいません。Stripe決済が完了すると自動でここに表示されます。")
        else:
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                status_filter = st.multiselect(
                    "ステータス",
                    ["active", "trialing", "past_due", "canceled"],
                    default=["active", "trialing"],
                )
            with col_f2:
                plan_filter = st.multiselect(
                    "プラン",
                    ["speed_light", "speed_standard"],
                    default=["speed_light", "speed_standard"],
                )

            filtered = []
            for u in all_users:
                m = u.get("membership") or {}
                if m.get("status") not in status_filter:
                    continue
                if m.get("plan") not in plan_filter:
                    continue
                filtered.append({
                    "line_user_id": u["line_user_id"][:12] + "...",
                    "事業者名": u.get("display_name") or "—",
                    "プラン": "Light" if m.get("plan") == "speed_light" else "Standard",
                    "ステータス": m.get("status", "—"),
                    "課金期間終了": str(m.get("current_period_end") or "—")[:10],
                    "解約予定": "✓" if m.get("cancel_at_period_end") else "",
                    "登録日": str(m.get("registered_at") or "—")[:10],
                })

            if filtered:
                st.dataframe(pd.DataFrame(filtered), use_container_width=True, hide_index=True)
            else:
                st.caption("該当する会員がいません")

        st.divider()

        # ----- 個別会員詳細・操作 -----
        st.markdown("##### 🔍 個別会員 詳細・操作")
        if all_users:
            opts = {
                f"{(u.get('display_name') or u['line_user_id'][:8])} "
                f"({(u.get('membership') or {}).get('plan', '—')} / "
                f"{(u.get('membership') or {}).get('status', '—')})": u["line_user_id"]
                for u in all_users
            }
            selected_label = st.selectbox("会員を選択", list(opts.keys()), key="member_select")
            selected_uid = opts[selected_label]
            user = next(u for u in all_users if u["line_user_id"] == selected_uid)
            mem = user.get("membership") or {}

            d1, d2 = st.columns(2)
            with d1:
                st.markdown("**会員情報**")
                st.write(f"**LINE user ID**: `{selected_uid}`")
                st.write(f"**Display Name**: {user.get('display_name') or '—'}")
                st.write(f"**プラン**: {mem.get('plan', '—')}")
                st.write(f"**ステータス**: {mem.get('status', '—')}")
                st.write(f"**Stripe Customer**: `{mem.get('stripe_customer_id') or '—'}`")
                st.write(f"**Stripe Subscription**: `{mem.get('stripe_subscription_id') or '—'}`")

            with d2:
                st.markdown("**期間情報**")
                st.write(f"**登録日**: {str(mem.get('registered_at') or '—')[:19]}")
                st.write(f"**今期間 開始**: {str(mem.get('current_period_start') or '—')[:19]}")
                st.write(f"**今期間 終了**: {str(mem.get('current_period_end') or '—')[:19]}")
                st.write(f"**解約予定（期末）**: {'はい' if mem.get('cancel_at_period_end') else 'いいえ'}")
                st.write(f"**トライアル終了**: {str(mem.get('trial_end') or '—')[:19]}")
                st.write(f"**解約日**: {str(mem.get('canceled_at') or '—')[:19]}")

            st.markdown("**操作**")
            op1, op2, op3 = st.columns(3)
            with op1:
                if st.button("📨 月次配信テスト", key="test_dispatch", use_container_width=True):
                    try:
                        from app import monthly_dispatcher
                        plan = mem.get("plan", "speed_light")
                        result = monthly_dispatcher.dispatch_for_user(selected_uid, plan, user)
                        st.success(f"配信結果: {result}")
                    except Exception as e:
                        st.error(f"配信失敗: {type(e).__name__}: {e}")
            with op2:
                if st.button("🔁 Stripe同期", key="stripe_sync", use_container_width=True,
                             help="Stripe側のサブスク状態をFirestoreに再同期（実装は別途）"):
                    st.info("（Stripe同期はPhase 5の追加実装範囲。現状は手動更新のみ）")
            with op3:
                if st.button("🚪 解約処理（手動）", key="manual_cancel", use_container_width=True):
                    if mem.get("status") in ("active", "trialing", "past_due"):
                        from app import member as member_module
                        member_module.mark_canceled(selected_uid)
                        st.warning("Firestore上を解約に変更しました。Stripe側でも別途解約処理を実施してください。")
                    else:
                        st.info(f"既に {mem.get('status')} ステータスのため変更不要")

        st.divider()

        # ----- 月次配信履歴 -----
        st.markdown("##### 📜 月次配信履歴（直近30件）")
        try:
            from google.cloud import firestore as _fs
            deliveries = []
            for snap in db.collection("member_deliveries") \
                    .order_by("delivered_at", direction=_fs.Query.DESCENDING) \
                    .limit(30).stream():
                d = snap.to_dict()
                deliveries.append({
                    "配信日時": str(d.get("delivered_at") or "—")[:19],
                    "LINE user": (d.get("line_user_id") or "—")[:12] + "...",
                    "プラン": d.get("plan") or "—",
                    "コンテンツ": d.get("content_type") or "—",
                    "ステータス": d.get("delivery_status") or "—",
                })
            if deliveries:
                st.dataframe(pd.DataFrame(deliveries), use_container_width=True, hide_index=True)
            else:
                st.caption("配信履歴はまだありません")
        except Exception as e:
            st.warning(f"配信履歴取得失敗: {type(e).__name__}: {e}")

        st.divider()

        # ----- 一括月次配信トリガー（管理者用） -----
        st.markdown("##### 🚀 一括月次配信トリガー")
        st.caption(
            "全active会員に月次レポートを配信します。通常はCloud Schedulerが毎月15日に自動実行。"
            "これは手動実行ボタンです（緊急時のみ使用）"
        )
        confirm = st.checkbox("⚠️ 全会員への配信を承認します", key="dispatch_confirm")
        if st.button("📢 一括配信を実行", disabled=not confirm, use_container_width=True):
            try:
                from app import monthly_dispatcher
                with st.spinner("配信実行中..."):
                    stats = monthly_dispatcher.dispatch_all()
                st.success(f"配信完了: {stats}")
            except Exception as e:
                st.error(f"配信失敗: {type(e).__name__}: {e}")
