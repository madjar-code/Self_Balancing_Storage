from typing import Any

import pytest

from self_balancing_storage.config import Config
from self_balancing_storage.engine.actions import (
    DemoteChunkAction,
    EvictHeavyIndexAction,
    PromoteChunkAction,
)
from self_balancing_storage.engine.decisions import (
    IndexInfo,
    TrackerView,
    compute_roi,
    should_demote_chunk,
    should_evict_heavy_index,
    should_promote_chunk,
)
from self_balancing_storage.engine.engine import DecisionEngine
from self_balancing_storage.indexes.hash_index import HashIndex
from self_balancing_storage.store import ChunkStore
from self_balancing_storage.tracker.tracker import AccessTracker
from self_balancing_storage.types import (
    IndexType,
    LogEntry,
    PredicateOp,
    Tier,
)


class FakeChunk:
    def __init__(self, chunk_id: str, tier: Tier = Tier.HOT):
        self.header = type("H", (), {"chunk_id": chunk_id, "schema_sketch": {}})()
        self.tier = tier


class FakeBroker:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def publish(self, event: dict) -> None:
        self.events.append(event)


def base_view(**overrides) -> TrackerView:
    defaults: dict[str, Any] = dict(
        now=1000.0,
        write_rate=10.0,
        burst_ratio=1.0,
        is_burst=False,
        predicate_freqs={},
        chunk_temperatures={},
        chunk_last_access={},
        index_usage={},
        index_last_used={},
        memory_pressure=0.3,
    )
    defaults.update(overrides)
    return TrackerView(**defaults)


# === should_demote_chunk ===

def test_demote_true_when_cold_and_idle_past_threshold():
    config = Config(demote_threshold=0.1, demote_idle_sec=300.0)
    chunk = FakeChunk("c1", tier=Tier.HOT)
    view = base_view(
        now=1000.0,
        chunk_temperatures={"c1": 0.05},
        chunk_last_access={"c1": 500.0},  # 500s ago > 300s
    )
    assert should_demote_chunk(chunk, view, config) is True


def test_demote_false_for_already_cold_chunk():
    config = Config(demote_threshold=0.1, demote_idle_sec=300.0)
    chunk = FakeChunk("c1", tier=Tier.COLD)
    view = base_view(chunk_temperatures={"c1": 0.0}, chunk_last_access={"c1": 0.0})
    assert should_demote_chunk(chunk, view, config) is False


def test_demote_false_when_recently_accessed():
    config = Config(demote_threshold=0.1, demote_idle_sec=300.0)
    chunk = FakeChunk("c1", tier=Tier.HOT)
    view = base_view(
        now=1000.0,
        chunk_temperatures={"c1": 0.05},
        chunk_last_access={"c1": 950.0},  # 50s ago < 300s
    )
    assert should_demote_chunk(chunk, view, config) is False


def test_demote_false_when_temperature_above_threshold():
    config = Config(demote_threshold=0.1, demote_idle_sec=300.0)
    chunk = FakeChunk("c1", tier=Tier.HOT)
    view = base_view(
        now=1000.0,
        chunk_temperatures={"c1": 0.5},
        chunk_last_access={"c1": 0.0},
    )
    assert should_demote_chunk(chunk, view, config) is False


def test_demote_true_when_no_recorded_access():
    config = Config(demote_threshold=0.1, demote_idle_sec=300.0)
    chunk = FakeChunk("c1", tier=Tier.HOT)
    view = base_view(chunk_temperatures={"c1": 0.05})  # no entry in chunk_last_access
    assert should_demote_chunk(chunk, view, config) is True


# === should_promote_chunk ===

def test_promote_true_when_cold_and_temperature_high():
    config = Config(promote_threshold=0.5)
    chunk = FakeChunk("c1", tier=Tier.COLD)
    view = base_view(chunk_temperatures={"c1": 0.7})
    assert should_promote_chunk(chunk, view, config) is True


def test_promote_false_when_already_hot():
    config = Config(promote_threshold=0.5)
    chunk = FakeChunk("c1", tier=Tier.HOT)
    view = base_view(chunk_temperatures={"c1": 0.9})
    assert should_promote_chunk(chunk, view, config) is False


def test_promote_false_when_temperature_below_threshold():
    config = Config(promote_threshold=0.5)
    chunk = FakeChunk("c1", tier=Tier.COLD)
    view = base_view(chunk_temperatures={"c1": 0.3})
    assert should_promote_chunk(chunk, view, config) is False


# === should_evict_heavy_index ===

def test_evict_heavy_true_when_heavy_idle_and_pressure():
    config = Config(heavy_index_threshold=100 * 1024, mem_pressure_drop=0.7)
    info = IndexInfo("i1", "c1", "x", PredicateOp.EQ, IndexType.HASH, memory_bytes=200 * 1024)
    view = base_view(
        now=1000.0,
        memory_pressure=0.85,
        index_last_used={"i1": 500.0},  # 500s idle > 60s
    )
    assert should_evict_heavy_index(info, view, config) is True


def test_evict_heavy_false_for_small_index():
    config = Config(heavy_index_threshold=100 * 1024)
    info = IndexInfo("i1", "c1", "x", PredicateOp.EQ, IndexType.HASH, memory_bytes=10_000)
    view = base_view(memory_pressure=0.95)
    assert should_evict_heavy_index(info, view, config) is False


def test_evict_heavy_false_when_pressure_low():
    config = Config(heavy_index_threshold=100 * 1024, mem_pressure_drop=0.7)
    info = IndexInfo("i1", "c1", "x", PredicateOp.EQ, IndexType.HASH, memory_bytes=200 * 1024)
    view = base_view(memory_pressure=0.5, index_last_used={"i1": 0.0})
    assert should_evict_heavy_index(info, view, config) is False


# === compute_roi tier-aware ===

def test_compute_roi_cold_higher_than_hot_for_same_inputs():
    config = Config(disk_cost_factor=100)
    hot_roi = compute_roi(usage=10, memory_bytes=10_240, tier=Tier.HOT, config=config)
    cold_roi = compute_roi(usage=10, memory_bytes=10_240, tier=Tier.COLD, config=config)
    assert cold_roi > hot_roi


def test_compute_roi_zero_when_unused():
    assert compute_roi(usage=0, memory_bytes=10_000, tier=Tier.HOT) == 0.0


# === apply methods ===

@pytest.mark.asyncio
async def test_apply_demote_clears_entries_and_emits_event():
    config = Config()
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    broker = FakeBroker()
    engine = DecisionEngine(tracker, store, config, event_broker=broker)
    for i in range(5):
        store.append(LogEntry(ts=float(i), service="a", level="INFO", msg="m"))
    chunk = store.chunks[0]
    assert chunk.tier == Tier.HOT
    assert chunk.entries

    await engine._apply_demote(DemoteChunkAction(chunk.header.chunk_id))

    assert chunk.tier == Tier.COLD
    assert chunk.entries == []
    tier_events = [e for e in broker.events if e["type"] == "tier_change"]
    assert len(tier_events) == 1
    assert tier_events[0]["from"] == "hot"
    assert tier_events[0]["to"] == "cold"


@pytest.mark.asyncio
async def test_apply_demote_idempotent_for_already_cold_chunk():
    config = Config()
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    broker = FakeBroker()
    engine = DecisionEngine(tracker, store, config, event_broker=broker)
    store.append(LogEntry(ts=0.0, service="a", level="INFO", msg="m"))
    chunk = store.chunks[0]
    chunk.tier = Tier.COLD

    await engine._apply_demote(DemoteChunkAction(chunk.header.chunk_id))

    assert broker.events == []  # no event emitted for no-op


@pytest.mark.asyncio
async def test_apply_promote_flips_tier_and_emits_event():
    config = Config()
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    broker = FakeBroker()
    engine = DecisionEngine(tracker, store, config, event_broker=broker)
    store.append(LogEntry(ts=0.0, service="a", level="INFO", msg="m"))
    chunk = store.chunks[0]
    chunk.tier = Tier.COLD

    await engine._apply_promote(PromoteChunkAction(chunk.header.chunk_id))

    assert chunk.tier == Tier.HOT
    tier_events = [e for e in broker.events if e["type"] == "tier_change"]
    assert len(tier_events) == 1
    assert tier_events[0]["from"] == "cold"
    assert tier_events[0]["to"] == "hot"


@pytest.mark.asyncio
async def test_apply_evict_heavy_pops_index_and_records_on_disk():
    config = Config()
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    broker = FakeBroker()
    engine = DecisionEngine(tracker, store, config, event_broker=broker)
    for i in range(5):
        store.append(LogEntry(ts=float(i), service="a", level="INFO", msg="m"))
    chunk = store.chunks[0]
    idx = HashIndex(chunk_id=chunk.header.chunk_id, field="service")
    idx.build(chunk.entries)
    chunk.indexes[idx.index_id] = idx

    await engine._apply_evict_heavy(EvictHeavyIndexAction(idx.index_id))

    assert idx.index_id not in chunk.indexes
    assert idx.index_id in chunk.header.indexes_on_disk
    decision_events = [e for e in broker.events if e["type"] == "decision"]
    assert any(e.get("action") == "evict_heavy_index" for e in decision_events)
