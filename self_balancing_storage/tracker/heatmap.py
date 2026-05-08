from __future__ import annotations

from ..types import ChunkId
from .primitives import EMA


class ChunkHeatmap:
    def __init__(self, alpha: float = 0.1):
        self.alpha = alpha
        self._ema: dict[ChunkId, EMA] = {}
        self._last_access: dict[ChunkId, float] = {}

    def record_access(self, chunk_id: ChunkId, now: float) -> None:
        ema = self._ema.get(chunk_id)
        if ema is None:
            ema = EMA(alpha=self.alpha)
            self._ema[chunk_id] = ema
        ema.update(1.0)
        self._last_access[chunk_id] = now

    def cool_down(self, chunk_ids: list[ChunkId]) -> None:
        """
        Called from Engine's tick: update EMA with 0 for all
        chunks so that inactive ones actually cool down.
        """
        for cid in chunk_ids:
            ema = self._ema.get(cid)
            if ema is None:
                ema = EMA(alpha=self.alpha)
                self._ema[cid] = ema
            ema.update(0.0)

    def temperature(self, chunk_id: ChunkId) -> float:
        ema = self._ema.get(chunk_id)
        return ema.get(0.0) if ema is not None else 0.0

    def hottest(self, n: int) -> list[ChunkId]:
        items = sorted(self._ema, key=lambda c: -self.temperature(c))
        return items[:n]

    def cold_chunks(self, since: float) -> list[ChunkId]:
        return [cid for cid, last in self._last_access.items() if last < since]

    def remove(self, chunk_id: ChunkId) -> None:
        self._ema.pop(chunk_id, None)
        self._last_access.pop(chunk_id, None)

    def last_access_snapshot(self) -> dict[ChunkId, float]:
        return dict(self._last_access)
