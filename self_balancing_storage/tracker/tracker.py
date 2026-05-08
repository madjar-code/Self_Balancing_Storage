from __future__ import annotations
import time
import psutil
from dataclasses import dataclass, field

from ..config import Config
from ..types import ChunkId, IndexId, Predicate
from .heatmap import ChunkHeatmap
from .primitives import (
    BurstDetector,
    CountMinSketch,
    MisraGries,
    SlidingCounter,
)


@dataclass(frozen=True)
class WriteEvent:
    ts: float
    n_entries: int
    n_bytes: int
    chunk_id: ChunkId | None = None


@dataclass(frozen=True)
class QueryEvent:
    ts: float
    predicates: list[Predicate]
    chunks_scanned: list[ChunkId]
    indexes_used: list[IndexId] = field(default_factory=list)
    duration_ms: float = 0.0
    rows_returned: int = 0


class AccessTracker:
    def __init__(self, config: Config):
        self.config = config
        self._write_counter = SlidingCounter(window_sec=config.write_window_sec)
        self._burst = BurstDetector()
        self._cms = CountMinSketch(d=config.cms_d, w=config.cms_w)
        self._topk = MisraGries(k=config.topk_k)
        self._heatmap = ChunkHeatmap(alpha=config.ema_alpha_chunk_temp)
        self._index_usage: dict[IndexId, int] = {}
        self._index_last_used: dict[IndexId, float] = {}
        self._process = psutil.Process()

    # === events ===
    def on_write(self, event: WriteEvent) -> None:
        self._write_counter.increment(event.ts, by=event.n_entries)
        rate = self._write_counter.value(event.ts) / max(self.config.write_window_sec, 1)
        self._burst.update(rate)

    def on_query(self, event: QueryEvent) -> None:
        for p in event.predicates:
            self._cms.increment(p.key())
            self._topk.add(p)
        for cid in event.chunks_scanned:
            self._heatmap.record_access(cid, event.ts)
        for iid in event.indexes_used:
            self._index_usage[iid] = self._index_usage.get(iid, 0) + 1
            self._index_last_used[iid] = event.ts

    def on_index_use(self, index_id: IndexId, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        self._index_usage[index_id] = self._index_usage.get(index_id, 0) + 1
        self._index_last_used[index_id] = now

    def on_index_built(self, index_id: IndexId, now: float | None = None) -> None:
        # Start the idle clock at creation time so a freshly-built index
        # isn't immediately seen as idle=inf by should_drop_index.
        # Does NOT count as usage (would distort ROI for never-queried indexes).
        self._index_last_used[index_id] = now if now is not None else time.time()

    # === metrics for Engine ===

    def write_rate(self) -> float:
        return self._write_counter.value() / max(self.config.write_window_sec, 1)

    def burst_ratio(self) -> float:
        return self._burst.burst_ratio

    def is_burst(self) -> bool:
        return self.burst_ratio() > self.config.burst_enter

    def top_predicates(self, k: int = 20) -> list[tuple[Predicate, int]]:
        return self._topk.top()[:k]

    def predicate_frequency(self, p: Predicate) -> int:
        return self._cms.estimate(p.key())

    def chunk_temperature(self, chunk_id: ChunkId) -> float:
        return self._heatmap.temperature(chunk_id)

    def hottest_chunks(self, n: int) -> list[ChunkId]:
        return self._heatmap.hottest(n)

    def cold_chunks(self, since: float) -> list[ChunkId]:
        return self._heatmap.cold_chunks(since)

    def index_usage(self, index_id: IndexId) -> int:
        return self._index_usage.get(index_id, 0)

    def index_last_used(self, index_id: IndexId) -> float | None:
        return self._index_last_used.get(index_id)

    def memory_pressure(self) -> float:
        rss = self._process.memory_info().rss
        return min(1.0, rss / max(self.config.max_memory_bytes, 1))

    def cool_down_chunks(self, chunk_ids: list[ChunkId]) -> None:
        """Called by the Engine every N ticks."""
        self._heatmap.cool_down(chunk_ids)

    def forget_chunk(self, chunk_id: ChunkId) -> None:
        self._heatmap.remove(chunk_id)

    def chunk_last_access(self) -> dict[ChunkId, float]:
        return self._heatmap.last_access_snapshot()
