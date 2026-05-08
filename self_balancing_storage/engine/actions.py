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


# === V2 NEW ===
@dataclass(frozen=True)
class DemoteChunkAction:
    chunk_id: ChunkId
    priority: int = 20


@dataclass(frozen=True)
class PromoteChunkAction:
    chunk_id: ChunkId
    priority: int = 25


@dataclass(frozen=True)
class EvictHeavyIndexAction:
    index_id: IndexId
    priority: int = 15


Action = (
    BuildIndexAction
    | DropIndexAction
    | RestoreIndexAction
    | DemoteChunkAction
    | PromoteChunkAction
    | EvictHeavyIndexAction
)


@dataclass
class DroppedIndex:
    index_id: IndexId
    chunk_id: ChunkId
    field: str
    op: PredicateOp
    index_type: IndexType
    dropped_at: float
    prior_usage: int
