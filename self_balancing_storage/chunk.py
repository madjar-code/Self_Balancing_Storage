from __future__ import annotations
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .types import (
    ChunkId,
    ChunkState,
    IndexId,
    LogEntry,
    Predicate,
    PredicateOp,
    Tier,
)

if TYPE_CHECKING:
    from .indexes.base import Index


@dataclass
class ChunkHeader:
    chunk_id: ChunkId
    seq: int
    ts_min: float
    ts_max: float
    services: set[str] = field(default_factory=set)
    count: int = 0
    size_bytes: int = 0
    schema_sketch: dict[str, set[type]] = field(default_factory=dict)
    state: ChunkState = ChunkState.OPEN
    indexes_on_disk: list[IndexId] = field(default_factory=list)
    persisted_at: float | None = None


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
    tier: Tier = Tier.HOT

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
        match = make_matcher(predicate)
        return [i for i, e in enumerate(self.entries) if match(e)]

    @staticmethod
    def _matches(entry: LogEntry, p: Predicate) -> bool:
        return make_matcher(p)(entry)


_FIELD_GETTERS: dict[str, Any] = {
    "ts": lambda e: e.ts,
    "service": lambda e: e.service,
    "level": lambda e: e.level,
    "msg": lambda e: e.msg,
}


def _extract_field(entry: LogEntry, name: str) -> Any:
    getter = _FIELD_GETTERS.get(name)
    if getter is not None:
        return getter(entry)
    return entry.fields.get(name)


def make_matcher(predicate: Predicate):
    """
    Build a per-entry checker once, reuse it inside the scan loop.

    Avoids re-dispatching predicate.op and re-resolving the field accessor
    on every entry comparison.
    """
    field = predicate.field
    op = predicate.op
    value = predicate.value
    getter = _FIELD_GETTERS.get(field)

    if getter is None:
        getter = _make_fields_getter(field)

    if op == PredicateOp.EQ:
        return lambda e: getter(e) == value
    if op == PredicateOp.IN:
        bag = set(value) if isinstance(value, list) else value
        return lambda e: getter(e) in bag
    if op == PredicateOp.RANGE:
        lo, hi = value
        def _match_range(e: LogEntry) -> bool:
            v = getter(e)
            return v is not None and lo <= v <= hi
        return _match_range
    if op == PredicateOp.EXISTS:
        return lambda e: getter(e) is not None
    return lambda e: False


def _make_fields_getter(name: str):
    return lambda e: e.fields.get(name)
