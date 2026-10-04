"""Xabar matnlari va tugmalar (Telegram HTML formatida)."""
from __future__ import annotations

from datetime import date
from html import escape as e

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .config import LEVELS, MAX_WORDS_PER_DAY
from .srs import Review

HELP = (
    "<b>Buyruqlar</b>\n"
    "/soz — bugungi so'zlar\n"
    "/test — takrorlash testi\n"
    "/statistika — natijalaringiz\n"
    "/sozlamalar — sozlamalar menyusi\n"
    "/vaqt <code>20:00</code> — kunlik yuborish vaqti\n"
    f"/soni <code>10</code> — kuniga nechta so'z (1–{MAX_WORDS_PER_DAY})\n"
    "/daraja <code>A2</code> — daraja (A1, A2, B1)\n"
    "/stop — kunlik xabarlarni to'xtatish"
)


def welcome(first_name: str | None, user) -> str:
    name = e(first_name or "do'st")
    return (
        f"Salom, {name}! 👋\n\n"
        f"Men har kuni soat <b>{user['send_time']}</b> da <b>{user['words_per_day']}</b> ta "
        f"turkcha so'z yuboraman: tarjimasi, misol gapi va talaffuzi bilan. "
        f"Keyingi kunlarda ularni qisqa test bilan takrorlatib turaman.\n\n"
        f"{HELP}"
    )


def words_message(words) -> str:
    lines = ["🇹🇷 <b>Bugungi so'zlar</b>", ""]
    for i, w in enumerate(words, 1):
        lines.append(f"{i}. <b>{e(w['tr'])}</b> — {e(w['uz'])}")
        if w["example_tr"]:
            lines.append(f"    <i>{e(w['example_tr'])}</i>")
            if w["example_uz"]:
                lines.append(f"    <tg-spoiler>{e(w['example_uz'])}</tg-spoiler>")
        lines.append("")
    lines.append("🔊 talaffuz · ✅ bilaman (takrorlanmaydi) · 🔁 takrorlayman")
    return "\n".join(lines)


def words_keyboard(words) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(f"🔊 {w['tr'][:20]}", callback_data=f"au:{w['id']}"),
            InlineKeyboardButton("✅", callback_data=f"kn:{w['id']}"),
            InlineKeyboardButton("🔁", callback_data=f"rp:{w['id']}"),
        ]
        for w in words
    ]
    return InlineKeyboardMarkup(rows)


def review_prompt_text(due: int) -> str:
    return f"🧠 Takrorlash vaqti! <b>{due}</b> ta so'zni eslab ko'rasizmi?"


def review_keyboard(due: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"🧠 Testni boshlash ({due})", callback_data="qs")]]
    )


# ---- test ---------------------------------------------------------------
def question_text(word, n: int, total: int) -> str:
    return f"🧠 <b>Savol {n}/{total}</b>\n\n«<b>{e(word['tr'])}</b>» nima degani?"


def question_keyboard(word_id: int, options: list[tuple[int, str]], n: int, score: int):
    buttons = [
        InlineKeyboardButton(uz[:30], callback_data=f"qa:{word_id}:{option_id}:{n}:{score}")
        for option_id, uz in options
    ]
    return InlineKeyboardMarkup([buttons[i : i + 2] for i in range(0, len(buttons), 2)])


def answer_text(word, correct: bool, review: Review, today: date, n: int) -> str:
    head = "✅ <b>To'g'ri!</b>" if correct else "❌ <b>Noto'g'ri.</b>"
    lines = [f"{head}  <i>(savol {n})</i>", f"<b>{e(word['tr'])}</b> — {e(word['uz'])}"]
    if word["example_tr"]:
        lines.append(f"<i>{e(word['example_tr'])}</i>")
    if review.status == "known":
        lines.append("\n🎓 Bu so'zni to'liq o'zlashtirdingiz!")
    elif review.next_review:
        days = (date.fromisoformat(review.next_review) - today).days
        lines.append(f"\n⏰ Keyingi takrorlash: {days} kundan keyin")
    return "\n".join(lines)


def quiz_summary(score: int, total: int) -> str:
    percent = round(100 * score / total) if total else 0
    return f"🏁 <b>Test tugadi!</b>\nNatija: <b>{score}/{total}</b> ({percent}%)"


# ---- sozlamalar va statistika --------------------------------------------
def settings_text(user) -> str:
    state = "yoqilgan ✅" if user["active"] else "o'chirilgan ⏸ (/start bilan yoqing)"
    return (
        "⚙️ <b>Sozlamalar</b>\n\n"
        f"Daraja: <b>{user['level']}</b>\n"
        f"Kuniga so'zlar: <b>{user['words_per_day']}</b>\n"
        f"Yuborish vaqti: <b>{user['send_time']}</b>\n"
        f"Kunlik xabarlar: {state}\n\n"
        "Vaqtni o'zgartirish: /vaqt <code>20:00</code>\n"
        "<i>Yangi daraja va son keyingi yangi so'zlar to'plamidan boshlab amal qiladi.</i>"
    )


def settings_keyboard(user) -> InlineKeyboardMarkup:
    levels = [
        InlineKeyboardButton(("✓ " if user["level"] == lvl else "") + lvl, callback_data=f"st:lvl:{lvl}")
        for lvl in LEVELS
    ]
    counts = [
        InlineKeyboardButton(
            ("✓ " if user["words_per_day"] == n else "") + str(n), callback_data=f"st:cnt:{n}"
        )
        for n in (3, 5, 10, 15)
    ]
    return InlineKeyboardMarkup([levels, counts])


def stats_text(stats: dict) -> str:
    answered = stats["correct"] + stats["wrong"]
    accuracy = f"{round(100 * stats['correct'] / answered)}%" if answered else "—"
    return (
        "📊 <b>Statistika</b>\n\n"
        f"Jami berilgan so'zlar: <b>{stats['total']}</b>\n"
        f"O'rganilmoqda: <b>{stats['learning']}</b>\n"
        f"O'zlashtirilgan: <b>{stats['known']}</b>\n"
        f"Bugun takrorlash kerak: <b>{stats['due']}</b>\n"
        f"Test aniqligi: <b>{accuracy}</b> ({stats['correct']}/{answered})"
    )
