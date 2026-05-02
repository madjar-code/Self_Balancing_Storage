from __future__ import annotations
import time
from typing import Awaitable, Callable

from .chunk import Chunk
from .config import Config
from .types import (
    ChunkId,
    LogEntry,
    Predicate,
    PredicateOp,
)


SealCallback = Callable[[ChunkId], Awaitable[None]]


class ChunkStore:
    def __init__(
        self,
        config: Config,
        on_chunk_sealed: SealCallback | None = None,
    ):
        self.config = config
        self.chunks: list[Chunk] = []
        self._open_chunk: Chunk | None = None
        self._next_seq = 1
        self._on_chunk_sealed = on_chunk_sealed

    def append(self, entry: LogEntry, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        if self._open_chunk is None:
            self._open_chunk = Chunk.new(seq=self._next_seq, now=now)
            self._next_seq += 1
            self.chunks.append(self._open_chunk)

        self._open_chunk.append(entry)

        if self._should_seal(now):
            self._self_open_chunk()

    def _should_seal(self, now: float) -> bool:
        c = self._open_chunk
        if c is None:
            return False
        h = c.header
        if h.count >= self.config.chunk_max_entries:
            return True
        if h.size_bytes >= self.config.chunk_max_bytes:
            return True
        if (now - h.ts_min) >= self.config.chunk_max_seconds:
            return True
        return False

    def _seal_open_chunk(self) -> None:
        if self._open_chunk is None:
            return
        chunk = self._open_chunk
        chunk.seal()
        self._open_chunk = None
        # Engine event hook is called externally (see runtime.py)

    def find(
        self,
        predicate: Predicate,
        time_range: tuple[float, float] | None = None,
    ) -> tuple[list[LogEntry], list[ChunkId]]:
        """
        Returns (results, scanned_chunk_ids).
        scanned_chunk_ids is needed to emit QueryEvent to Tracker.
        """
        results: list[LogEntry] = []
        scanned: list[ChunkId] = []

        for chunk in self.chunks:
            if not _chunk_in_range(chunk, time_range):
                continue
            scanned.append(chunk.header.chunk_id)
            # scan-only for now; index integration comes in Phase 7
            positions = chunk.scan(predicate)
            results.extend(chunk.entries[i] for i in positions)
        return results, scanned

    def take_pending_seal(self) -> ChunkId | None:
        """Drain: if a chunk was just sealed, return its id for the event hook."""
        # implementation will be finalized in Phase 7 during engine wiring
        return None


def _chunk_in_range(chunk: Chunk, time_range: tuple[float, float] | None) -> bool:
    if time_range is None:
        return True
    lo, hi = time_range
    return not (chunk.header.ts_max < lo or chunk.header.ts_min > hi)
