from __future__ import annotations
import asyncio
import logging
import time
from typing import TYPE_CHECKING

from ..config import Config
from ..indexes.base import make_index_id
from ..indexes.bloom import BloomIndex
from ..indexes.hash_index import HashIndex
from ..indexes.skip_index import SkipIndex
from ..types import ChunkId, IndexId, IndexType
from .actions import (
    Action,
    BuildIndexAction,
    DropIndexAction,
    DroppedIndex,
    RestoreIndexAction,
)
from .decisions import (
    IndexInfo,
    TrackerView,
    choose_index_type,
    is_dropped_expired,
    plan_memory_relief,
    should_build_index,
    should_drop_index,
    should_restore_dropped_index,
)
from .stability import StabilityCounter

if TYPE_CHECKING:
    from ..store import ChunkStore
    from ..tracker.tracker import AccessTracker

logger = logging.getLogger("decision_engine")


class DecisionEngine:
    def __init__(
        self,
        tracker: "AccessTracker",
        store: "ChunkStore",
        config: Config,
    ):
        self.tracker = tracker
        self.store = store
        self.config = config
        self._stop_event = asyncio.Event()

        self.in_burst = False
        self.burst_stability = StabilityCounter(n=config.burst_stability_n)
        self.deferred_index_queue: list[BuildIndexAction] = []
        self.dropped_indexes: dict[IndexId, DroppedIndex] = {}

    async def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("tick failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.config.tick_interval_sec,
                )
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop_event.set()

    async def _tick(self) -> None:
        view = self._make_tracker_view()
        actions: list[Action] = []

        # 1. Memory relief - highest priority
        index_infos = self._collect_index_infos()
        actions.extend(plan_memory_relief(view, index_infos, self.config))

        # 2. Burst mode update
        burst_now = view.burst_ratio > self.config.burst_enter
        if not self.in_burst and self.burst_stability.observe(burst_now):
            self.in_burst = True
            logger.info("burst_mode_enter", ...)
        elif self.in_burst and view.burst_ratio < self.config.burst_exit:
            self.in_burst = False
            self.burst_stability.reset()

        # 3. Plan drops and if not in burst - plan builds, restores
        if not self.in_burst:
            actions.extend(self._plan_index_restores(view))
            actions.extend(self._plan_index_builds(view))
        actions.extend(self._plan_index_drops(view, index_infos))

        # 4. Cleanup expider dropped
        self._expire_dropped(view.now)

        # 5. Sort by priority and apply within budget
        actions.sort(key=lambda a: getattr(a, "priority", 99))
        budget = self.config.actions_per_tick_budget
        builds_count = 0
        for action in actions:
            if builds_count >= self.config.builds_per_tick and isinstance(action, (BuildIndexAction, RestoreIndexAction)):
                continue
            if budget <= 0:
                break
            try:
                await self._apply(action)
                if isinstance(action, (BuildIndexAction, RestoreIndexAction)):
                    builds_count += 1
                budget -= 1
            except Exception:
                logger.exception("action_failed", extra={"action": str(action)})

    def _make_tracker_view(self) -> TrackerView:
        now = time.time()
        top_preds = self.tracker.top_predicates(self.config.topk_k)
        pred_freqs = {p: f for p, f in top_preds}

        chunk_temps = {
            c.header.chunk_id: self.tracker.chunk_temperature(c.header.chunk_id)
            for c in self.store.chunks
        }

        # Collect usage / last_used for all known indexes
        usage: dict[IndexId, int] = {}
        last_used: dict[IndexId, float] = {}
        for c in self.store.chunks:
            for iid in c.indexes:
                usage[iid] = self.tracker.index_usage(iid)
                lu = self.tracker.index_last_used(iid)
                if lu is not None:
                    last_used[iid] = lu

        return TrackerView(
            now=now,
            write_rate=self.tracker.write_rate(),
            burst_ratio=self.tracker.burst_ratio(),
            is_burst=self.tracker.is_burst(),
            predicate_freqs=pred_freqs,
            chunk_temperatures=chunk_temps,
            index_usage=usage,
            index_last_used=last_used,
            memory_pressure=self.tracker.memory_pressure(),
            top_predicates=top_preds,
        )

    def _collect_index_infos(self) -> list[IndexInfo]:
        infos: list[IndexInfo] = []
        for chunk in self.store.chunks:
            for iid, idx in chunk.indexes.items():
                infos.append(
                    IndexInfo(
                        index_id=iid,
                        chunk_id=chunk.header.chunk_id,
                        field=idx.field,
                        op=idx.op,
                        index_type=_index_type_of(idx),
                        memory_bytes=idx.memory_bytes,
                    )
                )
        return infos

    def _plan_index_restores(self, view: TrackerView) -> list[RestoreIndexAction]:
        actions: list[RestoreIndexAction] = []
        for dropped in list(self.dropped_indexes.values()):
            if should_restore_dropped_index(dropped, view, self.config):
                actions.append(
                    RestoreIndexAction(
                        chunk_id=dropped.chunk_id,
                        field=dropped.field,
                        op=dropped.op,
                        index_type=dropped.index_type,
                    )
                )
        return actions

    def _plan_index_builds(self, view: TrackerView) -> list[BuildIndexAction]:
        actions: list[BuildIndexAction] = []
        for chunk in self.store.chunks:
            if chunk.header.state.value != "sealed":
                continue
            for predicate, _freq in view.top_predicates:
                idx_type = choose_index_type(predicate, chunk.header.schema_sketch)
                iid = make_index_id(chunk.header.chunk_id, idx_type, predicate.field)
                if iid in chunk.indexes:
                    continue
                if iid in self.dropped_indexes:
                    continue
                if should_build_index(chunk, predicate, view, self.config):
                    actions.append(
                        BuildIndexAction(
                            chunk_id=chunk.header.chunk_id,
                            field=predicate.field,
                            op=predicate.op,
                            index_type=idx_type,
                        )
                    )
        return actions

    def _plan_index_drops(
        self,
        view: TrackerView,
        infos: list[IndexInfo],
    ) -> list[DropIndexAction]:
        return [
            DropIndexAction(index_id=info.index_id)
            for info in infos
            if should_drop_index(info, view, self.config)
        ]

    def _expire_dropped(self, now: float) -> None:
        expired = [
            iid for iid, d in self.dropped_indexes.items()
            if is_dropped_expired(d, now, self.config.cooldown_sec)
        ]
        for iid in expired:
            del self.dropped_indexes[iid]
            logger.info(
                "dropped_expired",
                extra={
                    "event": "dropped_expired",
                    "index_id": iid
                }
            )

    async def _apply(self, action: Action) -> None:
        if isinstance(action, BuildIndexAction):
            await self._apply_build(action)
        elif isinstance(action, DropIndexAction):
            await self._apply_drop(action)
        elif isinstance(action, RestoreIndexAction):
            await self._apply_restore(action)

    async def _apply_build(self, action: BuildIndexAction) -> None:
        chunk = self._find_chunk(action.chunk_id)
        if chunk is None:
            return
        idx = _make_index(
            chunk,
            action.field,
            action.index_type,
            self.config
        )
        idx.build(chunk.entries)
        chunk.indexes[idx.index_id] = idx
        logger.info(
            "decision",
            extra={
                "event": "decision",
                "type": "build_index",
                "chunk_id": action.chunk_id,
                "field": action.field,
                "index_type": action.index_type.value,
                "applied": True,
            },
        )

    async def _apply_drop(self, action: DropIndexAction) -> None:
        for chunk in self.store.chunks:
            if action.index_id in chunk.indexes:
                idx = chunk.indexes.pop(action.index_id)
                self.dropped_indexes[action.index_id] = DroppedIndex(
                    index_id=action.index_id,
                    chunk_id=chunk.header.chunk_id,
                    field=idx.field,
                    op=idx.op,
                    index_type=_index_type_of(idx),
                    dropped_at=time.time(),
                    prior_usage=self.tracker.index_usage(action.index_id),
                )
                logger.info(
                    "decision",
                    extra={
                        "event": "decision",
                        "type": "drop_index",
                        "index_id": action.index_id,
                    },
                )
                return

    async def _apply_restore(self, action: RestoreIndexAction) -> None:
        chunk = self._find_chunk(action.chunk_id)
        if chunk is None:
            return
        idx = _make_index(chunk, action.field, action.index_type, self.config)
        idx.build(chunk.entries)
        chunk.indexes[idx.index_id] = idx
        self.dropped_indexes.pop(idx.index_id, None)
        logger.info(
            "decision",
            extra={
                "event": "decision",
                "type": "restore_index",
                "chunk_id": action.chunk_id,
                "field": action.field,
            },
        )

    def _find_chunk(self, chunk_id: ChunkId):
        for c in self.store.chunks:
            if c.header.chunk_id == chunk_id:
                return c
        return None


def _index_type_of(idx) -> IndexType:
    from ..indexes.bloom import BloomIndex
    from ..indexes.hash_index import HashIndex
    from ..indexes.skip_index import SkipIndex

    if isinstance(idx, HashIndex):
        return IndexType.HASH
    if isinstance(idx, SkipIndex):
        return IndexType.SKIP
    if isinstance(idx, BloomIndex):
        return IndexType.BLOOM
    raise ValueError(f"unknown index class: {type(idx).__name__}")


def _make_index(chunk, field: str, index_type: IndexType, config: Config):
    chunk_id = chunk.header.chunk_id

    if index_type == IndexType.HASH:
        return HashIndex(
            chunk_id=chunk_id,
            field=field
        )
    if index_type == IndexType.SKIP:
        return SkipIndex(
            chunk_id=chunk_id,
            block_size=config.skip_block_size
        )
    if index_type == IndexType.BLOOM:
        return BloomIndex(
            chunk_id=chunk_id,
            field=field,
            n_items=max(chunk.header.count, 1),
            fp_rate=config.bloom_fp_rate,
        )
    raise ValueError(f"unknown index type: {index_type}")
