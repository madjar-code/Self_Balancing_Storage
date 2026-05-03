from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..config import Config
from ..types import (
    ChunkId,
    IndexId,
    IndexType,
    Predicate,
    PredicateOp,
)
from .actions import (
    Action,
    DropIndexAction,
    DroppedIndex,
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
    index_usage: dict[IndexId, int]
    index_last_used: dict[IndexId, float]
    memory_pressure: float
    top_predicates: list[tuple[Predicate, int]] = field(default_factory=list)


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
    predicate = Predicate(field=dropped.field, op=dropped.op)
    freq = view.predicate_freqs.get(predicate, 0)
    return freq >= config.build_threshold_freq


def is_dropped_expired(dropped: DroppedIndex, now: float, cooldown_sec: float) -> bool:
    return (now - dropped.dropped_at) > cooldown_sec


def choose_index_type(
    predicate: Predicate,
    schema_sketch: dict[str, set[type]],
) -> IndexType:
    if predicate.op == PredicateOp.RANGE and predicate.field == "ts":
        return IndexType.SKIP
    if predicate.op == PredicateOp.EQ:
        # ID-like fields → bloom (high cardinality)
        if predicate.field.endswith("_id"):
            return IndexType.BLOOM
        return IndexType.HASH
    # default → HASH
    return IndexType.HASH


def compute_roi(usage_count: int, memory_bytes: int) -> float:
    """Simple ROI metric for V1: usages per kilobyte of memory."""
    if memory_bytes <= 0:
        return float(usage_count)
    return usage_count / (memory_bytes / 1024)


def plan_memory_relief(
    view: TrackerView,
    indexes: list[IndexInfo],
    config: Config,
) -> list[Action]:
    """Cascade of actions by memory pressure level."""
    actions: list[Action] = []
    pressure = view.memory_pressure

    if pressure < config.mem_pressure_drop:
        return actions

    # Sort indexes from least to most valuable
    def index_value(info: IndexInfo) -> float:
        usage = view.index_usage.get(info.index_id, 0)
        return compute_roi(usage, info.memory_bytes)

    sorted_indexes = sorted(indexes, key=index_value)

    if pressure < config.mem_pressure_high:
        # elevated - drop the 25% least valuable
        n_to_drop = max(1, len(sorted_indexes) // 4)
        for info in sorted_indexes[:n_to_drop]:
            actions.append(DropIndexAction(index_id=info.index_id, priority=10))
    elif pressure < config.mem_pressure_critical:
        # high - drop 50%
        n_to_drop = max(1, len(sorted_indexes) // 2)
        for info in sorted_indexes[:n_to_drop]:
            actions.append(DropIndexAction(index_id=info.index_id, priority=5))
    else:
        # critical — drop everything except the top-3 most valuable
        for info in sorted_indexes[:-3]:
            actions.append(DropIndexAction(index_id=info.index_id, priority=1))
    return actions
