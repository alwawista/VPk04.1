#!/usr/bin/env python3
"""Export SQLite tickets table to CSV / Markdown / HTML for assignment submission."""

from __future__ import annotations

import argparse
import asyncio
import csv
import html
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.storage import SQLiteStorage

DEFAULT_OUT = ROOT / "reports"
COLUMNS = [
    "id",
    "created_at",
    "client_id",
    "channel",
    "text",
    "category",
    "confidence",
    "escalate",
    "draft_reply",
    "error",
]


def _fetch_rows(db_path: Path, limit: int | None) -> list[sqlite3.Row]:
    query = f"SELECT {', '.join(COLUMNS)} FROM tickets ORDER BY id ASC"
    params: tuple = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(query, params).fetchall()


def _row_dict(row: sqlite3.Row) -> dict[str, str]:
    data = {key: str(row[key]) if row[key] is not None else "" for key in COLUMNS}
    data["escalate"] = "true" if row["escalate"] else "false"
    return data


def export_csv(rows: list[sqlite3.Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_row_dict(row))


def export_markdown(rows: list[sqlite3.Row], path: Path, *, truncate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Лог откликов Support Triage",
        "",
        f"Сформировано: {datetime.now(UTC).isoformat()}",
        f"Записей: {len(rows)}",
        "",
        "| id | created_at | client_id | channel | category | confidence | escalate | text | draft_reply | error |",
        "|---:|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        data = _row_dict(row)
        text = data["text"]
        reply = data["draft_reply"]
        if truncate > 0:
            text = text[:truncate] + ("…" if len(text) > truncate else "")
            reply = reply[:truncate] + ("…" if len(reply) > truncate else "")
        cells = [
            data["id"],
            data["created_at"],
            data["client_id"],
            data["channel"],
            data["category"],
            data["confidence"],
            data["escalate"],
            text.replace("|", "\\|"),
            reply.replace("|", "\\|"),
            (data["error"] or "").replace("|", "\\|"),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_html(rows: list[sqlite3.Row], path: Path, *, truncate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    head = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <title>Лог откликов — Support Triage</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 24px; color: #111; }
    h1 { font-size: 1.4rem; }
    .meta { color: #555; margin-bottom: 16px; }
    table { border-collapse: collapse; width: 100%; font-size: 0.82rem; }
    th, td { border: 1px solid #ddd; padding: 8px; vertical-align: top; text-align: left; }
    th { background: #f4f4f5; position: sticky; top: 0; }
    tr:nth-child(even) { background: #fafafa; }
    .mono { font-family: ui-monospace, monospace; }
    .cat-billing { color: #b45309; font-weight: 600; }
    .cat-support { color: #1d4ed8; font-weight: 600; }
    .cat-complaint { color: #b91c1c; font-weight: 600; }
    .esc-true { color: #b45309; }
    .esc-false { color: #15803d; }
  </style>
</head>
<body>
  <h1>Лог откликов Support Triage</h1>
"""
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    body = [head, f'  <p class="meta">Записей: {len(rows)} · сформировано {generated}</p>', "  <table>", "    <thead><tr>"]
    for col in COLUMNS:
        body.append(f"<th>{html.escape(col)}</th>")
    body.append("</tr></thead><tbody>")

    for row in rows:
        data = _row_dict(row)
        text = data["text"]
        reply = data["draft_reply"]
        if truncate > 0:
            text = text[:truncate] + ("…" if len(text) > truncate else "")
            reply = reply[:truncate] + ("…" if len(reply) > truncate else "")
        cat_class = f"cat-{data['category']}" if data["category"] else ""
        esc_class = "esc-true" if data["escalate"] == "true" else "esc-false"
        body.append("<tr>")
        for key, value in (
            ("id", data["id"]),
            ("created_at", data["created_at"]),
            ("client_id", data["client_id"]),
            ("channel", data["channel"]),
            ("text", text),
            ("category", data["category"]),
            ("confidence", data["confidence"]),
            ("escalate", data["escalate"]),
            ("draft_reply", reply),
            ("error", data["error"]),
        ):
            extra = ""
            if key == "category":
                extra = f' class="{cat_class}"'
            elif key == "escalate":
                extra = f' class="{esc_class}"'
            body.append(f"<td{extra}>{html.escape(str(value))}</td>")
        body.append("</tr>")

    body.extend(["</tbody></table>", "</body></html>"])
    path.write_text("\n".join(body), encoding="utf-8")


async def _db_path() -> Path:
    load_dotenv()
    storage = SQLiteStorage(Settings.from_env().database_url)
    await storage.init()
    return storage.path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export response log from SQLite")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT, help="Output directory")
    parser.add_argument("--limit", type=int, default=None, help="Max rows (default: all)")
    parser.add_argument(
        "--format",
        choices=("csv", "md", "html", "all"),
        default="all",
        help="Output format",
    )
    parser.add_argument(
        "--truncate",
        type=int,
        default=120,
        help="Truncate text columns in md/html (0 = no truncate)",
    )
    args = parser.parse_args()

    db_path = asyncio.run(_db_path())
    rows = _fetch_rows(db_path, args.limit)
    if not rows:
        raise SystemExit(f"No tickets in {db_path}. Run seed or POST /triage first.")

    out_dir = args.out_dir.resolve()
    stem = "response_log"
    written: list[Path] = []

    if args.format in ("csv", "all"):
        path = out_dir / f"{stem}.csv"
        export_csv(rows, path)
        written.append(path)
    if args.format in ("md", "all"):
        path = out_dir / f"{stem}.md"
        export_markdown(rows, path, truncate=args.truncate)
        written.append(path)
    if args.format in ("html", "all"):
        path = out_dir / f"{stem}.html"
        export_html(rows, path, truncate=args.truncate)
        written.append(path)

    print(f"Exported {len(rows)} rows from {db_path}")
    for path in written:
        print(f"  -> {path}")


if __name__ == "__main__":
    main()
