from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
import aiofiles

from ..types import LogEntry


class WAL:
    """
    Write-ahead log with batched fsync.

    Each entry is appended to a log file. Periodic fsync ensures durability.
    Truncation clears the log after corresponding chunk is persisted.
    """

    def __init__(self, path: Path, fsync_interval_ms: int = 100):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fsync_interval_ms = fsync_interval_ms
        self._buffer: list[bytes] = []
        self._lock = asyncio.Lock()
        self._stopped = False
        self._flush_task: asyncio.Task | None = None
        self._file = None

    async def start(self) -> None:
        self._file = await aiofiles.open(self.path, "ab")
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        self._stopped = True
        if self._flush_task:
            try:
                await asyncio.wait_for(self._flush_task, timeout=1.0)
            except asyncio.TimeoutError:
                self._flush_task.cancel()
        await self._flush()
        if self._file is not None:
            await self._file.close()
            self._file = None

    async def append(self, entry: LogEntry) -> None:
        line = json.dumps({
            "ts": entry.ts,
            "service": entry.service,
            "level": entry.level,
            "msg": entry.msg,
            "fields": entry.fields,
        }).encode() + b"\n"
        async with self._lock:
            self._buffer.append(line)

    async def _flush_loop(self) -> None:
        while not self._stopped:
            await asyncio.sleep(self.fsync_interval_ms / 1000)
            await self._flush()

    async def _flush(self) -> None:
        async with self._lock:
            if not self._buffer or self._file is None:
                return
            for line in self._buffer:
                await self._file.write(line)
            self._buffer.clear()
            await self._file.flush()
            try:
                os.fsync(self._file.fileno())
            except OSError:
                pass

    async def replay(self) -> list[LogEntry]:
        """Read all entries from the log on startup."""
        if not self.path.exists():
            return []
        entries: list[LogEntry] = []
        async with aiofiles.open(self.path, "r") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(LogEntry(
                        ts=data["ts"],
                        service=data["service"],
                        level=data["level"],
                        msg=data["msg"],
                        fields=data.get("fields", {}),
                    ))
                except (json.JSONDecodeError, KeyError):
                    continue  # skip corrupt lines
        return entries

    async def truncate(self) -> None:
        """Clear all WAL entries (called after persistence)."""
        async with self._lock:
            if self._file is not None:
                await self._file.close()
            self.path.unlink(missing_ok=True)
            self._file = await aiofiles.open(self.path, "ab")

    async def compact(self, keep_entries: list[LogEntry]) -> None:
        """Replace WAL contents with `keep_entries` only.

        Used after a chunk is persisted: drop everything from the WAL,
        but re-add entries belonging to the still-open chunk so they
        survive a crash before the next chunk is sealed.
        """
        async with self._lock:
            self._buffer.clear()
            if self._file is not None:
                await self._file.close()
            self.path.unlink(missing_ok=True)
            self._file = await aiofiles.open(self.path, "ab")
            for entry in keep_entries:
                line = json.dumps({
                    "ts": entry.ts,
                    "service": entry.service,
                    "level": entry.level,
                    "msg": entry.msg,
                    "fields": entry.fields,
                }).encode() + b"\n"
                await self._file.write(line)
            await self._file.flush()
            try:
                os.fsync(self._file.fileno())
            except OSError:
                pass
