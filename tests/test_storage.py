from __future__ import annotations

import sqlite3
from pathlib import Path

from app.storage import SQLiteStorage


def test_legacy_schema_is_replaced_on_init(tmp_path: Path):
    db_path = tmp_path / "triage.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                client_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    storage = SQLiteStorage(f"sqlite:///{db_path}")
    storage._init_sync()

    assert not db_path.exists() or storage._schema_is_compatible()
    backups = list(tmp_path.glob("triage.legacy-*.db"))
    assert len(backups) == 1

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tickets)")}
    assert "category" in columns
    assert "draft_reply" in columns
    assert "request_id" not in columns
