from __future__ import annotations
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .types import (
    ChunkId,
    ChunkState,
    IndexId,
    LogEntry,
    Predicate,
    PredicateOp,
)

if TYPE_CHECKING:
    from .indexes.base import Index


@dataclass
class ChunkHeader:
    chunk_id: ChunkId
    seq_id: int
    ts_min: float
    ts_max: float
    services: set[str] = field(default_factory=set)
    count: int = 0
    size_bytes: int = 0
    schema_sketch: dict[str, set[type]] = field(default_factory=dict)
    state: ChunkState = ChunkState.OPEN


def _entry_size(entry: LogEntry) -> int:
    """Rough estimate of entry size in bytes."""
    return (
        sys.getsizeof(entry.service)
        + sys.getsizeof(entry.level)
        + sys.getsizeof(entry.msg)
        + sys.getsizeof(entry.fields)
        + 32  # fixed overhead for ts + bookkeeping
    )


@dataclass
class Chunk:
    header: ChunkHeader
    entries: list[LogEntry] = field(default_factory=list)
    indexes: dict[IndexId, "Index"] = field(default_factory=dict)

    @classmethod
    def new(cls, seq: int, now: float | None = None) -> Chunk:
        now = now if now is not None else time.time()
        chunk_id = f"chunk_{seq:06d}_{int(now * 1000)}"
        return cls(
            header=ChunkHeader(
                chunk_id=chunk_id,
                seq=seq,
                ts_min=now,
                ts_max=now,
            ),
        )

    def append(self, entry: LogEntry) -> None:
        if self.header.state != ChunkState.OPEN:
            raise RuntimeError(f"cannot append to chunk in state {self.header.state}")
        if self.header.count == 0:
            self.header.ts_min = entry.ts

        self.header.ts_max = max(self.header.ts_max, entry.ts)
        self.header.services.add(entry.service)
        self.header.count += 1
        self.header.size_bytes += _entry_size(entry)
        self.entries.append(entry)

    def seal(self) -> None:
        if self.header.state != ChunkState.OPEN:
            return
        self.header.state = ChunkState.SEALED
        self.header.schema_sketch = self._build_schema_sketch()

    def _build_schema_sketch(self) -> dict[str, set[type]]:
        sketch: dict[str, set[type]] = {
            "ts": {float},
            "service": {str},
            "level": {str},
            "msg": {str},
        }
        for entry in self.entries:
            for k, v in entry.fields.items():
                sketch.setdefault(k, set()).add(type(v))
        return sketch

    def scan(self, predicate: Predicate) -> list[int]:
        """Full scan, return positions (indices into self.entries)."""
        result: list[int] = []
        for i, entry in enumerate(self.entries):
            if self._matches(entry, predicate):
                result.append(i)
        return result

    @staticmethod
    def _matches(entry: LogEntry, p: Predicate) -> bool:
        value = _extract_field(entry, p.field)
        if p.op == PredicateOp.EQ:
            return value == p.value
        if p.op == PredicateOp.IN:
            return value in p.value
        if p.op == PredicateOp.RANGE:
            lo, hi = p.value
            return value is not None and lo <= value <= hi
        if p.op == PredicateOp.EXISTS:
            return value is not None
        return False


def _extract_field(entry: LogEntry, name: str) -> Any:
    if name == "ts":
        return entry.ts
    if name == "service":
        return entry.service
    if name == "level":
        return entry.level
    if name == "msg":
        return entry.msg
    return entry.fields.get(name)
