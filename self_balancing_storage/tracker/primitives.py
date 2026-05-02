from __future__ import annotations
import math
from collections import defaultdict
from typing import Any

import mmh3


class EMA:
    def __init__(self, alpha: float):
        if not 0 < alpha <= 1:
            raise ValueError("alpha must be in (0, 1]")
        self.alpha = alpha
        self.value: float | None = None

    def update(self, x: float) -> None:
        if self.value is None:
            self.value = x
        else:
            self.value = self.alpha * x + (1 - self.alpha) * self.value

    def get(self, default: float = 0.0) -> float:
        return self.value if self.value is not None else default


class SlidingCounter:
    """Bucketed sliding window counter."""

    def __init__(self, window_sec: int, n_buckets: int = 60):
        self.window_sec = window_sec
        self.bucket_sec = window_sec / n_buckets

        # each bucket: (start_ts, count)
        self._buckets: list[list[float | int]] = []  # [[start, count], ...]

    def increment(self, now: float, by: int = 1) -> None:
        bucket_start = math.floor(now / self.bucket_sec) * self.bucket_sec
        if self._buckets and self._buckets[-1][0] == bucket_start:
            self._buckets[-1][1] += by
        else:
            self._buckets.append([bucket_start, by])
        cutoff = now - self.window_sec
        # evict stale buckets
        while self._buckets and self._buckets[0][0] < cutoff:
            self._buckets.pop(0)

    def value(self, now: float | None = None) -> int:
        if now is not None:
            cutoff = now - self.window_sec
            return sum(int(b[1]) for b in self._buckets if b[0] >= cutoff)
        return sum(int(b[1]) for b in self._buckets)


class BurstDetector:
    def __init__(self, alpha_short: float = 0.5, alpha_long: float = 0.05):
        self.short = EMA(alpha=alpha_short)
        self.long = EMA(alpha=alpha_long)

    def update(self, rate: float) -> None:
        self.short.update(rate)
        self.long.update(rate)

    @property
    def burst_ratio(self) -> float:
        long_v = self.long.value
        short_v = self.short.value
        if long_v is None or long_v <= 0 or short_v is None:
            return 1.0
        return short_v / long_v


class CountMinSketch:
    def __init__(self, d: int = 5, w: int = 1024):
        self.d = d
        self.w = w
        self._table: list[list[int]] = [[0] * w for _ in range (d)]

    def _positions(self, key: bytes) -> list[int]:
        h1 = mmh3.hash(key, signed=False, seed=0x12345)
        h2 = mmh3.hash(key, signed=False, seed=0x67890)
        return [(h1 + i * h2) % self.w for i in range(self.d)]

    def increment(self, key: bytes, by: int = 1) -> None:
        for i, pos in enumerate(self._positions(key)):
            self._table[i][pos] += by

    def estimate(self, key: bytes) -> int:
        return min(self._table[i][pos] for i, pos in enumerate(self._positions(key)))


class MisraGries:
    """
    Heavy hitters approximation. Guarantees that elements
    with frequency > N/k will appear in the result.
    """

    def __init__(self, k: int = 20):
        self.k = k
        self._counters: dict[Any, int] = {}

    def add(self, key: Any) -> None:
        if key in self._counters:
            self._counters[key] += 1
        elif len(self._counters) < self.k:
            self._counters[key] = 1
        else:
            # all slots taken — decrement all, remove zero-counters
            to_delete = []
            for k in self._counters:
                self._counters[k] -= 1
                if self._counters[k] == 0:
                    to_delete.append(k)
            for k in to_delete:
                del self._counters[k]

    def top(self) -> list[tuple[Any, int]]:
        return sorted(self._counters.items(), key=lambda kv: -kv[1])

    def estimate(self, key: Any) -> int:
        return self._counters.get(key, 0)