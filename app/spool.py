from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class EmergencySpool:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def append(self, event_type: str, payload: dict[str, Any]) -> None:
        record = {
            "event_type": event_type,
            "created_at": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        async with self._lock:
            await asyncio.to_thread(self._append_sync, record)

    def _append_sync(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
