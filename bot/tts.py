"""Talaffuz audiosi: gTTS bilan yaratiladi, diskda va Telegram file_id sifatida keshlanadi."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from gtts import gTTS
from telegram import Bot
from telegram.error import TelegramError

from .db import Database

log = logging.getLogger(__name__)


class AudioService:
    def __init__(self, db: Database, audio_dir: Path):
        self._db = db
        self._dir = audio_dir

    async def send_word_audio(self, bot: Bot, chat_id: int, word) -> None:
        title, performer = word["tr"], "Türkçe"

        file_id = word["audio_file_id"]
        if file_id:
            try:
                await bot.send_audio(chat_id, file_id, title=title, performer=performer)
                return
            except TelegramError:
                log.warning("Keshlangan file_id yaroqsiz (so'z %s), qayta yaratiladi", word["id"])

        path = self._dir / f"{word['id']}.mp3"
        if not path.exists():
            await asyncio.to_thread(self._synthesize, word["tr"], path)

        with path.open("rb") as handle:
            message = await bot.send_audio(chat_id, handle, title=title, performer=performer)
        if message.audio:
            await self._db.set_audio_file_id(word["id"], message.audio.file_id)

    @staticmethod
    def _synthesize(text: str, path: Path) -> None:
        tmp = path.with_suffix(".part")
        gTTS(text=text, lang="tr").save(str(tmp))
        tmp.replace(path)
