"""Sozlamalar: muhit o'zgaruvchilaridan (.env) o'qiladi."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

LEVELS = ("A1", "A2", "B1")
MAX_WORDS_PER_DAY = 20


@dataclass(frozen=True)
class Settings:
    bot_token: str
    anthropic_api_key: str | None
    anthropic_model: str
    gemini_api_key: str | None
    gemini_model: str
    admin_id: int | None
    data_dir: Path
    tz: ZoneInfo
    default_send_time: str
    default_words_per_day: int
    quiz_length: int
    generate_batch: int

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bot.sqlite3"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def load_settings() -> Settings:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN o'rnatilmagan. .env faylni tekshiring.")

    data_dir = Path(os.getenv("DATA_DIR", "data").strip() or "data")
    (data_dir / "audio").mkdir(parents=True, exist_ok=True)

    admin_raw = os.getenv("ADMIN_ID", "").strip()
    return Settings(
        bot_token=token,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip() or None,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "").strip() or "claude-sonnet-5-5",
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip() or None,
        gemini_model=os.getenv("GEMINI_MODEL", "").strip() or "gemini-2.5-flash",
        admin_id=int(admin_raw) if admin_raw else None,
        data_dir=data_dir,
        tz=ZoneInfo(os.getenv("TIMEZONE", "").strip() or "Asia/Tashkent"),
        default_send_time=os.getenv("DEFAULT_SEND_TIME", "").strip() or "09:00",
        default_words_per_day=_int("DEFAULT_WORDS_PER_DAY", 5),
        quiz_length=_int("QUIZ_LENGTH", 10),
        generate_batch=_int("GENERATE_BATCH", 50),
    )
