"""The queue, in SQLite. Every confirm and dismiss is kept: it is the training data for
learning what matters to this person."""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

QUEUED, PRINTED, DISMISSED, IGNORED = "queued", "printed", "dismissed", "ignored"
PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    sender TEXT NOT NULL DEFAULT '',
    raw_text TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'normal',
    due TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    engine TEXT NOT NULL,
    external_id TEXT,
    created_at REAL NOT NULL,
    decided_at REAL,
    UNIQUE (source, external_id)
);
CREATE INDEX IF NOT EXISTS items_status ON items (status);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


@dataclass
class Item:
    id: int
    source: str
    sender: str
    raw_text: str
    title: str
    detail: str
    priority: str
    due: str
    status: str
    engine: str
    created_at: float


class Store:
    def __init__(self, path: Path | str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)

    def seen(self, source: str, external_id: Optional[str]) -> bool:
        if not external_id:
            return False
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM items WHERE source = ? AND external_id = ?",
                (source, external_id),
            ).fetchone()
        return row is not None

    def add(
        self,
        *,
        source: str,
        sender: str,
        raw_text: str,
        title: str,
        detail: str = "",
        priority: str = "normal",
        due: str = "",
        status: str = QUEUED,
        engine: str = "none",
        external_id: Optional[str] = None,
    ) -> Optional[int]:
        """Returns the new id, or None when this external_id is already stored."""
        with self._lock, self._db:
            cur = self._db.execute(
                """INSERT OR IGNORE INTO items
                   (source, sender, raw_text, title, detail, priority, due, status, engine,
                    external_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source, sender, raw_text, title, detail, priority, due, status, engine,
                 external_id, time.time()),
            )
            return cur.lastrowid if cur.rowcount else None

    def get(self, item_id: int) -> Optional[Item]:
        with self._lock:
            row = self._db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return _to_item(row) if row else None

    def next_queued(self) -> Optional[Item]:
        with self._lock:
            row = self._db.execute(
                """SELECT * FROM items WHERE status = ?
                   ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,
                            created_at, id
                   LIMIT 1""",
                (QUEUED,),
            ).fetchone()
        return _to_item(row) if row else None

    def queue_size(self) -> int:
        with self._lock:
            return self._db.execute(
                "SELECT COUNT(*) FROM items WHERE status = ?", (QUEUED,)
            ).fetchone()[0]

    def decide(self, item_id: int, status: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE items SET status = ?, decided_at = ? WHERE id = ?",
                (status, time.time(), item_id),
            )

    def stats(self) -> dict[str, int]:
        with self._lock:
            rows = self._db.execute(
                "SELECT status, COUNT(*) FROM items GROUP BY status"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def kv_get(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def kv_set(self, key: str, value: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )


def _to_item(row: sqlite3.Row) -> Item:
    return Item(
        id=row["id"], source=row["source"], sender=row["sender"], raw_text=row["raw_text"],
        title=row["title"], detail=row["detail"], priority=row["priority"], due=row["due"],
        status=row["status"], engine=row["engine"], created_at=row["created_at"],
    )
