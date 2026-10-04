"""So'zlar manbai: ichki katta ro'yxat + (ixtiyoriy) AI orqali yangi so'zlar yaratish.

Provayderlar (ustuvorlik tartibida):
  1. Claude (ANTHROPIC_API_KEY) — pullik
  2. Gemini (GEMINI_API_KEY)    — Google AI Studio'ning bepul kaliti bilan ishlaydi
  3. Hech biri                  — faqat ichki ro'yxatdagi so'zlar ishlatiladi (pulsiz, kalitsiz)
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from .config import LEVELS, Settings
from .db import Database

log = logging.getLogger(__name__)

SEED_PATH = Path(__file__).with_name("seed_words.json")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"

LEVEL_HINTS = {
    "A1": "absolute beginner (A1): the most common everyday words, very simple example sentences",
    "A2": "elementary (A2): common everyday words and short practical phrases, simple example sentences",
    "B1": "intermediate (B1): wider vocabulary, abstract and work/travel/social topics, natural example sentences",
}


def parse_words(text: str) -> list[dict]:
    """Model javobidan JSON massivni ajratib oladi va tozalaydi."""
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError("Javobda JSON massiv topilmadi")
    data = json.loads(text[start : end + 1])

    result: list[dict] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        tr = str(item.get("tr", "")).strip()
        uz = str(item.get("uz", "")).strip()
        if not tr or not uz:
            continue
        key = tr.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "tr": tr,
                "uz": uz,
                "example_tr": str(item.get("example_tr", "")).strip() or None,
                "example_uz": str(item.get("example_uz", "")).strip() or None,
            }
        )
    return result


def gemini_text(data: dict) -> str:
    """Gemini generateContent javobidan matnni ajratib oladi."""
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        raise ValueError("Gemini javobi kutilgan ko'rinishda emas") from None
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    if not text.strip():
        raise ValueError("Gemini bo'sh javob qaytardi")
    return text


class WordService:
    def __init__(self, db: Database, settings: Settings):
        self._db = db
        self._s = settings
        self._anthropic = None
        self._provider: str | None = None

        if settings.anthropic_api_key:
            from anthropic import AsyncAnthropic  # kechiktirilgan import

            self._anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
            self._provider = "claude"
        elif settings.gemini_api_key:
            self._provider = "gemini"

        if self._provider:
            log.info("Yangi so'zlar manbai: %s", self._provider)
        else:
            log.info("API kaliti yo'q: faqat ichki so'zlar ro'yxati ishlatiladi (pulsiz rejim)")

        self._locks = {level: asyncio.Lock() for level in LEVELS}

    async def sync_seed(self) -> None:
        """Ichki ro'yxatni bazaga qo'shadi (mavjud so'zlar o'zgarmaydi, faqat yangilari qo'shiladi)."""
        data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        added = await self._db.add_words(data)
        if added:
            log.info("Bazaga %d ta yangi so'z qo'shildi (ichki ro'yxatdan)", added)

    async def pick_new(self, user) -> list:
        """Foydalanuvchiga hali berilmagan so'zlarni tanlaydi; yetmasa yangilarini yaratadi."""
        need, level, chat_id = user["words_per_day"], user["level"], user["chat_id"]
        rows = await self._db.new_words_for_user(chat_id, level, need)
        if len(rows) >= need:
            return rows
        if self._provider is None:
            log.warning(
                "%s darajasidagi so'zlar tugayapti (qoldi: %d) va API kaliti yo'q. "
                "GEMINI_API_KEY (bepul) qo'shing yoki seed_words.json ni kengaytiring.",
                level,
                len(rows),
            )
            return rows

        async with self._locks[level]:
            for _ in range(3):
                rows = await self._db.new_words_for_user(chat_id, level, need)
                if len(rows) >= need:
                    break
                try:
                    added = await self._generate(level)
                    log.info("%s darajasi uchun %d ta yangi so'z yaratildi", level, added)
                except Exception as exc:
                    log.error("Yangi so'z yaratib bo'lmadi: %s: %s", type(exc).__name__, exc)
                    break
            return await self._db.new_words_for_user(chat_id, level, need)

    # ---- AI orqali yaratish ----------------------------------------------
    def _prompt(self, level: str, recent: list[str]) -> str:
        return (
            f"Give me {self._s.generate_batch} NEW useful Turkish vocabulary words for a learner at this level: "
            f"{LEVEL_HINTS[level]}.\n"
            "For each word provide its Uzbek translation (Latin script, natural and accurate), "
            "one short Turkish example sentence, and the Uzbek translation of that sentence.\n"
            f"Do NOT use any of these words: {json.dumps(recent, ensure_ascii=False)}.\n"
            'Reply ONLY with a JSON array like '
            '[{"tr": "...", "uz": "...", "example_tr": "...", "example_uz": "..."}]. '
            "No other text and no markdown."
        )

    async def _complete(self, prompt: str) -> str:
        if self._provider == "claude":
            response = await self._anthropic.messages.create(
                model=self._s.anthropic_model,
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        return await self._gemini_complete(prompt)

    async def _gemini_complete(self, prompt: str) -> str:
        import httpx  # PTB bilan birga o'rnatiladi

        url = f"{GEMINI_URL}/{self._s.gemini_model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7},
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                url, headers={"x-goog-api-key": self._s.gemini_api_key}, json=payload
            )
        response.raise_for_status()
        return gemini_text(response.json())

    async def _generate(self, level: str) -> int:
        recent = await self._db.recent_words(level, 300)
        text = await self._complete(self._prompt(level, recent))
        items = parse_words(text)
        for item in items:
            item["level"] = level
        return await self._db.add_words(items)
