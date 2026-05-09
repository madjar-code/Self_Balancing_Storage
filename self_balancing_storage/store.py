from __future__ import annotations
import asyncio
import time
from typing import Awaitable, Callable

from .chunk import Chunk, make_matcher
from .config import Config
from .types import (
    ChunkId,
    IndexId,
    Predicate,
    PredicateOp,
    LogEntry,
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
        self._on_chunk_sealed = on_chunk_sealed
        self._open_chunk: Chunk | None = None
        self._next_seq = 1
        self._pending_seal_tasks: set[asyncio.Task[None]] = set()

    def append(self, entry: LogEntry, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        if self._open_chunk is None:
            self._open_chunk = Chunk.new(seq=self._next_seq, now=now)
            self._next_seq += 1
            self.chunks.append(self._open_chunk)

        self._open_chunk.append(entry)

        if self._should_seal(now):
            self._seal_open_chunk()

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
        if self._on_chunk_sealed is not None:
            coro = self._on_chunk_sealed(chunk.header.chunk_id)
            task: asyncio.Task[None] = asyncio.create_task(coro)  # type: ignore[arg-type]
            self._pending_seal_tasks.add(task)
            task.add_done_callback(self._pending_seal_tasks.discard)

    def find(
        self,
        predicate: Predicate,
        time_range: tuple[float, float] | None = None,
    ) -> tuple[list[LogEntry], list[ChunkId], list[IndexId]]:
        results: list[LogEntry] = []
        scanned: list[ChunkId] = []
        used_indexes: list[IndexId] = []

        for chunk in self.chunks:
            if not _chunk_in_range(chunk, time_range):
                continue
            scanned.append(chunk.header.chunk_id)

            idx = _pick_index(chunk, predicate)
            if idx is None:
                results.extend(chunk.entries[p] for p in chunk.scan(predicate))
                continue

            used_indexes.append(idx.index_id)
            positions = idx.lookup(predicate.value)
            if idx.precise:
                results.extend(chunk.entries[p] for p in positions)
            else:
                results.extend(_post_filter(chunk, positions, predicate))

        return results, scanned, used_indexes


def _chunk_in_range(chunk: Chunk, time_range: tuple[float, float] | None) -> bool:
    if time_range is None:
        return True
    lo, hi = time_range
    return not (chunk.header.ts_max < lo or chunk.header.ts_min > hi)


def _post_filter(
    chunk: Chunk,
    positions: list[int],
    predicate: Predicate,
) -> list[LogEntry]:
    """Filter index-returned candidate positions through exact predicate match."""
    match = make_matcher(predicate)
    return [chunk.entries[pos] for pos in positions if match(chunk.entries[pos])]

def _pick_index(chunk: Chunk, predicate: Predicate):
    """Simple strategy: first index for the requested field with a compatible op."""
    for idx in chunk.indexes.values():
        if idx.field != predicate.field:
            continue
        if idx.op == predicate.op:
            return idx
        # Bloom (op=IN) can answer EQ predicates as a per-chunk gate.
        if predicate.op == PredicateOp.EQ and idx.op == PredicateOp.IN:
            return idx
    return None
