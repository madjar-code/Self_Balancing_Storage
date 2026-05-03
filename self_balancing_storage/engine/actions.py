from __future__ import annotations
from dataclasses import dataclass

from ..types import (
    ChunkId,
    IndexId,
    IndexType,
    PredicateOp,
)


@dataclass(frozen=True)
class BuildIndexAction:
    chunk_id: ChunkId
    field: str
    op: PredicateOp
    index_type: IndexType
    priority: int = 30


@dataclass(frozen=True)
class DropIndexAction:
    index_id: IndexId
    priority: int = 50


@dataclass(frozen=True)
class RestoreIndexAction:
    chunk_id: ChunkId
    field: str
    op: PredicateOp
    index_type: IndexType
    priority: int = 30


Action = BuildIndexAction | DropIndexAction | RestoreIndexAction


@dataclass
class DroppedIndex:
    index_id: IndexId
    chunk_id: ChunkId
    field: str
    op: PredicateOp
    index_type: IndexType
    dropped_at: float
    prior_usage: int  # so fast restore doesn't have to "learn from scratch"
