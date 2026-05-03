from __future__ import annotations
from typing import Any, Protocol, runtime_checkable

from ..types import ChunkId, IndexId, IndexType, PredicateOp


def make_index_id(chunk_id: ChunkId, index_type: IndexType, field: str) -> IndexId:
    return f"{chunk_id}:{index_type.value}:{field}"


@runtime_checkable
class Index(Protocol):
    index_id: IndexId
    chunk_id: ChunkId
    field: str
    op: PredicateOp
    precise: bool

    @property
    def memory_bytes(self) -> int: ...

    def build(self, entries: list[Any]) -> None: ...

    def lookup(self, value: Any) -> list[int]: ...
