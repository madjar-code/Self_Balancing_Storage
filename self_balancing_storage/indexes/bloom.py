from __future__ import annotations
import math
import sys
from typing import Any

import mmh3
from bitarray import bitarray

from ..chunk import _extract_field
from ..types import ChunkId, IndexType, LogEntry, PredicateOp
from .base import make_index_id


class BloomFilter:
    precise = False

    def __init__(self, n_items: int, fp_rate: float = 0.01):
        if n_items <= 0:
            n_items = 1
        # m = -n * ln(p) / (ln 2)^2
        m = int(-n_items * math.log(fp_rate) / (math.log(2) ** 2))
        m = max(m, 64)  # minimum to avoid a 0-bit filter
        # k = (m / n) * ln 2
        k = max(1, int((m / n_items) * math.log(2)))
        self.m = m
        self.k = k
        self.bits = bitarray(m)
        self.bits.setall(False)

    def _positions(self, value: bytes) -> list[int]:
        # Double hashing: h_i = (h1 + i * h2) mod m
        h1 = mmh3.hash(value, signed=False, seed=0x12345)
        h2 = mmh3.hash(value, signed=False, seed=0x67890)
        return [(h1 + i * h2) % self.m for i in range(self.k)]

    def add(self, value: bytes) -> None:
        for pos in self._positions(value):
            self.bits[pos] = True

    def __contains__(self, value: bytes) -> bool:
        return all(self.bits[pos] for pos in self._positions(value))

    @property
    def memory_bytes(self) -> int:
        return self.m // 8 + 64  # bitarray + overhead


def _to_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")


class BloomIndex:
    precise = False

    def __init__(
        self,
        chunk_id: ChunkId,
        field: str,
        n_items: int,
        fp_rate: float = 0.01,
    ):
        self.chunk_id = chunk_id
        self.field = field
        self.op = PredicateOp.IN
        self.index_id = make_index_id(chunk_id, IndexType.BLOOM, field)
        self._filter = BloomFilter(n_items=n_items, fp_rate=fp_rate)
        self._chunk_count = n_items

    def build(self, entries: list[LogEntry]) -> None:
        self._chunk_count = len(entries)
        for entry in entries:
            value = _extract_field(entry, self.field)
            if value is None:
                continue
            self._filter.add(_to_bytes(value))

    def lookup(self, value: Any) -> list[int]:
        if _to_bytes(value) in self._filter:
            # Bloom does not return positions — return the whole chunk; query layer post-filters
            return list(range(self._chunk_count))
        return []

    @property
    def memory_bytes(self) -> int:
        return self._filter.memory_bytes + sys.getsizeof(self.field)
