"""Bounded prediction summaries. Callers must never submit raw input values."""

from __future__ import annotations

import json
import os
import sqlite3
from collections import deque
from contextlib import closing
from threading import Lock
from typing import Any, Protocol


class HistoryStore(Protocol):
    limit: int

    def append(self, record: dict[str, Any]) -> None: ...

    def recent(self) -> list[dict[str, Any]]: ...


def _encode(record: dict[str, Any]) -> str:
    return json.dumps(record, allow_nan=False, sort_keys=True)


class InMemoryHistoryStore:
    def __init__(self, limit: int = 200):
        if limit < 1:
            raise ValueError("History limit must be positive")
        self.limit = limit
        self._records: deque[str] = deque(maxlen=limit)
        self._lock = Lock()

    def append(self, record: dict[str, Any]) -> None:
        encoded = _encode(record)
        with self._lock:
            self._records.append(encoded)

    def recent(self) -> list[dict[str, Any]]:
        with self._lock:
            return [json.loads(row) for row in reversed(self._records)]


class SQLiteHistoryStore:
    """One connection per operation; insert and retention share a transaction."""

    def __init__(self, path: str, limit: int = 200):
        if limit < 1:
            raise ValueError("History limit must be positive")
        self.path = path
        self.limit = limit
        with closing(self._connect()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS prediction_history "
                "(sequence INTEGER PRIMARY KEY AUTOINCREMENT, record TEXT NOT NULL)"
            )
            self._trim(conn)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def _trim(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "DELETE FROM prediction_history WHERE sequence NOT IN "
            "(SELECT sequence FROM prediction_history ORDER BY sequence DESC LIMIT ?)",
            (self.limit,),
        )

    def append(self, record: dict[str, Any]) -> None:
        encoded = _encode(record)
        with closing(self._connect()) as conn, conn:
            conn.execute("INSERT INTO prediction_history(record) VALUES (?)", (encoded,))
            self._trim(conn)

    def recent(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT record FROM prediction_history ORDER BY sequence DESC LIMIT ?",
                (self.limit,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]


def configured_history_store() -> HistoryStore:
    """Unset path preserves the original process-local 200-record history."""
    path = os.environ.get("RULGUARD_HISTORY_DB")
    limit = int(os.environ.get("RULGUARD_HISTORY_LIMIT", "200"))
    return SQLiteHistoryStore(path, limit) if path else InMemoryHistoryStore(limit)
