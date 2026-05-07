from __future__ import annotations
from typing import TYPE_CHECKING

from ..chunk import Chunk
from ..types import Tier

if TYPE_CHECKING:
    from ..store import ChunkStore
    from .chunk_reader import ChunkReader
    from .wal import WAL


class RecoveryManager:
    """Restores ChunkStore state from disk on startup."""

    def __init__(self, store: "ChunkStore", wal: "WAL", reader: "ChunkReader"):
        self.store = store
        self.wal = wal
        self.reader = reader

    async def recover(self) -> None:
        # 1. Load all sealed chunks from disk (as COLD by default)
        headers = await self.reader.load_metadata()
        for header in headers:
            chunk = Chunk(header=header, entries=[], indexes={}, tier=Tier.COLD)
            self.store.chunks.append(chunk)
            if header.seq >= self.store._next_seq:
                self.store._next_seq = header.seq + 1

        # 2. Replay WAL into a new open chunk
        wal_entries = await self.wal.replay()
        for entry in wal_entries:
            self.store.append(entry, now=entry.ts)
