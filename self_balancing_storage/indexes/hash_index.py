from __future__ import annotations
import sys
from collections import defaultdict
from typing import Any

from ..chunk import _extract_field
from ..types import ChunkId, IndexId, IndexType, LogEntry, PredicateOp
from .base import make_index_id


class HashIndex:
    def __init__(self, chunk_id: ChunkId, field: str):
        self.chunk_id = chunk_id
        self.field = field
        self.op = PredicateOp.EQ
        self.index_id: IndexId = make_index_id(chunk_id, IndexType.HASH, field)

        self._table: dict[str, list[int]] = defaultdict(list)

    def build(self, entries: list[LogEntry]) -> None:
        self._table.clear()
        for i, entry in enumerate(entries):
            value = _extract_field(entry, self.field)
            if value is None:
                continue
            self._table[value].append(i)

    def lookup(self, value: Any) -> list[int]:
        return list(self._table.get(value, ()))

    def lookup_many(self, values: list[Any]) -> list[int]:
        seen: set[int] = set()
        for v in values:
            for pos in self._table.get(v, ()):
                seen.add(pos)
        return sorted(seen)

    @property
    def memory_bytes(self) -> int:
        size = sys.getsizeof(self._table)
        for k, v in self._table.items():
            size += sys.getsizeof(k) + sys.getsizeof(v) + len(v) * 8
        return size
