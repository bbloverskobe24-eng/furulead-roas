"""ROAS分析タブ — Streamlit管理画面に組み込むビュー"""
from __future__ import annotations
import json
import os

import streamlit as st

from app import roas_report


def _default_form_state():
    return {
        "business_name": "",
        "representative": "",
        "prefecture": "千葉県",
        "city": "",
        "business_type": "食品",
        "website_url": "",
        "years_in_business": 10,
        "main_products": [
            {"name": "", "retail_price": 5000, "monthly_supply": 200, "unique_point": ""},
        ],
        "furusato_status": "未掲載",
        "current_donation_amount": 0,
        "target_municipality": "",
        "municipality_relation": "相談中",
        "annual_revenue_range": "1000-5000万",
        "employees": 10,
        "unique_story": "",
        "awards": "",
        "media_coverage": "",
        "marketing_budget_monthly": 300000,
        "contact_email": "",
        "contact_phone": "",
    }


def render():
    st.subheader("🎯 ROAS分析レポート生成")
    st.caption(
        "事業者情報を入力 → AIが分析 → ROAS試算・推奨プラン入りPDFレポートを生成"
    )

    if "roas_form" not in st.session_state:
        st.session_state["roas_form"] = _default_form_state()

    form = st.session_state["roas_form"]

    with st.expander("💾 サンプル：うなぎや茂右ヱ門で埋める", expanded=False):
        if st.button("サンプル投入", use_container_width=True, key="roas_sample_btn"):
            st.session_state["roas_form"] = {
                "business_name": "うなぎや茂右ヱ門",
                "representative": "佐藤茂右ヱ門",
                "prefecture": "福井県",
                "city": "若狭町",
                "business_type": "食品",
                "website_url": "https://example.com",
                "years_in_business": 28,
                "main_products": [
                    {"name": "国産うなぎ蒲焼1尾", "retail_price": 5500,
                     "monthly_supply": 300, "unique_point": "三方湖天然うなぎ"},
                    {"name": "蒲焼2尾セット", "retail_price": 10000,
                     "monthly_supply": 200, "unique_point": "贈答用"},
                    {"name": "宿泊会席プラン", "retail_price": 35000,
                     "monthly_supply": 50, "unique_point": "うなぎ会席＋温泉"},
                ],
                "furusato_status": "検討中",
                "current_donation_amount": 0,
                "target_municipality": "若狭町",
                "municipality_relation": "連携あり",
                "annual_revenue_range": "1-5億",
                "employees": 18,
                "unique_story": "創業江戸時代、三方湖天然うなぎ、宿泊と一体化した体験提供",
                "awards": "福井県知事賞",
                "media_coverage": "日経MJ、NHKふるさと特集",
                "marketing_budget_monthly": 500000,
                "contact_email": "info@example.com",
                "contact_phone": "0770-XX-XXXX",
            }
            st.rerun()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### 事業者基本情報")
        form["business_name"] = st.text_input("事業者名", form["business_name"])
        form["representative"] = st.text_input("代表者名", form["representative"])
        form["prefecture"] = st.text_input("都道府県", form["prefecture"])
        form["city"] = st.text_input("市区町村", form["city"])
        form["business_type"] = st.selectbox(
            "業種", ["食品", "工芸", "宿泊・体験", "その他"],
            index=["食品", "工芸", "宿泊・体験", "その他"].index(form["business_type"])
        )
        form["website_url"] = st.text_input("Webサイト（任意）", form["website_url"])
        form["years_in_business"] = st.number_input(
            "創業年数", min_value=0, max_value=200,
            value=int(form["years_in_business"])
        )

    with col2:
        st.markdown("##### 事業規模・現状")
        form["annual_revenue_range"] = st.selectbox(
            "年商レンジ",
            ["1000万未満", "1000-5000万", "5000万-1億", "1-5億", "5億以上"],
            index=["1000万未満", "1000-5000万", "5000万-1億", "1-5億", "5億以上"]
                .index(form["annual_revenue_range"])
        )
        form["employees"] = st.number_input(
            "従業員数", min_value=0, max_value=10000, value=int(form["employees"])
        )
        form["furusato_status"] = st.selectbox(
            "ふるさと納税ステータス",
            ["未掲載", "掲載中", "検討中"],
            index=["未掲載", "掲載中", "検討中"].index(form["furusato_status"])
        )
        form["current_donation_amount"] = st.number_input(
            "現在の年間寄付額（円）", min_value=0, value=int(form["current_donation_amount"]),
            step=1000000
        )
        form["target_municipality"] = st.text_input("想定自治体", form["target_municipality"])
        form["municipality_relation"] = st.selectbox(
            "自治体との関係", ["連携あり", "相談中", "なし"],
            index=["連携あり", "相談中", "なし"].index(form["municipality_relation"])
        )

    st.markdown("##### 商品情報")
    products = form.get("main_products", [])
    n_products = st.number_input(
        "商品数", min_value=1, max_value=10, value=max(1, len(products))
    )
    while len(products) < n_products:
        products.append({"name": "", "retail_price": 5000,
                         "monthly_supply": 200, "unique_point": ""})
    products = products[:n_products]

    for idx, p in enumerate(products):
        with st.expander(f"商品 {idx + 1}: {p.get('name') or '(未入力)'}", expanded=idx == 0):
            c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
            with c1:
                p["name"] = st.text_input("商品名", p.get("name", ""), key=f"pname_{idx}")
            with c2:
                p["retail_price"] = st.number_input(
                    "小売価格（円）", min_value=0, value=int(p.get("retail_price", 0)),
                    step=500, key=f"price_{idx}"
                )
            with c3:
                p["monthly_supply"] = st.number_input(
                    "月間供給可能量", min_value=0, value=int(p.get("monthly_supply", 0)),
                    step=10, key=f"sup_{idx}"
                )
            with c4:
                p["unique_point"] = st.text_input(
                    "差別化ポイント", p.get("unique_point", ""), key=f"upoint_{idx}"
                )
    form["main_products"] = products

    st.markdown("##### 差別化要素・広告予算")
    col3, col4 = st.columns(2)
    with col3:
        form["unique_story"] = st.text_area("ストーリー・強み", form["unique_story"], height=80)
        form["awards"] = st.text_input("受賞歴（任意）", form["awards"])
        form["media_coverage"] = st.text_input("メディア掲載（任意）", form["media_coverage"])
    with col4:
        form["marketing_budget_monthly"] = st.number_input(
            "月間広告予算（円）", min_value=0,
            value=int(form["marketing_budget_monthly"]), step=50000
        )
        form["contact_email"] = st.text_input("連絡先メール", form["contact_email"])
        form["contact_phone"] = st.text_input("連絡先電話", form["contact_phone"])

    st.divider()

    if st.button("🚀 AI分析を実行", type="primary", use_container_width=True):
        if not form["business_name"]:
            st.error("事業者名を入力してください")
            return
        try:
            with st.spinner("AI分析中... (30〜60秒程度)"):
                md_path, pdf_path, analysis, usage = roas_report.generate(form, mode="internal")
            st.success("分析完了。下記から用途別のPDFをダウンロードできます。")
            st.session_state["roas_form_snapshot"] = dict(form)
            st.session_state["roas_last_analysis"] = analysis
            st.session_state["roas_last_usage"] = usage
            st.session_state["roas_pdfs"] = {"internal": (md_path, pdf_path)}
        except Exception as e:
            st.error(f"分析失敗: {e}")
            st.exception(e)

    if "roas_last_analysis" in st.session_state:
        st.divider()
        st.markdown("##### 分析結果")

        usage = st.session_state.get("roas_last_usage") or {}
        if usage:
            u1, u2, u3, u4 = st.columns(4)
            with u1:
                st.metric("入力トークン", f"{usage.get('input_tokens', 0):,}")
            with u2:
                st.metric("出力トークン", f"{usage.get('output_tokens', 0):,}")
            with u3:
                st.metric("コスト (USD)", f"${usage.get('cost_usd', 0):.4f}")
            with u4:
                st.metric("コスト (JPY)", f"¥{usage.get('cost_jpy', 0):.2f}")
            st.caption(
                f"使用モデル: `{usage.get('model', '—')}` / "
                f"単価: 入力 ${usage.get('input_price_usd_per_mtok', 0):.2f} / 出力 ${usage.get('output_price_usd_per_mtok', 0):.2f} per 1M tok / "
                f"換算レート 1 USD = {usage.get('fx_rate', 0):.1f} 円"
            )

        st.markdown("##### 📄 PDF出力（用途別）")
        st.caption(
            "**興味付け版**: 初回提供用（コスト・プラン詳細・ROAS試算なし） / "
            "**一次営業版**: 商談用（ROAS・プラン別の手元残金あり） / "
            "**社内全項目版**: 内部資料用"
        )

        modes = [
            ("lead", "🎯 興味付け版", "事業者初回提供用（軽め）"),
            ("sales", "💼 一次営業版", "商談時に渡す詳細版"),
            ("internal", "📊 社内全項目版", "内部資料・分析根拠付き"),
        ]

        cols = st.columns(3)
        pdfs = st.session_state.setdefault("roas_pdfs", {})
        snapshot = st.session_state.get("roas_form_snapshot", form)
        analysis = st.session_state["roas_last_analysis"]

        for col, (mode, label, caption) in zip(cols, modes):
            with col:
                st.markdown(f"**{label}**")
                st.caption(caption)
                if mode not in pdfs:
                    if st.button(f"生成", key=f"gen_{mode}", use_container_width=True):
                        try:
                            with st.spinner("PDF生成中..."):
                                md_p, pdf_p = roas_report.generate_with_existing_analysis(
                                    snapshot, analysis, usage, mode
                                )
                            pdfs[mode] = (md_p, pdf_p)
                            st.rerun()
                        except Exception as e:
                            st.error(f"生成失敗: {e}")
                            st.exception(e)
                else:
                    md_p, pdf_p = pdfs[mode]
                    with open(pdf_p, "rb") as f:
                        st.download_button(
                            "⬇️ PDF",
                            f.read(),
                            file_name=os.path.basename(pdf_p),
                            mime="application/pdf",
                            use_container_width=True,
                            key=f"dl_pdf_{mode}",
                        )
                    with open(md_p, encoding="utf-8") as f:
                        st.download_button(
                            "📝 MD",
                            f.read(),
                            file_name=os.path.basename(md_p),
                            mime="text/markdown",
                            use_container_width=True,
                            key=f"dl_md_{mode}",
                        )

        with st.expander("🔍 AI分析JSON（デバッグ用）"):
            st.json(analysis)
