from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

ChunkId = str
IndexId = str


class ChunkState(Enum):
    OPEN = "open"
    SEALED = "sealed"
    PERSISTED = "persisted"


class IndexState(Enum):
    NOT_BUILD = "not_built"
    BUILDING = "building"
    ACTIVE = "active"
    DROPPED = "dropped"


class IndexType(Enum):
    HASH = "hash"
    SKIP = "skip"
    BLOOM = "bloom"


class PredicateOp(Enum):
    EQ = "="
    IN = "in"
    EXISTS = "exists"
    RANGE = "range"


@dataclass(frozen=True)
class LogEntry:
    ts: float
    service: str
    level: str
    msg: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Predicate:
    field: str
    op: PredicateOp
    value: Any = None

    def key(self) -> bytes:
        return f"{self.field}|{self.op.value}".encode()


class Tier(Enum):
    HOT = "hot"
    COLD = "cold"
