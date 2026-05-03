from __future__ import annotations
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from .config import Config
from .engine.engine import DecisionEngine
from .store import ChunkStore
from .tracker.tracker import AccessTracker, QueryEvent, WriteEvent
from .types import LogEntry, Predicate

logger = logging.getLogger("runtime")


class Runtime:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.tracker = AccessTracker(self.config)
        self.store = ChunkStore(self.config)
        self.engine = DecisionEngine(self.tracker, self.store, self.config)
        self._engine_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._engine_task = asyncio.create_task(self.engine.run())

    async def stop(self) -> None:
        await self.engine.stop()
        if self._engine_task is not None:
            await self._engine_task

    # public API

    def append(self, entry: LogEntry) -> None:
        self.store.append(entry)
        self.tracker.on_write(
            WriteEvent(
                ts=entry.ts,
                n_entries=1,
                n_bytes=64,  # rough
                chunk_id=self.store.chunks[-1].header.chunk_id if self.store.chunks else None,
            )
        )

    def find(
        self,
        predicate: Predicate,
        time_range: tuple[float, float] | None = None,
    ) -> list[LogEntry]:
        t0 = time.time()
        results, scanned, used = self.store.find(predicate, time_range)
        dt = (time.time() - t0) * 1000
        self.tracker.on_query(
            QueryEvent(
                ts=time.time(),
                predicates=[predicate],
                chunks_scanned=scanned,
                indexes_used=used,
                duration_ms=dt,
                rows_returned=len(results),
            )
        )
        return results


@asynccontextmanager
async def runtime(config: Config | None = None) -> AsyncIterator[Runtime]:
    rt = Runtime(config)
    await rt.start()
    try:
        yield rt
    finally:
        await rt.stop()
