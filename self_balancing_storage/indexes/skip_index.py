from __future__ import annotations
import sys
from typing import Any

from ..types import ChunkId, IndexId, IndexType, LogEntry, PredicateOp
from .base import make_index_id


class SkipIndex:
    """Min/max skip index, specialized for the `ts` field."""

    def __init__(self, chunk_id: ChunkId, block_size: int = 100):
        self.chunk_id = chunk_id
        self.field = "ts"
        self.op = PredicateOp.RANGE
        self.index_id: IndexId = make_index_id(chunk_id, IndexType.SKIP, "ts")
        self.block_size = block_size

        # each block: (ts_min, ts_max, pos_start, pos_end)
        self._blocks: list[tuple[float, float, int, int]] = []

        # for binary search by block start
        self._block_starts: list[float] = []

    def build(self, entries: list[LogEntry]) -> None:
        self._blocks.clear()
        self._block_starts.clear()

        n = len(entries)
        if n == 0:
            return

        for start in range(0, n, self.block_size):
            end = min(start + self.block_size, n)
            block_entries = entries[start:end]
            ts_values = [e.ts for e in block_entries]
            self._blocks.append((min(ts_values), max(ts_values), start, end))
            self._block_starts.append(min(ts_values))

    def lookup(self, values: Any) -> list[int]:
        """value = (ts_lo + ts_hi)"""
        lo, hi = values

        # Pick all blocks whose [ts_min, ts_max] intersects with [lo, hi].
        # We need every block where ts_max >= lo and ts_min <= hi.
        # Linear scan for simplicity (blocks are usually few).

        positions: list[int] = []
        for ts_min, ts_max, start, end in self._blocks:
            if ts_max < lo:
                continue
            if ts_min > hi:
                break
            positions.extend(range(start, end))
        return positions

    @property
    def memory_bytes(self) -> int:
        return sys.getsizeof(self._blocks) + len(self._blocks) * 56
