"""Kirish nuqtasi: python -m bot"""
from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

from . import handlers as h
from .config import load_settings
from .db import Database
from .delivery import DeliveryService
from .services import AppContext
from .tts import AudioService
from .words import WordService

log = logging.getLogger("bot")

COMMANDS = [
    BotCommand("soz", "Bugungi so'zlar"),
    BotCommand("test", "Takrorlash testi"),
    BotCommand("statistika", "Natijalarim"),
    BotCommand("sozlamalar", "Sozlamalar menyusi"),
    BotCommand("vaqt", "Yuborish vaqti (masalan: /vaqt 20:00)"),
    BotCommand("soni", "Kuniga so'zlar soni"),
    BotCommand("daraja", "Daraja: A1, A2, B1"),
    BotCommand("stop", "Kunlik xabarlarni to'xtatish"),
    BotCommand("help", "Yordam"),
]


def setup_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", level=logging.INFO
    )
    # httpx so'rov URL'larini (ichida bot tokeni bor) INFO darajasida yozadi
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def post_init(app: Application) -> None:
    settings = app.bot_data["settings"]
    db = Database(settings.db_path)
    await db.connect()
    words = WordService(db, settings)
    await words.sync_seed()
    app.bot_data["ctx"] = AppContext(
        settings=settings,
        db=db,
        words=words,
        audio=AudioService(db, settings.audio_dir),
        delivery=DeliveryService(settings, db, words),
    )
    await app.bot.set_my_commands(COMMANDS)
    log.info("Bot ishga tushdi: @%s", app.bot.username)


async def post_shutdown(app: Application) -> None:
    ctx = app.bot_data.get("ctx")
    if ctx:
        await ctx.db.close()


async def scheduler_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.application.bot_data["ctx"].delivery.run_scheduled(context.bot)


def main() -> None:
    setup_logging()
    settings = load_settings()

    app = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["settings"] = settings

    private = filters.ChatType.PRIVATE
    for names, callback in [
        (["start"], h.cmd_start),
        (["help"], h.cmd_help),
        (["soz", "bugun"], h.cmd_today),
        (["test"], h.cmd_test),
        (["statistika"], h.cmd_stats),
        (["sozlamalar"], h.cmd_settings),
        (["vaqt"], h.cmd_time),
        (["soni"], h.cmd_count),
        (["daraja"], h.cmd_level),
        (["stop"], h.cmd_stop),
        (["admin"], h.cmd_admin),
    ]:
        app.add_handler(CommandHandler(names, callback, filters=private))

    app.add_handler(CallbackQueryHandler(h.cb_audio, pattern=r"^au:\d+$"))
    app.add_handler(CallbackQueryHandler(h.cb_known, pattern=r"^kn:\d+$"))
    app.add_handler(CallbackQueryHandler(h.cb_repeat, pattern=r"^rp:\d+$"))
    app.add_handler(CallbackQueryHandler(h.cb_quiz_start, pattern=r"^qs$"))
    app.add_handler(CallbackQueryHandler(h.cb_quiz_answer, pattern=r"^qa:\d+:\d+:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(h.cb_settings, pattern=r"^st:(lvl|cnt):\w+$"))
    app.add_error_handler(h.on_error)

    if app.job_queue is None:
        raise RuntimeError('JobQueue yo\'q: pip install "python-telegram-bot[job-queue]"')
    app.job_queue.run_repeating(scheduler_tick, interval=60, first=10, name="daily-delivery")

    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
