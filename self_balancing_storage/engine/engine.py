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
from ..types import (
    Tier,
    ChunkId,
    IndexId,
    IndexType,
)
from .actions import (
    Action,
    BuildIndexAction,
    DropIndexAction,
    DroppedIndex,
    RestoreIndexAction,
    DemoteChunkAction,
    PromoteChunkAction,
    EvictHeavyIndexAction,
)
from .decisions import (
    IndexInfo,
    TrackerView,
    choose_index_type,
    compute_roi,
    is_dropped_expired,
    plan_memory_relief,
    should_build_index,
    should_demote_chunk,
    should_drop_index,
    should_promote_chunk,
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
        event_broker=None,
        reader=None,
    ):
        self.tracker = tracker
        self.store = store
        self.config = config
        self._stop_event = asyncio.Event()

        self.in_burst = False
        self.burst_stability = StabilityCounter(n=config.burst_stability_n)
        self.deferred_index_queue: list[BuildIndexAction] = []
        self.dropped_indexes: dict[IndexId, DroppedIndex] = {}
        self._tick_count = 0

        self.event_broker = event_broker
        self.reader = reader

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
        self._tick_count += 1

        # Decay temperatures of all chunks. Chunks that get queried in this
        # tick will have record_access bump temp back up; idle chunks decay.
        self.tracker.cool_down_chunks([c.header.chunk_id for c in self.store.chunks])

        # Periodic decay of accumulated counters (predicate frequencies and
        # per-index usage) so stale patterns lose influence over time.
        if (
            self.config.decay_every_n_ticks > 0
            and self._tick_count % self.config.decay_every_n_ticks == 0
        ):
            self.tracker.decay_counters(self.config.decay_factor)

        view = self._make_tracker_view()
        actions: list[Action] = []

        # 1. Memory relief - highest priority
        index_infos = self.collect_index_infos()
        actions.extend(
            plan_memory_relief(
                view,
                index_infos,
                list(self.store.chunks),
                self.config
            )
        )

        # 2. Burst mode update
        burst_now = view.burst_ratio > self.config.burst_enter
        if not self.in_burst and self.burst_stability.observe(burst_now):
            self.in_burst = True
            logger.info(
                "burst_mode_enter",
                extra={"event": "burst", "state": "enter", "ratio": view.burst_ratio},
            )
            self._publish_event({
                "type": "burst",
                "ts": time.time(),
                "state": "enter",
                "ratio": view.burst_ratio,
            })
        elif self.in_burst and view.burst_ratio < self.config.burst_exit:
            self.in_burst = False
            self.burst_stability.reset()
            logger.info(
                "burst_mode_exit",
                extra={"event": "burst", "state": "exit", "ratio": view.burst_ratio},
            )
            self._publish_event({
                "type": "burst",
                "ts": time.time(),
                "state": "exit",
                "ratio": view.burst_ratio,
            })

        # 3. Seed static indexes (independent of dynamic_indexing).
        if self.config.static_indexes:
            self._ensure_static_indexes()

        # 4. Plan drops and if not in burst - plan builds, restores, tier moves
        if not self.in_burst:
            if self.config.dynamic_indexing:
                actions.extend(self._plan_index_restores(view))
                actions.extend(self._plan_index_builds(view))
            if self.config.dynamic_tiering:
                actions.extend(self._plan_promotes(view))
            actions.extend(self._plan_demotes(view))
        if self.config.dynamic_indexing:
            actions.extend(self._plan_index_drops(view, index_infos))

        # 5. Cleanup expired dropped
        self._expire_dropped(view.now)

        # 6. Sort by priority and apply within budget
        actions.sort(key=lambda a: getattr(a, "priority", 99))
        budget = self.config.actions_per_tick_budget
        builds_count = 0
        applied: list[str] = []
        for action in actions:
            if builds_count >= self.config.builds_per_tick and isinstance(action, (BuildIndexAction, RestoreIndexAction)):
                continue
            if budget <= 0:
                break
            try:
                await self._apply(action)
                applied.append(type(action).__name__)
                if isinstance(action, (BuildIndexAction, RestoreIndexAction)):
                    builds_count += 1
                budget -= 1
            except Exception:
                logger.exception("action_failed", extra={"action": str(action)})

        self._log_tick_summary(view, actions, applied)

    def _log_tick_summary(
        self,
        view: TrackerView,
        planned: list[Action],
        applied: list[str],
    ) -> None:
        # DEBUG-level: useful for engine diagnostics; demo prints its own
        # compact snapshot at INFO via the runtime/demo layer.
        if not logger.isEnabledFor(logging.DEBUG):
            return
        n_sealed = sum(1 for c in self.store.chunks if c.header.state.value == "sealed")
        n_with_indexes = sum(1 for c in self.store.chunks if c.indexes)
        top = [
            (f"{p.field}|{p.op.value}={p.value!r}", f)
            for p, f in view.top_predicates[:3]
        ]
        max_temp = max(view.chunk_temperatures.values(), default=0.0)
        logger.debug(
            "tick",
            extra={
                "event": "tick",
                "write_rate": round(view.write_rate, 2),
                "burst_ratio": round(view.burst_ratio, 2),
                "is_burst": view.is_burst,
                "in_burst_state": self.in_burst,
                "mem_pressure": round(view.memory_pressure, 3),
                "n_chunks": len(self.store.chunks),
                "n_sealed": n_sealed,
                "n_with_indexes": n_with_indexes,
                "n_dropped": len(self.dropped_indexes),
                "max_chunk_temp": round(max_temp, 3),
                "top_preds": top,
                "planned": len(planned),
                "applied": applied,
            },
        )

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
            chunk_last_access=self.tracker.chunk_last_access(),
            top_predicates=top_preds,
            predicate_last_seen=self.tracker.predicate_last_seen_snapshot(),
        )

    def collect_index_infos(self) -> list[IndexInfo]:
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

    def _ensure_static_indexes(self) -> None:
        """
        Build any missing index from `config.static_indexes` on every sealed
        HOT chunk. Idempotent: skips chunks that already have the index.
        """
        for chunk in self.store.chunks:
            if chunk.header.state.value == "open" or chunk.tier == Tier.COLD:
                continue
            if not chunk.entries:
                continue
            for field in self.config.static_indexes:
                idx_type = IndexType.SKIP if field == "ts" else IndexType.HASH
                iid = make_index_id(chunk.header.chunk_id, idx_type, field)
                if iid in chunk.indexes:
                    continue
                idx = _make_index(chunk, field, idx_type, self.config)
                idx.build(chunk.entries)
                chunk.indexes[idx.index_id] = idx
                self.tracker.on_index_built(idx.index_id)

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
            if chunk.header.state.value == "open" or chunk.tier == Tier.COLD:
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
        static_fields = set(self.config.static_indexes)
        return [
            DropIndexAction(index_id=info.index_id)
            for info in infos
            if info.field not in static_fields
            and should_drop_index(info, view, self.config)
        ]

    def _plan_promotes(self, view: TrackerView) -> list[PromoteChunkAction]:
        return [
            PromoteChunkAction(chunk_id=chunk.header.chunk_id)
            for chunk in self.store.chunks
            if should_promote_chunk(chunk, view, self.config)
        ]

    def _plan_demotes(self, view: TrackerView) -> list[DemoteChunkAction]:
        """
        First pass: soft demotes from should_demote_chunk (temp+idle).
        Second pass: hard cap. If HOT chunks exceed max_hot_chunks after
        soft demotes, force-demote the coldest persisted ones to bring the
        count down. Coldness = (temperature, last_access) ascending.
        """
        soft = [
            DemoteChunkAction(chunk_id=chunk.header.chunk_id)
            for chunk in self.store.chunks
            if should_demote_chunk(chunk, view, self.config)
        ]

        cap = self.config.max_hot_chunks
        if cap <= 0:
            return soft

        soft_ids = {a.chunk_id for a in soft}
        hot_count = sum(1 for c in self.store.chunks if c.tier == Tier.HOT)
        excess = hot_count - len(soft) - cap
        if excess <= 0:
            return soft

        candidates = sorted(
            (
                c for c in self.store.chunks
                if c.tier == Tier.HOT
                and c.header.state.value == "persisted"
                and c.header.chunk_id not in soft_ids
            ),
            key=lambda c: (
                view.chunk_temperatures.get(c.header.chunk_id, 0.0),
                view.chunk_last_access.get(c.header.chunk_id, 0.0),
            ),
        )
        forced = [
            DemoteChunkAction(chunk_id=c.header.chunk_id)
            for c in candidates[:excess]
        ]
        return soft + forced

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
        elif isinstance(action, DemoteChunkAction):
            await self._apply_demote(action)
        elif isinstance(action, PromoteChunkAction):
            await self._apply_promote(action)
        elif isinstance(action, EvictHeavyIndexAction):
            await self._apply_evict_heavy(action)

    async def _apply_build(self, action: BuildIndexAction) -> None:
        chunk = self._find_chunk(action.chunk_id)
        if chunk is None:
            return
        if chunk.tier == Tier.COLD:
            return
        if chunk.header.state.value == "open":
            return
        if not chunk.entries:
            return
        idx = _make_index(
            chunk,
            action.field,
            action.index_type,
            self.config
        )
        idx.build(chunk.entries)
        chunk.indexes[idx.index_id] = idx
        self.tracker.on_index_built(idx.index_id)
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
        self._publish_event({
            "type": "decision",
            "ts": time.time(),
            "action": "build_index",
            "chunk_id": action.chunk_id,
            "predicate": {"field": action.field, "op": action.op.value},
            "index_type": action.index_type.value,
        })

    async def _apply_drop(self, action: DropIndexAction) -> None:
        for chunk in self.store.chunks:
            if action.index_id in chunk.indexes:
                idx = chunk.indexes.pop(action.index_id)
                usage = self.tracker.index_usage(action.index_id)
                last_used = self.tracker.index_last_used(action.index_id)
                idle = (time.time() - last_used) if last_used is not None else float("inf")
                roi = compute_roi(usage, idx.memory_bytes)
                self.dropped_indexes[action.index_id] = DroppedIndex(
                    index_id=action.index_id,
                    chunk_id=chunk.header.chunk_id,
                    field=idx.field,
                    op=idx.op,
                    index_type=_index_type_of(idx),
                    dropped_at=time.time(),
                    prior_usage=usage,
                )
                logger.info(
                    "decision",
                    extra={
                        "event": "decision",
                        "type": "drop_index",
                        "index_id": action.index_id,
                    },
                )
                self._publish_event({
                    "type": "decision",
                    "ts": time.time(),
                    "action": "drop_index",
                    "index_id": action.index_id,
                    "reason": f"idle={idle:.0f}s, roi={roi:.2f}",
                })
                return

    async def _apply_restore(self, action: RestoreIndexAction) -> None:
        chunk = self._find_chunk(action.chunk_id)
        if chunk is None:
            return
        if chunk.tier == Tier.COLD and self.reader is not None:
            entries = await self.reader.load_entries(chunk.header.chunk_id)
        else:
            entries = chunk.entries
        idx = _make_index(chunk, action.field, action.index_type, self.config)
        idx.build(entries)
        chunk.indexes[idx.index_id] = idx
        self.dropped_indexes.pop(idx.index_id, None)
        self.tracker.on_index_built(idx.index_id)
        logger.info(
            "decision",
            extra={
                "event": "decision",
                "type": "restore_index",
                "chunk_id": action.chunk_id,
                "field": action.field,
            },
        )
        self._publish_event({
            "type": "decision",
            "ts": time.time(),
            "action": "restore_index",
            "chunk_id": action.chunk_id,
            "predicate": {"field": action.field, "op": action.op.value},
            "index_type": action.index_type.value,
        })

    async def _apply_demote(self, action: DemoteChunkAction) -> None:
        chunk = self._find_chunk(action.chunk_id)
        if chunk is None or chunk.tier == Tier.COLD:
            return
        if chunk.header.state.value != "persisted":
            return
        chunk.entries = []
        chunk.tier = Tier.COLD
        self._publish_event({
            "type": "tier_change",
            "ts": time.time(),
            "chunk_id": action.chunk_id,
            "from": "hot",
            "to": "cold",
        })

    async def _apply_promote(self, action: PromoteChunkAction) -> None:
        chunk = self._find_chunk(action.chunk_id)
        if chunk is None or chunk.tier == Tier.HOT:
            return
        if self.reader is not None and not chunk.entries:
            chunk.entries = await self.reader.load_entries(chunk.header.chunk_id)
        chunk.tier = Tier.HOT
        self._publish_event({
            "type": "tier_change",
            "ts": time.time(),
            "chunk_id": action.chunk_id,
            "from": "cold",
            "to": "hot",
        })

    async def _apply_evict_heavy(self, action: EvictHeavyIndexAction) -> None:
        for chunk in self.store.chunks:
            if action.index_id in chunk.indexes:
                chunk.indexes.pop(action.index_id)
                if action.index_id not in chunk.header.indexes_on_disk:
                    chunk.header.indexes_on_disk.append(action.index_id)
                self._publish_event({
                    "type": "decision",
                    "ts": time.time(),
                    "action": "evict_heavy_index",
                    "index_id": action.index_id,
                })
                return

    def _publish_event(self, event: dict) -> None:
        if self.event_broker is not None:
            self.event_broker.publish(event)

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
