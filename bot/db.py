"""SQLite saqlash qatlami (aiosqlite)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    chat_id        INTEGER PRIMARY KEY,
    username       TEXT,
    first_name     TEXT,
    level          TEXT    NOT NULL DEFAULT 'A1',
    words_per_day  INTEGER NOT NULL DEFAULT 5,
    send_time      TEXT    NOT NULL DEFAULT '09:00',
    active         INTEGER NOT NULL DEFAULT 1,
    last_sent_date TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS words (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tr            TEXT NOT NULL COLLATE NOCASE UNIQUE,
    uz            TEXT NOT NULL,
    example_tr    TEXT,
    example_uz    TEXT,
    level         TEXT NOT NULL DEFAULT 'A1',
    audio_file_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_words_level ON words(level);

CREATE TABLE IF NOT EXISTS user_words (
    user_id       INTEGER NOT NULL REFERENCES users(chat_id) ON DELETE CASCADE,
    word_id       INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    status        TEXT    NOT NULL DEFAULT 'learning',   -- learning | known
    box           INTEGER NOT NULL DEFAULT 0,
    introduced_on TEXT    NOT NULL,
    next_review   TEXT,
    correct       INTEGER NOT NULL DEFAULT 0,
    wrong         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, word_id)
);
CREATE INDEX IF NOT EXISTS idx_uw_due ON user_words(user_id, status, next_review);
"""

_USER_FIELDS = {"level", "words_per_day", "send_time", "active", "last_sent_date"}


class Database:
    def __init__(self, path: Path | str):
        self._path = str(path)
        self._conn: aiosqlite.Connection | None = None

    # ---- ulanish -------------------------------------------------------
    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Baza ulanmagan: avval connect() chaqiring")
        return self._conn

    async def _one(self, sql: str, params: tuple = ()):
        async with self.conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def _all(self, sql: str, params: tuple = ()):
        async with self.conn.execute(sql, params) as cur:
            return await cur.fetchall()

    async def _run(self, sql: str, params: tuple = ()) -> int:
        cur = await self.conn.execute(sql, params)
        await self.conn.commit()
        count = cur.rowcount
        await cur.close()
        return count

    # ---- foydalanuvchilar ---------------------------------------------
    async def register_user(
        self,
        chat_id: int,
        username: str | None,
        first_name: str | None,
        send_time: str,
        words_per_day: int,
    ):
        await self._run(
            """INSERT INTO users(chat_id, username, first_name, send_time, words_per_day)
               VALUES(?, ?, ?, ?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET
                   username = excluded.username,
                   first_name = excluded.first_name""",
            (chat_id, username, first_name, send_time, words_per_day),
        )
        return await self.get_user(chat_id)

    async def get_user(self, chat_id: int):
        return await self._one("SELECT * FROM users WHERE chat_id = ?", (chat_id,))

    async def set_user_field(self, chat_id: int, **fields) -> None:
        if not fields or not set(fields) <= _USER_FIELDS:
            raise ValueError(f"Noto'g'ri maydonlar: {sorted(fields)}")
        assignments = ", ".join(f"{name} = ?" for name in fields)
        await self._run(
            f"UPDATE users SET {assignments} WHERE chat_id = ?",
            (*fields.values(), chat_id),
        )

    async def users_due_for_delivery(self, today: str, hhmm: str):
        return await self._all(
            """SELECT * FROM users
               WHERE active = 1
                 AND (last_sent_date IS NULL OR last_sent_date != ?)
                 AND send_time <= ?""",
            (today, hhmm),
        )

    # ---- so'zlar -------------------------------------------------------
    async def add_words(self, words: Iterable[dict]) -> int:
        added = 0
        for w in words:
            cur = await self.conn.execute(
                """INSERT OR IGNORE INTO words(tr, uz, example_tr, example_uz, level)
                   VALUES(?, ?, ?, ?, ?)""",
                (w["tr"], w["uz"], w.get("example_tr"), w.get("example_uz"), w.get("level", "A1")),
            )
            added += max(cur.rowcount, 0)
            await cur.close()
        await self.conn.commit()
        return added

    async def count_words(self) -> int:
        row = await self._one("SELECT COUNT(*) AS n FROM words")
        return row["n"]

    async def recent_words(self, level: str, limit: int) -> list[str]:
        rows = await self._all(
            "SELECT tr FROM words WHERE level = ? ORDER BY id DESC LIMIT ?", (level, limit)
        )
        return [r["tr"] for r in rows]

    async def get_word(self, word_id: int):
        return await self._one("SELECT * FROM words WHERE id = ?", (word_id,))

    async def set_audio_file_id(self, word_id: int, file_id: str) -> None:
        await self._run("UPDATE words SET audio_file_id = ? WHERE id = ?", (file_id, word_id))

    async def new_words_for_user(self, chat_id: int, level: str, limit: int):
        return await self._all(
            """SELECT w.* FROM words w
               WHERE w.level = ?
                 AND NOT EXISTS (
                     SELECT 1 FROM user_words uw
                     WHERE uw.user_id = ? AND uw.word_id = w.id)
               ORDER BY w.id
               LIMIT ?""",
            (level, chat_id, limit),
        )

    async def distractors(self, word_id: int, uz: str, n: int = 3) -> list:
        rows = await self._all(
            """SELECT id, uz FROM words
               WHERE id != ? AND uz != ? COLLATE NOCASE
               ORDER BY RANDOM() LIMIT 30""",
            (word_id, uz),
        )
        seen = {uz.lower()}
        picked = []
        for row in rows:
            key = row["uz"].lower()
            if key in seen:
                continue
            seen.add(key)
            picked.append(row)
            if len(picked) == n:
                break
        return picked

    # ---- o'rganish jarayoni -------------------------------------------
    async def introduce(
        self, chat_id: int, word_ids: list[int], today: str, first_review: str
    ) -> None:
        await self.conn.executemany(
            """INSERT OR IGNORE INTO user_words(user_id, word_id, introduced_on, next_review)
               VALUES(?, ?, ?, ?)""",
            [(chat_id, wid, today, first_review) for wid in word_ids],
        )
        await self.conn.commit()

    async def todays_words(self, chat_id: int, today: str):
        return await self._all(
            """SELECT w.* FROM user_words uw
               JOIN words w ON w.id = uw.word_id
               WHERE uw.user_id = ? AND uw.introduced_on = ?
               ORDER BY w.id""",
            (chat_id, today),
        )

    async def get_progress(self, chat_id: int, word_id: int):
        return await self._one(
            "SELECT * FROM user_words WHERE user_id = ? AND word_id = ?", (chat_id, word_id)
        )

    async def next_due_word(self, chat_id: int, today: str):
        return await self._one(
            """SELECT w.*, uw.box AS box FROM user_words uw
               JOIN words w ON w.id = uw.word_id
               WHERE uw.user_id = ? AND uw.status = 'learning'
                 AND uw.next_review IS NOT NULL AND uw.next_review <= ?
               ORDER BY uw.next_review, RANDOM()
               LIMIT 1""",
            (chat_id, today),
        )

    async def count_due(self, chat_id: int, today: str) -> int:
        row = await self._one(
            """SELECT COUNT(*) AS n FROM user_words
               WHERE user_id = ? AND status = 'learning'
                 AND next_review IS NOT NULL AND next_review <= ?""",
            (chat_id, today),
        )
        return row["n"]

    async def update_progress(
        self,
        chat_id: int,
        word_id: int,
        status: str,
        box: int,
        next_review: str | None,
        correct: bool,
    ) -> None:
        await self._run(
            """UPDATE user_words
               SET status = ?, box = ?, next_review = ?,
                   correct = correct + ?, wrong = wrong + ?
               WHERE user_id = ? AND word_id = ?""",
            (status, box, next_review, int(correct), int(not correct), chat_id, word_id),
        )

    async def mark_known(self, chat_id: int, word_id: int) -> None:
        await self._run(
            """UPDATE user_words SET status = 'known', next_review = NULL
               WHERE user_id = ? AND word_id = ?""",
            (chat_id, word_id),
        )

    async def mark_repeat(self, chat_id: int, word_id: int, next_review: str) -> None:
        await self._run(
            """UPDATE user_words SET status = 'learning', box = 0, next_review = ?
               WHERE user_id = ? AND word_id = ?""",
            (next_review, chat_id, word_id),
        )

    # ---- statistika ----------------------------------------------------
    async def user_stats(self, chat_id: int, today: str) -> dict:
        row = await self._one(
            """SELECT COUNT(*) AS total,
                      COALESCE(SUM(status = 'known'), 0)    AS known,
                      COALESCE(SUM(status = 'learning'), 0) AS learning,
                      COALESCE(SUM(correct), 0)             AS correct,
                      COALESCE(SUM(wrong), 0)               AS wrong
               FROM user_words WHERE user_id = ?""",
            (chat_id,),
        )
        stats = dict(row)
        stats["due"] = await self.count_due(chat_id, today)
        return stats

    async def global_stats(self) -> dict:
        row = await self._one(
            """SELECT (SELECT COUNT(*) FROM users)               AS users,
                      (SELECT COUNT(*) FROM users WHERE active=1) AS active,
                      (SELECT COUNT(*) FROM words)               AS words"""
        )
        return dict(row)
