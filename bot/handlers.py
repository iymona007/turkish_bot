"""Telegram buyruqlari va tugma (callback) handlerlari."""
from __future__ import annotations

import html
import logging
import random
import re
import traceback
from datetime import timedelta

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError
from telegram.ext import ContextTypes

from . import formatting as fmt
from . import srs
from .config import LEVELS, MAX_WORDS_PER_DAY
from .services import AppContext

log = logging.getLogger(__name__)

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
HTML = ParseMode.HTML


def _ctx(context: ContextTypes.DEFAULT_TYPE) -> AppContext:
    return context.application.bot_data["ctx"]


async def _ensure_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = _ctx(context)
    tg_user, chat = update.effective_user, update.effective_chat
    return await c.db.register_user(
        chat.id,
        tg_user.username,
        tg_user.first_name,
        c.settings.default_send_time,
        c.settings.default_words_per_day,
    )


# ---- asosiy buyruqlar ---------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = _ctx(context)
    user = await _ensure_user(update, context)
    await c.db.set_user_field(user["chat_id"], active=1)
    await update.message.reply_html(fmt.welcome(update.effective_user.first_name, user))
    await c.delivery.deliver(context.bot, user["chat_id"])


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update, context)
    await update.message.reply_html(fmt.HELP)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _ensure_user(update, context)
    await _ctx(context).delivery.deliver(context.bot, user["chat_id"])


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _ensure_user(update, context)
    await _ctx(context).db.set_user_field(user["chat_id"], active=0)
    await update.message.reply_text("⏸ Kunlik xabarlar to'xtatildi. Qayta yoqish uchun /start yuboring.")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = _ctx(context)
    user = await _ensure_user(update, context)
    stats = await c.db.user_stats(user["chat_id"], c.today().isoformat())
    await update.message.reply_html(fmt.stats_text(stats))


# ---- sozlamalar ---------------------------------------------------------
async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _ensure_user(update, context)
    await update.message.reply_html(fmt.settings_text(user), reply_markup=fmt.settings_keyboard(user))


async def cmd_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _ensure_user(update, context)
    match = TIME_RE.match(context.args[0]) if context.args else None
    if not match:
        await update.message.reply_html("Vaqtni shunday yozing: /vaqt <code>20:00</code> (SS:DD)")
        return
    hhmm = f"{int(match[1]):02d}:{match[2]}"
    await _ctx(context).db.set_user_field(user["chat_id"], send_time=hhmm)
    await update.message.reply_text(f"✅ So'zlar endi har kuni soat {hhmm} da yuboriladi.")


async def cmd_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _ensure_user(update, context)
    arg = context.args[0] if context.args else ""
    if not arg.isdigit() or not 1 <= int(arg) <= MAX_WORDS_PER_DAY:
        await update.message.reply_html(f"Shunday yozing: /soni <code>10</code> (1 dan {MAX_WORDS_PER_DAY} gacha)")
        return
    await _ctx(context).db.set_user_field(user["chat_id"], words_per_day=int(arg))
    await update.message.reply_text(f"✅ Kuniga {int(arg)} tadan so'z beriladi (keyingi to'plamdan boshlab).")


async def cmd_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _ensure_user(update, context)
    arg = context.args[0].upper() if context.args else ""
    if arg not in LEVELS:
        await update.message.reply_html(f"Shunday yozing: /daraja <code>A2</code> ({', '.join(LEVELS)})")
        return
    await _ctx(context).db.set_user_field(user["chat_id"], level=arg)
    await update.message.reply_text(f"✅ Daraja: {arg} (keyingi to'plamdan boshlab).")


async def cb_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = _ctx(context)
    query = update.callback_query
    user = await _ensure_user(update, context)
    _, kind, value = query.data.split(":")

    if kind == "lvl" and value in LEVELS:
        await c.db.set_user_field(user["chat_id"], level=value)
    elif kind == "cnt" and value.isdigit() and 1 <= int(value) <= MAX_WORDS_PER_DAY:
        await c.db.set_user_field(user["chat_id"], words_per_day=int(value))
    else:
        await query.answer()
        return

    user = await c.db.get_user(user["chat_id"])
    await query.answer("Saqlandi ✅")
    try:
        await query.edit_message_text(
            fmt.settings_text(user), parse_mode=HTML, reply_markup=fmt.settings_keyboard(user)
        )
    except BadRequest:  # xabar o'zgarmagan bo'lsa
        pass


# ---- so'z tugmalari -----------------------------------------------------
async def cb_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = _ctx(context)
    query = update.callback_query
    word = await c.db.get_word(int(query.data.split(":")[1]))
    if word is None:
        await query.answer("So'z topilmadi", show_alert=True)
        return
    await query.answer("🔊 Audio tayyorlanmoqda…")
    try:
        await c.audio.send_word_audio(context.bot, query.message.chat.id, word)
    except Exception:
        log.exception("Audio yuborib bo'lmadi (so'z %s)", word["id"])
        await context.bot.send_message(
            query.message.chat.id, "Audio yaratib bo'lmadi, keyinroq urinib ko'ring."
        )


async def cb_known(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _ctx(context).db.mark_known(query.message.chat.id, int(query.data.split(":")[1]))
    await query.answer("✅ Ajoyib! Bu so'z endi takrorlanmaydi.")


async def cb_repeat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = _ctx(context)
    query = update.callback_query
    tomorrow = (c.today() + timedelta(days=1)).isoformat()
    await c.db.mark_repeat(query.message.chat.id, int(query.data.split(":")[1]), tomorrow)
    await query.answer("🔁 Ertaga qayta so'rayman.")


# ---- test ---------------------------------------------------------------
async def _send_question(bot, c: AppContext, chat_id: int, n: int, score: int) -> bool:
    word = await c.db.next_due_word(chat_id, c.today().isoformat())
    if word is None:
        return False
    wrong = await c.db.distractors(word["id"], word["uz"], 3)
    options = [(word["id"], word["uz"])] + [(row["id"], row["uz"]) for row in wrong]
    random.shuffle(options)
    await bot.send_message(
        chat_id,
        fmt.question_text(word, n, c.settings.quiz_length),
        parse_mode=HTML,
        reply_markup=fmt.question_keyboard(word["id"], options, n, score),
    )
    return True


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _ensure_user(update, context)
    if not await _send_question(context.bot, _ctx(context), user["chat_id"], 1, 0):
        await update.message.reply_text(
            "Bugun takrorlash uchun so'z yo'q 🎉 Yangi so'zlar uchun /soz ni yuboring."
        )


async def cb_quiz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await _send_question(context.bot, _ctx(context), query.message.chat.id, 1, 0):
        await query.answer()
    else:
        await query.answer("Bugun takrorlash uchun so'z yo'q 🎉", show_alert=True)


async def cb_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = _ctx(context)
    query = update.callback_query
    chat_id = query.message.chat.id
    try:
        _, word_id, choice_id, n, score = (int(x) if x.isdigit() else x for x in query.data.split(":"))
    except ValueError:
        await query.answer()
        return

    today = c.today()
    progress = await c.db.get_progress(chat_id, word_id)
    stale = (
        progress is None
        or progress["status"] != "learning"
        or not progress["next_review"]
        or progress["next_review"] > today.isoformat()
    )
    if stale:  # savolga allaqachon javob berilgan
        await query.answer("Bu savolga allaqachon javob berilgan.")
        return

    word = await c.db.get_word(word_id)
    correct = choice_id == word_id
    review = srs.after_answer(progress["box"], correct, today)
    await c.db.update_progress(chat_id, word_id, review.status, review.box, review.next_review, correct)

    await query.answer("✅ To'g'ri!" if correct else "❌ Noto'g'ri")
    await query.edit_message_text(fmt.answer_text(word, correct, review, today, n), parse_mode=HTML)

    score += int(correct)
    if n < c.settings.quiz_length and await _send_question(context.bot, c, chat_id, n + 1, score):
        return
    await context.bot.send_message(chat_id, fmt.quiz_summary(score, n), parse_mode=HTML)


# ---- admin va xatolar ---------------------------------------------------
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = _ctx(context)
    if c.settings.admin_id is None or update.effective_user.id != c.settings.admin_id:
        return
    stats = await c.db.global_stats()
    await update.message.reply_html(
        "🛠 <b>Admin</b>\n\n"
        f"Foydalanuvchilar: <b>{stats['users']}</b> (faol: {stats['active']})\n"
        f"Bazadagi so'zlar: <b>{stats['words']}</b>"
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    log.error("Handlerda xato", exc_info=error)
    if isinstance(error, NetworkError):  # vaqtinchalik tarmoq xatolari — adminni bezovta qilmaymiz
        return
    c = context.application.bot_data.get("ctx")
    if c and c.settings.admin_id:
        tb = "".join(traceback.format_exception(None, error, error.__traceback__))[-1500:]
        try:
            await context.bot.send_message(
                c.settings.admin_id, f"⚠️ <b>Xato</b>\n<pre>{html.escape(tb)}</pre>", parse_mode=HTML
            )
        except Exception:
            log.exception("Adminga xabar yuborib bo'lmadi")
