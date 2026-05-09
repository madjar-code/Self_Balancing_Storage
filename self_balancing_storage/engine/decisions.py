from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..config import Config
from ..types import (
    ChunkId,
    IndexId,
    Tier,
    IndexType,
    Predicate,
    PredicateOp,
)
from .actions import (
    Action,
    DropIndexAction,
    DroppedIndex,
    DemoteChunkAction,
    EvictHeavyIndexAction,
)

if TYPE_CHECKING:
    from ..chunk import Chunk


@dataclass(frozen=True)
class IndexInfo:
    """Snapshot info about a single ACTIVE index."""
    index_id: IndexId
    chunk_id: ChunkId
    field: str
    op: PredicateOp
    index_type: IndexType
    memory_bytes: int


@dataclass(frozen=True)
class TrackerView:
    """Read-only snapshot of all metrics needed at the start of a tick."""
    now: float
    write_rate: float
    burst_ratio: float
    is_burst: bool
    predicate_freqs: dict[Predicate, int]
    chunk_temperatures: dict[ChunkId, float]
    chunk_last_access: dict[ChunkId, float]
    index_usage: dict[IndexId, int]
    index_last_used: dict[IndexId, float]
    memory_pressure: float
    top_predicates: list[tuple[Predicate, int]] = field(default_factory=list)
    predicate_last_seen: dict[tuple[str, PredicateOp], float] = field(default_factory=dict)


def should_build_index(
    chunk: "Chunk",
    predicate: Predicate,
    view: TrackerView,
    config: Config,
) -> bool:
    if predicate.field not in chunk.header.schema_sketch:
        return False
    freq = view.predicate_freqs.get(predicate, 0)
    if freq < config.build_threshold_freq:
        return False
    temp = view.chunk_temperatures.get(chunk.header.chunk_id, 0.0)
    if temp < config.min_temp_for_index:
        return False
    if view.is_burst:
        return False
    return True


def should_drop_index(
    index_info: IndexInfo,
    view: TrackerView,
    config: Config,
) -> bool:
    last = view.index_last_used.get(index_info.index_id)
    idle = (view.now - last) if last is not None else float("inf")
    usage = view.index_usage.get(index_info.index_id, 0)

    # ROI below minimun - drop
    roi = compute_roi(usage, index_info.memory_bytes)
    if idle > config.idle_drop_sec and roi < config.min_roi:
        return True

    # Memory pressure high - drop even if ROI is acceptable
    if view.memory_pressure > config.mem_pressure_drop and idle > 60:
        return True

    return False


def should_restore_dropped_index(
    dropped: DroppedIndex,
    view: TrackerView,
    config: Config,
) -> bool:
    if (view.now - dropped.dropped_at) > config.cooldown_sec:
        return False
    # Freshness gate: a query must have hit (field, op) since the drop.
    last_seen = view.predicate_last_seen.get((dropped.field, dropped.op))
    if last_seen is None or last_seen <= dropped.dropped_at:
        return False
    freq = sum(
        f for p, f in view.predicate_freqs.items()
        if p.field == dropped.field and p.op == dropped.op
    )
    return freq >= config.build_threshold_freq


def is_dropped_expired(dropped: DroppedIndex, now: float, cooldown_sec: float) -> bool:
    return (now - dropped.dropped_at) > cooldown_sec


def should_demote_chunk(chunk: Chunk, view: TrackerView, config: Config) -> bool:
    if chunk.tier.value != "hot":
        return False
    if chunk.header.state.value != "persisted":
        return False
    persisted_at = chunk.header.persisted_at
    if persisted_at is not None and (view.now - persisted_at) < config.demote_grace_sec:
        return False
    temp = view.chunk_temperatures.get(chunk.header.chunk_id, 0.0)
    if temp >= config.demote_threshold:
        return False
    last = view.chunk_last_access.get(chunk.header.chunk_id)
    if last is None:
        return True
    return (view.now - last) > config.demote_idle_sec


def should_promote_chunk(chunk: Chunk, view: TrackerView, config: Config) -> bool:
    if chunk.tier.value != "cold":
        return False
    temp = view.chunk_temperatures.get(chunk.header.chunk_id, 0.0)
    return temp > config.promote_threshold


def should_evict_heavy_index(info: IndexInfo, view: TrackerView, config: Config) -> bool:
    if info.memory_bytes < config.heavy_index_threshold:
        return False
    last_used = view.index_last_used.get(info.index_id)
    idle = view.now - last_used if last_used is not None else float("inf")
    return view.memory_pressure > config.mem_pressure_drop and idle > 60


def compute_roi(usage: int, memory_bytes: int, tier: "Tier | None" = None, config: Config | None = None) -> float:
    """Tier-aware ROI. If tier is None, falls back to V1 hot-only formula."""
    if usage <= 0:
        return 0.0
    if memory_bytes <= 0:
        return float(usage)
    from ..types import Tier as T
    if tier is None or tier == T.HOT:
        return usage / (memory_bytes / 1024)
    # COLD
    factor = (config.disk_cost_factor if config else 100)
    return usage / (memory_bytes / 1024 / factor)


def plan_memory_relief(
    view: TrackerView,
    indexes: list[IndexInfo],
    chunks: list,  # list[Chunk]
    config: Config,
) -> list[Action]:
    """V2 cascade: demote first, drop as last resort."""
    actions: list[Action] = []
    pressure = view.memory_pressure

    if pressure < config.mem_pressure_drop:
        return actions

    from ..types import Tier
    hot_chunks = [
        c for c in chunks
        if c.tier == Tier.HOT and c.header.state.value == "persisted"
    ]
    coldest_first = sorted(
        hot_chunks,
        key=lambda c: view.chunk_temperatures.get(c.header.chunk_id, 0.0),
    )

    if pressure < config.mem_pressure_high:
        # Elevated: demote 25% coldest hot chunks
        n = max(1, len(coldest_first) // 4)
        for c in coldest_first[:n]:
            actions.append(DemoteChunkAction(c.header.chunk_id, priority=15))

    elif pressure < config.mem_pressure_critical:
        # High: demote 50% + evict heavy indexes
        n = max(1, len(coldest_first) // 2)
        for c in coldest_first[:n]:
            actions.append(DemoteChunkAction(c.header.chunk_id, priority=10))
        for info in indexes:
            if should_evict_heavy_index(info, view, config):
                actions.append(EvictHeavyIndexAction(info.index_id, priority=8))

    else:
        # Critical: demote everything + drop indexes as last resort
        for c in coldest_first:
            actions.append(DemoteChunkAction(c.header.chunk_id, priority=5))
        sorted_indexes = sorted(
            indexes,
            key=lambda i: compute_roi(
                view.index_usage.get(i.index_id, 0), i.memory_bytes, Tier.HOT, config,
            ),
        )
        for info in sorted_indexes[:-3]:
            actions.append(DropIndexAction(info.index_id, priority=1))

    return actions


def choose_index_type(
    predicate: Predicate,
    schema_sketch: dict[str, set[type]],
) -> IndexType:
    if predicate.op == PredicateOp.RANGE and predicate.field == "ts":
        return IndexType.SKIP
    return IndexType.HASH
