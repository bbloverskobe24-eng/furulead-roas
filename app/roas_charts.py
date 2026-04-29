"""ROAS分析レポート用チャート生成（うなぎや茂右ヱ門 generate_charts.py の汎用化版）

3種類のチャートを動的データから生成:
  - radar_fit.png        : 参入適性レーダーチャート（8軸）
  - revenue_forecast.png : 売上予測バーチャート（保守/中位/強気）
  - product_matrix.png   : 商品ラインナップマトリクス（希少性×寄付額）
"""
from __future__ import annotations
import os
from typing import Iterable
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager

for _cand in ["Hiragino Sans", "Hiragino Maru Gothic ProN", "Noto Sans CJK JP",
              "IPAexGothic", "YuGothic"]:
    if any(_cand in f.name for f in font_manager.fontManager.ttflist):
        matplotlib.rcParams["font.family"] = _cand
        break
matplotlib.rcParams["axes.unicode_minus"] = False

BRAND_DARK = "#1a5276"
BRAND_ACCENT = "#e67e22"
BRAND_GREEN = "#27ae60"
BRAND_RED = "#c0392b"
LIGHT = "#f4f6f7"
GREY = "#95a5a6"

DEFAULT_AXES = [
    "商品力",
    "ストーリー性",
    "価格帯適合",
    "供給能力",
    "自治体連携",
    "競合優位性",
    "オペ負荷の低さ",
    "地場産品要件適合度",
]


def _save(fig, out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def radar_fit(scores: dict, benchmark: dict, business_name: str, out_path: str,
              axes: Iterable[str] = DEFAULT_AXES) -> str:
    labels = list(axes)
    s = [float(scores.get(k, 0)) for k in labels]
    b = [float(benchmark.get(k, 0)) for k in labels]

    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    s_c = s + [s[0]]
    b_c = b + [b[0]]
    a_c = angles + [angles[0]]

    fig, ax = plt.subplots(figsize=(8, 7.5), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor("white")
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 10)
    ax.set_yticks([2, 4, 6, 8, 10])
    ax.set_yticklabels(["2", "4", "6", "8", "10"], fontsize=8, color="#999")
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=10)
    ax.tick_params(axis="x", pad=16)
    ax.grid(color="#ddd", linestyle="--", linewidth=0.8)
    for spine in ax.spines.values():
        spine.set_color("#ddd")

    ax.plot(a_c, b_c, color=GREY, linewidth=1.5, linestyle="--", label="業界ベンチマーク")
    ax.fill(a_c, b_c, color=GREY, alpha=0.08)
    ax.plot(a_c, s_c, color=BRAND_ACCENT, linewidth=2.5, label=business_name)
    ax.fill(a_c, s_c, color=BRAND_ACCENT, alpha=0.22)

    ax.set_title("ふるさと納税 参入適性スコア（10点満点）",
                 fontsize=14, color=BRAND_DARK, pad=28, weight="bold")
    ax.legend(loc="upper right", bbox_to_anchor=(1.28, 1.10), fontsize=9, frameon=False)

    return _save(fig, out_path)


def revenue_forecast(scenarios: dict, out_path: str) -> str:
    """
    scenarios = {
      "conservative": {"year1": 5000000, "year2": 12000000, "year3": 25000000},
      "moderate":     {...},
      "aggressive":   {...}
    }
    """
    years = ["1年目", "2年目", "3年目"]
    cons = [scenarios["conservative"][k] / 10000 for k in ("year1", "year2", "year3")]
    mod = [scenarios["moderate"][k] / 10000 for k in ("year1", "year2", "year3")]
    agg = [scenarios["aggressive"][k] / 10000 for k in ("year1", "year2", "year3")]

    x = np.arange(len(years))
    w = 0.27

    fig, ax = plt.subplots(figsize=(10, 5.4))
    fig.patch.set_facecolor("white")

    b1 = ax.bar(x - w, cons, w, label="保守シナリオ", color=BRAND_DARK)
    b2 = ax.bar(x, mod, w, label="中位シナリオ", color=BRAND_GREEN)
    b3 = ax.bar(x + w, agg, w, label="強気シナリオ", color=BRAND_ACCENT)

    for bars in (b1, b2, b3):
        for rect in bars:
            h = rect.get_height()
            if h > 0:
                ax.text(rect.get_x() + rect.get_width() / 2, h + max(agg) * 0.015,
                        f"{int(h):,}", ha="center", va="bottom",
                        fontsize=8.5, color="#333")

    ax.set_xticks(x)
    ax.set_xticklabels(years, fontsize=11)
    ax.set_ylabel("年間寄付額（万円）", fontsize=10.5, color="#333")
    ax.set_title("売上見込み（3シナリオ・3年推移）",
                 fontsize=13.5, color=BRAND_DARK, weight="bold", pad=12)
    ax.set_ylim(0, max(agg) * 1.22 if agg and max(agg) > 0 else 100)
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle="--", linewidth=0.5, color="#ddd")
    ax.set_axisbelow(True)

    return _save(fig, out_path)


def product_matrix(items: list, out_path: str) -> str:
    """
    items = [{"name": "U-1 蒲焼1尾", "rarity_score": 4, "donation_price": 18000, "category": "メイン"}]
    donation_price は円。グラフでは万円換算。
    """
    if not items:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, "商品データなし", ha="center", va="center")
        ax.axis("off")
        return _save(fig, out_path)

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("white")

    cats = list({it.get("category", "メイン") for it in items})
    palette = [BRAND_DARK, BRAND_ACCENT, BRAND_GREEN, BRAND_RED, "#8e44ad"]
    cat_color = {c: palette[i % len(palette)] for i, c in enumerate(cats)}

    max_p = 1.0
    for it in items:
        r = float(it.get("rarity_score", 5))
        p = float(it.get("donation_price", 0)) / 10000  # 万円
        c = cat_color.get(it.get("category", "メイン"), BRAND_DARK)
        max_p = max(max_p, p)
        ax.scatter(r, p, s=350, color=c, alpha=0.82,
                   edgecolors="white", linewidths=2, zorder=3)
        ax.annotate(it.get("name", "—"), (r, p),
                    xytext=(r + 0.18, p + max_p * 0.04),
                    fontsize=9.2, color="#222")

    ax.set_xlim(0, 11)
    ax.set_ylim(0, max_p * 1.25)
    ax.set_xlabel("希少性スコア（0–10）", fontsize=10.5, color="#333")
    ax.set_ylabel("想定寄付額（万円）", fontsize=10.5, color="#333")
    ax.set_title("商品ラインナップ提案（希少性 × 寄付額）",
                 fontsize=13.5, color=BRAND_DARK, weight="bold", pad=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(linestyle="--", linewidth=0.5, color="#ddd")
    ax.set_axisbelow(True)

    handles = [plt.Line2D([0], [0], marker="o", color="w",
                          markerfacecolor=cat_color[c], markersize=10, label=c)
               for c in cats]
    ax.legend(handles=handles, loc="upper left", frameon=False, fontsize=9.5)

    return _save(fig, out_path)


def generate_all(analysis: dict, business_name: str, out_dir: str) -> dict:
    """analysis JSONから3種チャートを生成し、ファイルパスのdictを返す"""
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    fit = analysis.get("fit_score", {})
    paths["radar"] = radar_fit(
        fit.get("scores", {}),
        fit.get("benchmark", {}),
        business_name,
        os.path.join(out_dir, "radar_fit.png"),
    )
    paths["revenue"] = revenue_forecast(
        analysis.get("revenue_forecast", {}),
        os.path.join(out_dir, "revenue_forecast.png"),
    )
    paths["matrix"] = product_matrix(
        analysis.get("product_recommendations", []),
        os.path.join(out_dir, "product_matrix.png"),
    )
    return paths
