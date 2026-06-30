#!/usr/bin/env python3
"""Import ticket rows from CSV into SQLite for demo UI history."""

from __future__ import annotations

import argparse
import asyncio
import csv
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.storage import SQLiteStorage

DEFAULT_CSV = ROOT / "data" / "samples" / "tickets_60.csv"

INSERT_SQL = """
INSERT INTO tickets (
    created_at, client_id, channel, text,
    category, confidence, escalate, draft_reply, error
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _parse_bool(value: str) -> int:
    return 1 if value.strip().lower() in {"1", "true", "yes"} else 0


def _import_rows(connection: sqlite3.Connection, csv_path: Path, *, clear: bool) -> int:
    if clear:
        connection.execute("DELETE FROM tickets")

    count = 0
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "created_at",
            "client_id",
            "channel",
            "text",
            "category",
            "confidence",
            "escalate",
            "draft_reply",
        }
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            missing = required - set(reader.fieldnames or [])
            raise ValueError(f"CSV missing columns: {', '.join(sorted(missing))}")

        for row in reader:
            error = (row.get("error") or "").strip() or None
            connection.execute(
                INSERT_SQL,
                (
                    row["created_at"],
                    row["client_id"],
                    row["channel"],
                    row["text"],
                    row["category"],
                    row["confidence"],
                    _parse_bool(row["escalate"]),
                    row["draft_reply"],
                    error,
                ),
            )
            count += 1

    return count


async def _prepare_database() -> Path:
    load_dotenv()
    settings = Settings.from_env()
    storage = SQLiteStorage(settings.database_url)
    await storage.init()
    return storage.path


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SQLite tickets table from CSV")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Path to CSV file (default: {DEFAULT_CSV.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete existing tickets before import",
    )
    args = parser.parse_args()

    csv_path = args.csv.resolve()
    if not csv_path.is_file():
        raise SystemExit(f"CSV not found: {csv_path}")

    db_path = asyncio.run(_prepare_database())

    with sqlite3.connect(db_path) as connection:
        imported = _import_rows(connection, csv_path, clear=args.clear)

    print(f"Imported {imported} tickets into {db_path}")
    if args.clear:
        print("(existing rows were cleared)")


if __name__ == "__main__":
    main()
