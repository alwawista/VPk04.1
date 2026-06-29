from __future__ import annotations

import asyncio
import shutil
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from app.models import Category, Confidence, StoredTicket, TicketIn, TriageResult


class StorageUnavailable(Exception):
    pass


class SQLiteStorage:
    _REQUIRED_COLUMNS = frozenset(
        {"id", "created_at", "client_id", "channel", "text", "category", "confidence", "escalate", "draft_reply", "error"}
    )

    def __init__(self, database_url: str) -> None:
        if not database_url.startswith("sqlite:///"):
            raise ValueError("This MVP storage supports sqlite:/// URLs only.")
        parsed = urlparse(database_url)
        raw_path = parsed.path
        if raw_path.startswith("/") and len(raw_path) > 3 and raw_path[2] == ":":
            db_path = Path(raw_path[1:])
        else:
            db_path = Path(raw_path.lstrip("/"))
        self.path = db_path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init_sync(self) -> None:
        needs_recreate = False
        if self.path.exists():
            connection = self._connect()
            try:
                table = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='tickets'"
                ).fetchone()
                if table is not None:
                    columns = {row[1] for row in connection.execute("PRAGMA table_info(tickets)")}
                    needs_recreate = not self._REQUIRED_COLUMNS.issubset(columns)
            finally:
                connection.close()

        if needs_recreate:
            backup_path = self.path.with_name(f"{self.path.stem}.legacy-{int(time.time())}{self.path.suffix}")
            shutil.copy2(self.path, backup_path)
            connection = self._connect()
            try:
                connection.execute("DROP TABLE IF EXISTS tickets")
            finally:
                connection.close()

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    text TEXT NOT NULL,
                    category TEXT,
                    confidence TEXT,
                    escalate INTEGER,
                    draft_reply TEXT,
                    error TEXT
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_tickets_client_id ON tickets(client_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON tickets(created_at)")

    def _schema_is_compatible(self) -> bool:
        if not self.path.exists():
            return True
        connection = self._connect()
        try:
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tickets'"
            ).fetchone()
            if table is None:
                return True
            columns = {row[1] for row in connection.execute("PRAGMA table_info(tickets)")}
            return self._REQUIRED_COLUMNS.issubset(columns)
        finally:
            connection.close()

    async def create_ticket(self, ticket: TicketIn) -> int:
        return await asyncio.to_thread(self._with_retry, self._create_ticket_sync, ticket)

    def _create_ticket_sync(self, ticket: TicketIn) -> int:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tickets (created_at, client_id, channel, text)
                VALUES (?, ?, ?, ?)
                """,
                (now, ticket.client_id, ticket.channel.value, ticket.text),
            )
            return int(cursor.lastrowid)

    async def update_ticket(
        self,
        ticket_id: int,
        result: TriageResult,
        *,
        error: str | None = None,
    ) -> None:
        await asyncio.to_thread(self._with_retry, self._update_ticket_sync, ticket_id, result, error)

    def _update_ticket_sync(
        self,
        ticket_id: int,
        result: TriageResult,
        error: str | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tickets
                SET category = ?, confidence = ?, escalate = ?, draft_reply = ?, error = ?
                WHERE id = ?
                """,
                (
                    result.category.value,
                    result.confidence.value,
                    int(result.escalate),
                    result.draft_reply,
                    error,
                    ticket_id,
                ),
            )

    def _row_to_ticket(self, row: sqlite3.Row) -> StoredTicket:
        data = dict(row)
        data["escalate"] = bool(data["escalate"]) if data.get("escalate") is not None else None
        if data.get("category"):
            data["category"] = Category(data["category"])
        if data.get("confidence"):
            data["confidence"] = Confidence(data["confidence"])
        return StoredTicket(**data)

    async def get_ticket(self, ticket_id: int) -> StoredTicket | None:
        row = await asyncio.to_thread(self._get_ticket_sync, ticket_id)
        if row is None:
            return None
        return self._row_to_ticket(row)

    async def list_tickets(self, limit: int = 10) -> list[StoredTicket]:
        rows = await asyncio.to_thread(self._with_retry, self._list_tickets_sync, limit)
        return [self._row_to_ticket(row) for row in rows]

    def _list_tickets_sync(self, limit: int) -> list[sqlite3.Row]:
        with self._connect() as connection:
            cursor = connection.execute(
                "SELECT * FROM tickets ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return cursor.fetchall()

    def _get_ticket_sync(self, ticket_id: int) -> sqlite3.Row | None:
        with self._connect() as connection:
            cursor = connection.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
            return cursor.fetchone()

    async def count_tickets(self) -> int:
        return await asyncio.to_thread(self._count_tickets_sync)

    def _count_tickets_sync(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute("SELECT COUNT(*) FROM tickets")
            return int(cursor.fetchone()[0])

    def _with_retry(self, func, *args):
        delay = 0.05
        last_error: Exception | None = None
        for _ in range(5):
            try:
                return func(*args)
            except sqlite3.OperationalError as exc:
                last_error = exc
                if "locked" not in str(exc).lower():
                    break
                time.sleep(delay)
                delay *= 2
        raise StorageUnavailable(str(last_error) if last_error else "SQLite operation failed")
