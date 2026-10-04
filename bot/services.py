"""Ilova konteyneri: handlerlar uchun umumiy xizmatlar."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .config import Settings
from .db import Database
from .delivery import DeliveryService
from .tts import AudioService
from .words import WordService


@dataclass
class AppContext:
    settings: Settings
    db: Database
    words: WordService
    audio: AudioService
    delivery: DeliveryService

    def today(self) -> date:
        return datetime.now(self.settings.tz).date()
