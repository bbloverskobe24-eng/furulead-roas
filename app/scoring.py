"""充足度計算ロジック"""
from __future__ import annotations
from typing import Set
from app.questions import get_questions


def calculate_completeness(course: str, answered_qids: Set[str]) -> int:
    """回答済みの質問IDセットから充足度（0-100）を計算"""
    total = 0
    for q in get_questions(course):
        if q["id"] in answered_qids:
            total += q["weight"]
    return min(total, 100)


def progress_bar(pct: int, length: int = 5) -> str:
    """進捗率に応じて色が変化する絵文字バー（赤→橙→黄→緑→青）"""
    filled = round(pct / 100 * length)
    if pct <= 20:
        filled_char = "🟥"  # 赤
    elif pct <= 40:
        filled_char = "🟧"  # 橙
    elif pct <= 60:
        filled_char = "🟨"  # 黄
    elif pct <= 80:
        filled_char = "🟩"  # 緑
    else:
        filled_char = "🟦"  # 青
    empty_char = "⬜"
    return filled_char * filled + empty_char * (length - filled)
