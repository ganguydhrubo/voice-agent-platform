"""SQLite storage and migrations.

SQLite in WAL mode is the default because it needs no server and is enough for one machine. All
tenant data is reached through helpers that take tenant_id, so a query cannot forget the filter.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def later_iso(**delta: float) -> str:
    return (datetime.now(UTC) + timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_id() -> str:
    return uuid.uuid4().hex


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def migrate(self) -> list[str]:
        """Apply each migration once, in file-name order, inside a transaction."""
        applied: list[str] = []
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            done = {row["version"] for row in self._conn.execute("SELECT version FROM schema_migrations")}
            for script in sorted(MIGRATIONS.glob("*.sql")):
                if script.stem in done:
                    continue
                self._conn.executescript(
                    "BEGIN;\n"
                    + script.read_text(encoding="utf-8")
                    + "\nINSERT INTO schema_migrations VALUES "
                    + f"('{script.stem}', '{now_iso()}');\nCOMMIT;"
                )
                applied.append(script.stem)
        return applied

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.executemany(sql, rows)
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def one(self, sql: str, params: Sequence[Any] = ()) -> dict | None:
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        with self._lock:
            return [dict(row) for row in self._conn.execute(sql, params).fetchall()]

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return row[0] if row else None

    def audit(
        self,
        tenant_id: str | None,
        actor: str,
        action: str,
        target: str = "",
        detail: dict | None = None,
        ip: str = "",
    ) -> None:
        self.execute(
            "INSERT INTO audit_log (tenant_id, actor, action, target, detail, ip, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, actor, action, target, json.dumps(detail or {}), ip, now_iso()),
        )
