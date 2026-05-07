from __future__ import annotations
import asyncio
import gzip
import json
import time
from pathlib import Path
from typing import Awaitable, Callable

import aiofiles

from ..chunk import Chunk
from ..types import ChunkId, ChunkState, LogEntry


PersistedCallback = Callable[[ChunkId], Awaitable[None]]


class ChunkPersistence:
    """Writes sealed chunks to disk in JSON Lines + gzip format."""

    def __init__(
        self,
        cold_path: Path,
        on_chunk_persisted: PersistedCallback | None = None,
    ):
        self.cold_path = cold_path
        self.cold_path.mkdir(parents=True, exist_ok=True)
        self._on_chunk_persisted = on_chunk_persisted

    async def persist_chunk(self, chunk: Chunk) -> None:
        path = self.cold_path / chunk.header.chunk_id
        path.mkdir(exist_ok=True)

        # Serialize header
        header_dict = self._header_to_dict(chunk)
        async with aiofiles.open(path / "header.json", "w") as f:
            await f.write(json.dumps(header_dict))

        # Serialize entries (gzipped JSON Lines)
        entries_path = path / "entries.jsonl.gz"
        await asyncio.to_thread(self._write_entries_sync, chunk.entries, entries_path)

        # Mark persisted
        chunk.header.state = ChunkState.PERSISTED
        chunk.header.persisted_at = time.time()

        if self._on_chunk_persisted is not None:
            await self._on_chunk_persisted(chunk.header.chunk_id)

    @staticmethod
    def _header_to_dict(chunk: Chunk) -> dict:
        return {
            "chunk_id": chunk.header.chunk_id,
            "seq": chunk.header.seq,
            "ts_min": chunk.header.ts_min,
            "ts_max": chunk.header.ts_max,
            "services": list(chunk.header.services),
            "count": chunk.header.count,
            "size_bytes": chunk.header.size_bytes,
            "schema_sketch": {
                k: [t.__name__ for t in types]
                for k, types in chunk.header.schema_sketch.items()
            },
            "state": "persisted",
            "indexes_on_disk": chunk.header.indexes_on_disk,
            "persisted_at": time.time(),
        }

    @staticmethod
    def _write_entries_sync(entries: list[LogEntry], path: Path) -> None:
        with gzip.open(path, "wt", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps({
                    "ts": entry.ts,
                    "service": entry.service,
                    "level": entry.level,
                    "msg": entry.msg,
                    "fields": entry.fields,
                }) + "\n")
