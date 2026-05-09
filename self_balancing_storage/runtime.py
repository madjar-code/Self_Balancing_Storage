from __future__ import annotations
import asyncio
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator

from .config import Config
from .engine.engine import DecisionEngine
from .observability.event_broker import EventBroker
from .persistence.chunk_reader import ChunkReader
from .persistence.chunk_writer import ChunkPersistence
from .persistence.recovery import RecoveryManager
from .persistence.wal import WAL
from .store import ChunkStore
from .tracker.tracker import AccessTracker, QueryEvent, WriteEvent
from .types import ChunkId, LogEntry, Predicate


class Runtime:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self._stop_event = asyncio.Event()

        # Event broker — created here, not in start(), since it has no startup work.
        # Engine and Persistence may publish events during their operation.
        self.event_broker = EventBroker()

        # Persistence layer
        self.wal = WAL(self.config.wal_path, self.config.wal_fsync_interval_ms)
        self.persistence = ChunkPersistence(
            cold_path=self.config.cold_path,
            on_chunk_persisted=self._on_chunk_persisted,
        )
        self.reader = ChunkReader(self.config.cold_path)

        # Core components
        self.tracker = AccessTracker(self.config)
        self.store = ChunkStore(
            config=self.config,
            on_chunk_sealed=self._on_chunk_sealed,
        )
        self.engine = DecisionEngine(
            self.tracker,
            self.store,
            self.config,
            event_broker=self.event_broker,
            reader=self.reader,
        )

        # Ingest queue + tasks
        self.queue: asyncio.Queue[LogEntry] = asyncio.Queue(
            maxsize=self.config.ingest_queue_size,
        )
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        # Start WAL
        await self.wal.start()

        # Recovery
        recovery = RecoveryManager(self.store, self.wal, self.reader)
        await recovery.recover()

        # Background tasks
        self._tasks = [
            asyncio.create_task(self._consumer_loop()),
            asyncio.create_task(self._metric_tick_loop()),
            asyncio.create_task(self.engine.run()),
        ]

    async def stop(self) -> None:
        self._stop_event.set()
        await self.engine.stop()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Wait for any in-flight seal/persist tasks to finish so their
        # data lands on disk before we stop the WAL.
        if self.store._pending_seal_tasks:
            await asyncio.gather(
                *list(self.store._pending_seal_tasks),
                return_exceptions=True,
            )

        # Drain open chunk so its entries land on disk before WAL stops.
        if self.store.chunks:
            last = self.store.chunks[-1]
            if last.header.state.value == "open" and last.entries:
                last.seal()
                await self.persistence.persist_chunk(last)

        await self.wal.stop()

    async def try_append(self, entry: LogEntry) -> bool:
        try:
            self.queue.put_nowait(entry)
            return True
        except asyncio.QueueFull:
            return False

    def append(self, entry: LogEntry) -> None:
        """Sync direct path for tests/demos — bypasses ingest queue and WAL."""
        self.store.append(entry)
        self.tracker.on_write(WriteEvent(
            ts=entry.ts,
            n_entries=1,
            n_bytes=64,
            chunk_id=self.store.chunks[-1].header.chunk_id if self.store.chunks else None,
        ))

    async def find(self, query, time_range=None) -> list[LogEntry]:
        from .query.parser import parse
        from .query.ast import Query
        from .query.planner import plan_query
        from .query.executor import execute as exec_plan

        if isinstance(query, str):
            q = parse(query)
            if time_range is not None:
                q = Query(
                    where=q.where,
                    limit=q.limit,
                    time_range=time_range,
                    order_by=q.order_by,
                )
        elif isinstance(query, Predicate):
            q = Query(where=query, time_range=time_range)
        else:
            q = query

        plan = plan_query(q, self.store)
        t0 = time.time()
        results, scanned, used = await exec_plan(plan, self.store, reader=self.reader)
        duration_ms = (time.time() - t0) * 1000

        self.tracker.on_query(QueryEvent(
            ts=time.time(),
            predicates=_extract_predicates(q.where),
            chunks_scanned=scanned,
            indexes_used=used,
            duration_ms=duration_ms,
            rows_returned=len(results),
        ))
        return results

    async def _consumer_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                entry = await asyncio.wait_for(self.queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            await self.wal.append(entry)
            self.store.append(entry)
            self.tracker.on_write(WriteEvent(
                ts=entry.ts,
                n_entries=1,
                n_bytes=64,
                chunk_id=self.store.chunks[-1].header.chunk_id if self.store.chunks else None,
            ))

    async def _metric_tick_loop(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(self.config.metric_tick_interval_sec)
            self.event_broker.publish({
                "type": "metric_tick",
                "ts": time.time(),
                "write_rate": self.tracker.write_rate(),
                "burst_ratio": self.tracker.burst_ratio(),
                "memory_pressure": self.tracker.memory_pressure(),
                "n_chunks": len(self.store.chunks),
                "n_sealed": sum(1 for c in self.store.chunks if c.header.state.value == "sealed"),
                "n_indexed": sum(1 for c in self.store.chunks if c.indexes),
            })

    async def _on_chunk_sealed(self, chunk_id: ChunkId) -> None:
        chunk = self._find_chunk(chunk_id)
        if chunk is None:
            return
        await self.persistence.persist_chunk(chunk)
        self.event_broker.publish({
            "type": "chunk_sealed", "ts": time.time(), "chunk_id": chunk_id,
        })

    async def _on_chunk_persisted(self, chunk_id: ChunkId) -> None:
        # Compact the WAL: drop everything that is now safely on disk,
        # but keep entries belonging to the currently-open chunk so a
        # crash before its seal does not lose them.
        keep = list(self.store._open_chunk.entries) if self.store._open_chunk else []
        await self.wal.compact(keep)
        self.event_broker.publish({
            "type": "chunk_persisted", "ts": time.time(), "chunk_id": chunk_id,
        })

    def _find_chunk(self, chunk_id: ChunkId):
        for c in self.store.chunks:
            if c.header.chunk_id == chunk_id:
                return c
        return None


@asynccontextmanager
async def runtime(config: Config | None = None) -> AsyncIterator[Runtime]:
    rt = Runtime(config)
    await rt.start()
    try:
        yield rt
    finally:
        await rt.stop()


def _extract_predicates(expr) -> list[Predicate]:
    from .query.ast import And, Or, Not
    if isinstance(expr, Predicate):
        return [expr]
    if isinstance(expr, (And, Or)):
        out = []
        for p in expr.parts:
            out.extend(_extract_predicates(p))
        return out
    if isinstance(expr, Not):
        return _extract_predicates(expr.expr)
    return []
