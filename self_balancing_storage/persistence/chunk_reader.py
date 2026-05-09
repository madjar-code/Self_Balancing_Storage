from __future__ import annotations
import asyncio
import gzip
import json
from pathlib import Path

import aiofiles

from ..chunk import ChunkHeader
from ..types import ChunkId, ChunkState, LogEntry


# Map type name strings back to Python types
_TYPE_MAP = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict
}


class ChunkReader:
    """Reads chunk metadata and entries from disk."""

    def __init__(self, cold_path: Path):
        self.cold_path = cold_path

    async def load_metadata(self) -> list[ChunkHeader]:
        if not self.cold_path.exists():
            return []
        headers: list[ChunkHeader] = []

        for chunk_dir in sorted(self.cold_path.iterdir()):
            if not chunk_dir.is_dir() or not chunk_dir.name.startswith("chunk_"):
                continue
            header_path = chunk_dir / "header.json"
            if not header_path.exists():
                continue
            try:
                async with aiofiles.open(header_path, "r") as f:
                    data = json.loads(await f.read())
                headers.append(self._parse_header(data))
            except (json.JSONDecodeError, KeyError):
                continue
        return headers

    @staticmethod
    def _parse_header(data: dict) -> ChunkHeader:
        return ChunkHeader(
            chunk_id=data["chunk_id"],
            seq=data["seq"],
            ts_min=data["ts_min"],
            ts_max=data["ts_max"],
            services=set(data.get("services", [])),
            count=data["count"],
            size_bytes=data["size_bytes"],
            schema_sketch={
                k: {_TYPE_MAP.get(t, str) for t in types}
                for k, types in data.get("schema_sketch", {}).items()
            },
            state=ChunkState.PERSISTED,
            indexes_on_disk=data.get("indexes_on_disk", []),
            persisted_at=data.get("persisted_at"),
        )

    async def load_entries(self, chunk_id: ChunkId) -> list[LogEntry]:
        path = self.cold_path / chunk_id / "entries.jsonl.gz"
        if not path.exists():
            return []
        return await asyncio.to_thread(self._read_entries_sync, path)

    @staticmethod
    def _read_entries_sync(path: Path) -> list[LogEntry]:
        entries: list[LogEntry] = []
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data: dict = json.loads(line)
                    entries.append(LogEntry(
                        ts=data["ts"],
                        service=data["service"],
                        level=data["level"],
                        msg=data["msg"],
                        fields=data.get("fields", {})
                    ))
                except (json.JSONDecodeError, KeyError):
                    continue
        return entries
