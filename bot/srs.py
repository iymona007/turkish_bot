"""Oraliqli takrorlash (Leitner tizimi).

Yangi so'z 0-qutiga tushadi va 1 kundan keyin birinchi marta so'raladi.
To'g'ri javob so'zni keyingi qutiga o'tkazadi (oraliq kengayadi),
noto'g'ri javob esa 0-qutiga qaytaradi. Oxirgi qutidan o'tgan so'z
"o'zlashtirilgan" (known) deb belgilanadi.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

INTERVALS = (1, 3, 7, 14, 30, 60)  # kunlarda


@dataclass(frozen=True)
class Review:
    status: str               # "learning" yoki "known"
    box: int
    next_review: str | None   # ISO sana, known bo'lsa None


def first_review(today: date) -> date:
    return today + timedelta(days=INTERVALS[0])


def after_answer(box: int, correct: bool, today: date) -> Review:
    if not correct:
        return Review("learning", 0, (today + timedelta(days=INTERVALS[0])).isoformat())
    new_box = box + 1
    if new_box >= len(INTERVALS):
        return Review("known", len(INTERVALS) - 1, None)
    return Review("learning", new_box, (today + timedelta(days=INTERVALS[new_box])).isoformat())
