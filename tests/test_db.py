import asyncio

from bot.db import Database

WORDS = [
    {"tr": "su", "uz": "suv", "level": "A1"},
    {"tr": "SU", "uz": "boshqa", "level": "A1"},  # takror (katta-kichik harf farqi)
    {"tr": "ekmek", "uz": "non", "level": "A1"},
    {"tr": "kitap", "uz": "kitob", "level": "A1"},
    {"tr": "başarı", "uz": "muvaffaqiyat", "level": "B1"},
]


def run(coro):
    return asyncio.run(coro)


async def _make(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    await db.connect()
    await db.register_user(1, "ali", "Ali", "09:00", 5)
    return db


def test_words_are_unique_case_insensitive(tmp_path):
    async def go():
        db = await _make(tmp_path)
        assert await db.add_words(WORDS) == 4
        assert await db.count_words() == 4
        await db.close()

    run(go())


def test_new_words_exclude_already_introduced(tmp_path):
    async def go():
        db = await _make(tmp_path)
        await db.add_words(WORDS)
        first = await db.new_words_for_user(1, "A1", 2)
        assert len(first) == 2
        await db.introduce(1, [w["id"] for w in first], "2026-10-04", "2026-10-05")
        rest = await db.new_words_for_user(1, "A1", 5)
        assert len(rest) == 1
        assert {w["id"] for w in rest}.isdisjoint({w["id"] for w in first})
        assert len(await db.todays_words(1, "2026-10-04")) == 2
        await db.close()

    run(go())


def test_due_and_progress_flow(tmp_path):
    async def go():
        db = await _make(tmp_path)
        await db.add_words(WORDS)
        word = (await db.new_words_for_user(1, "A1", 1))[0]
        await db.introduce(1, [word["id"]], "2026-10-04", "2026-10-05")

        assert await db.next_due_word(1, "2026-10-04") is None
        due = await db.next_due_word(1, "2026-10-05")
        assert due["id"] == word["id"]
        assert await db.count_due(1, "2026-10-05") == 1

        await db.update_progress(1, word["id"], "learning", 1, "2026-10-08", True)
        assert await db.count_due(1, "2026-10-05") == 0
        stats = await db.user_stats(1, "2026-10-08")
        assert (stats["total"], stats["correct"], stats["wrong"], stats["due"]) == (1, 1, 0, 1)

        await db.mark_known(1, word["id"])
        assert await db.count_due(1, "2030-01-01") == 0
        assert (await db.user_stats(1, "2030-01-01"))["known"] == 1

        await db.mark_repeat(1, word["id"], "2026-10-09")
        assert await db.count_due(1, "2026-10-09") == 1
        await db.close()

    run(go())


def test_scheduler_query_and_distractors(tmp_path):
    async def go():
        db = await _make(tmp_path)
        await db.add_words(WORDS)

        assert len(await db.users_due_for_delivery("2026-10-04", "08:59")) == 0
        assert len(await db.users_due_for_delivery("2026-10-04", "09:00")) == 1
        await db.set_user_field(1, last_sent_date="2026-10-04")
        assert len(await db.users_due_for_delivery("2026-10-04", "23:59")) == 0
        await db.set_user_field(1, active=0)
        assert len(await db.users_due_for_delivery("2026-10-05", "23:59")) == 0

        word = (await db.new_words_for_user(1, "A1", 1))[0]
        options = await db.distractors(word["id"], word["uz"], 3)
        assert len(options) == 3
        assert word["uz"] not in {o["uz"] for o in options}
        await db.close()

    run(go())
