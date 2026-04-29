"""
ふるりーどSPEED Bot 会話シミュレーション（単体テスト）
実LINE接続なしで会話フロー・PDF生成を検証する。

実行:
    python3 test_flow.py
    python3 test_flow.py --detailed  # 詳細15問コース
"""
from __future__ import annotations
import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from app import storage, conversation, report_generator  # noqa


SIMPLE_ANSWERS = [
    "うなぎや茂右ヱ門",
    "福井県若狭町",
    "食品加工品・酒類",
    "三方湖の天然うなぎ・1日1組貸切宿泊。浜名湖産＋備長炭関西風",
    "test@example.com",
]

DETAILED_ANSWERS = [
    "うなぎや茂右ヱ門",                                       # D1
    "福井県若狭町",                                            # D2
    "食品加工・酒類",                                          # D3
    "https://unagiya-moemon.com/",                             # D4
    "浜名湖産うなぎ1尾350g・関西風・備長炭焼き・三方湖天然品", # D5
    "3,000〜10,000円",                                         # D6
    "300尾",                                                   # D7
    "冷凍",                                                    # D8
    "未掲載（これから）",                                      # D9
    "法人（株式会社等）",                                      # D10
    "1,000〜5,000万",                                          # D11
    "三方五湖湖畔で炭火の関西風うなぎ。1日1組のゲストハウスも併設", # D12
    "なし",                                                    # D13
    "未接触",                                                  # D14
    "test@example.com",                                        # D15
]


def run(course: str):
    uid = f"U_test_{course}_001"
    # 既存テストデータをクリア
    storage.init_db()

    print(f"\n{'=' * 60}")
    print(f"  ふるりーどSPEED テストフロー: {course.upper()}")
    print(f"{'=' * 60}\n")

    print("── [1] 友だち追加 ──")
    r = conversation.on_follow(uid, "テストユーザー")
    print(f"Bot: {r['text'][:100]}...\n")

    print("── [2] コース選択 ──")
    label = "簡易診断（5問・3分）" if course == "simple" else "詳細診断（15問・10分）"
    r = conversation.on_message(uid, label)
    print(f"User: {label}")
    print(f"Bot: {r['text'][:120]}\n")

    answers = SIMPLE_ANSWERS if course == "simple" else DETAILED_ANSWERS
    for i, ans in enumerate(answers, 1):
        r = conversation.on_message(uid, ans)
        print(f"── [Q{i}] User: {ans}")
        preview = r["text"].replace("\n", " | ")[:140]
        print(f"Bot: {preview}\n")

    user = storage.get_user(uid)
    print(f"Final status: {user['status']}  /  Completeness: {user['completeness']}%")

    print("\n── [PDF生成] ──")
    md, pdf = report_generator.generate_full_report(uid)
    print(f"MD:  {md}")
    print(f"PDF: {pdf}")
    print(f"PDF size: {os.path.getsize(pdf)} bytes")

    assert user["completeness"] == 100, "充足度が100%になっていません"
    assert os.path.exists(pdf), "PDFが生成されていません"
    print("\n✅ すべての検証項目PASS")


if __name__ == "__main__":
    course = "detailed" if "--detailed" in sys.argv else "simple"
    run(course)
