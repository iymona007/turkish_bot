"""Kunlik so'zlarni yuborish va rejalashtirilgan yuborish (scheduler)."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter

from . import formatting as fmt
from . import srs
from .config import Settings
from .db import Database
from .words import WordService

log = logging.getLogger(__name__)

RETRY_COOLDOWN = 15 * 60


class DeliveryService:
    def __init__(self, settings: Settings, db: Database, words: WordService):
        self._s = settings
        self._db = db
        self._words = words
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._cooldown: dict[int, float] = {}

    async def deliver(
        self,
        bot: Bot,
        chat_id: int,
        *,
        scheduled: bool = False,
    ) -> bool:
        """Bugungi so'zlarni yuboradi."""

        async with self._locks[chat_id]:
            user = await self._db.get_user(chat_id)

            if user is None:
                return False

            today = datetime.now(self._s.tz).date()
            today_iso = today.isoformat()

            words = await self._db.todays_words(
                chat_id,
                today_iso,
            )

            if not words:
                fresh = await self._words.pick_new(user)

                if fresh:
                    await self._db.introduce(
                        chat_id,
                        [w["id"] for w in fresh],
                        today_iso,
                        srs.first_review(today).isoformat(),
                    )

                    words = await self._db.todays_words(
                        chat_id,
                        today_iso,
                    )

            if not words:
                if not scheduled:
                    await bot.send_message(
                        chat_id,
                        "Hozircha yangi so'z topilmadi. "
                        "Birozdan keyin /soz ni qayta yuboring.",
                    )

                return False

            # Bugungi so'zlarni yuborish
            await bot.send_message(
                chat_id,
                fmt.words_message(words),
                parse_mode=ParseMode.HTML,
                reply_markup=fmt.words_keyboard(words),
            )

            # Qayta yuborilmasligi uchun belgilanadi
            await self._db.set_user_field(
                chat_id,
                last_sent_date=today_iso,
            )

            # Takrorlash kerak bo'lgan so'zlar
            due = await self._db.count_due(
                chat_id,
                today_iso,
            )

            if due:
                await bot.send_message(
                    chat_id,
                    fmt.review_prompt_text(due),
                    parse_mode=ParseMode.HTML,
                    reply_markup=fmt.review_keyboard(due),
                )

            return True

    async def run_scheduled(self, bot: Bot) -> None:
        """Har daqiqada chaqiriladi."""

        now = datetime.now(self._s.tz)

        users = await self._db.users_due_for_delivery(
            now.date().isoformat(),
            now.strftime("%H:%M"),
        )

        for user in users:
            chat_id = user["chat_id"]

            # Yaqinda xato bo'lgan bo'lsa, qayta urinmaymiz
            if self._cooldown.get(
                chat_id,
                0,
            ) > time.monotonic():
                continue

            try:
                success = await self.deliver(
                    bot,
                    chat_id,
                    scheduled=True,
                )

                if not success:
                    self._cooldown[chat_id] = (
                        time.monotonic()
                        + RETRY_COOLDOWN
                    )

            except Forbidden:
                # Foydalanuvchi botni bloklagan.
                # Faqat shu foydalanuvchi o'chiriladi.
                # Bot ishlashda davom etadi.
                log.info(
                    "Foydalanuvchi %s botni bloklagan, "
                    "o'chirib qo'yildi",
                    chat_id,
                )

                await self._db.set_user_field(
                    chat_id,
                    active=0,
                )

                # Keyingi foydalanuvchiga o'tamiz
                continue

            except RetryAfter as exc:
                log.warning(
                    "Telegram limiti. %s soniya kutamiz.",
                    exc.retry_after,
                )

                await asyncio.sleep(
                    exc.retry_after
                )

            except Exception:
                # Bitta foydalanuvchidagi xato
                # butun scheduler'ni to'xtatmaydi.
                log.exception(
                    "Foydalanuvchi %s uchun "
                    "yuborishda xato",
                    chat_id,
                )

                self._cooldown[chat_id] = (
                    time.monotonic()
                    + RETRY_COOLDOWN
                )

                continue

            # Telegram limitlariga hurmat
            await asyncio.sleep(0.05)