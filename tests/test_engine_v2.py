from typing import Any

import pytest

from self_balancing_storage.config import Config
from self_balancing_storage.engine.actions import (
    BuildIndexAction,
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
    ChunkState,
    IndexType,
    LogEntry,
    PredicateOp,
    Tier,
)


class FakeChunk:
    def __init__(self, chunk_id: str, tier: Tier = Tier.HOT, state: str = "persisted"):
        state_obj = type("S", (), {"value": state})()
        self.header = type(
            "H", (),
            {
                "chunk_id": chunk_id,
                "schema_sketch": {},
                "state": state_obj,
                "persisted_at": None,
            },
        )()
        self.tier = tier
        self.indexes: dict = {}
        self.entries: list = []


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


def test_demote_false_for_open_chunk():
    # Open chunks aren't on disk yet; demote would clear entries and lose data.
    config = Config(demote_threshold=0.1, demote_idle_sec=300.0)
    chunk = FakeChunk("c1", tier=Tier.HOT, state="open")
    view = base_view(chunk_temperatures={"c1": 0.0})
    assert should_demote_chunk(chunk, view, config) is False


def test_demote_false_for_sealed_not_yet_persisted_chunk():
    # Sealed chunks have a persist task queued but maybe not finished;
    # demoting would race and write empty entries to disk.
    config = Config(demote_threshold=0.1, demote_idle_sec=300.0)
    chunk = FakeChunk("c1", tier=Tier.HOT, state="sealed")
    view = base_view(chunk_temperatures={"c1": 0.0})
    assert should_demote_chunk(chunk, view, config) is False


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
    chunk.header.state = ChunkState.PERSISTED
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


# === demote grace period after persist ===

def test_demote_false_for_recently_persisted_chunk():
    """A chunk persisted within demote_grace_sec should not be demoted yet."""
    config = Config(demote_threshold=0.1, demote_idle_sec=10.0, demote_grace_sec=30.0)
    chunk = FakeChunk("c1", tier=Tier.HOT, state="persisted")
    chunk.header.persisted_at = 990.0  # 10s before view.now=1000, within grace
    view = base_view(now=1000.0)
    assert should_demote_chunk(chunk, view, config) is False


def test_demote_true_after_grace_period_elapses():
    """After grace period, the usual idle/temp checks decide."""
    config = Config(demote_threshold=0.1, demote_idle_sec=10.0, demote_grace_sec=30.0)
    chunk = FakeChunk("c1", tier=Tier.HOT, state="persisted")
    chunk.header.persisted_at = 900.0  # 100s before view.now=1000, way past grace
    view = base_view(
        now=1000.0,
        chunk_temperatures={"c1": 0.0},
        chunk_last_access={"c1": 900.0},  # idle 100s > 10
    )
    assert should_demote_chunk(chunk, view, config) is True


# === _apply_build defensive guards ===

@pytest.mark.asyncio
async def test_apply_build_skips_cold_chunk():
    """If the chunk turned cold between planning and apply, build is no-op."""
    config = Config()
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    engine = DecisionEngine(tracker, store, config)
    for i in range(3):
        store.append(LogEntry(ts=float(i), service="a", level="INFO", msg="m"))
    chunk = store.chunks[0]
    chunk.header.state = ChunkState.PERSISTED
    chunk.tier = Tier.COLD
    chunk.entries = []

    await engine._apply_build(BuildIndexAction(
        chunk_id=chunk.header.chunk_id,
        field="service",
        op=PredicateOp.EQ,
        index_type=IndexType.HASH,
    ))
    assert chunk.indexes == {}


@pytest.mark.asyncio
async def test_apply_build_skips_open_chunk():
    """Open chunks have no schema yet - build is no-op."""
    config = Config()
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    engine = DecisionEngine(tracker, store, config)
    store.append(LogEntry(ts=0.0, service="a", level="INFO", msg="m"), now=0.0)
    chunk = store.chunks[0]
    chunk.header.state = ChunkState.OPEN  # explicitly keep open for the test

    await engine._apply_build(BuildIndexAction(
        chunk_id=chunk.header.chunk_id,
        field="service",
        op=PredicateOp.EQ,
        index_type=IndexType.HASH,
    ))
    assert chunk.indexes == {}


@pytest.mark.asyncio
async def test_apply_build_skips_chunk_with_empty_entries():
    """Persisted-but-emptied chunk (e.g. recently demoted) is no-op."""
    config = Config()
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    engine = DecisionEngine(tracker, store, config)
    for i in range(3):
        store.append(LogEntry(ts=float(i), service="a", level="INFO", msg="m"))
    chunk = store.chunks[0]
    chunk.header.state = ChunkState.PERSISTED
    chunk.entries = []  # forced empty, tier still HOT

    await engine._apply_build(BuildIndexAction(
        chunk_id=chunk.header.chunk_id,
        field="service",
        op=PredicateOp.EQ,
        index_type=IndexType.HASH,
    ))
    assert chunk.indexes == {}


# === dynamic_tiering toggle ===

def test_plan_promotes_runs_when_tiering_enabled():
    """When dynamic_tiering=True (default), _plan_promotes returns actions."""
    config = Config(dynamic_tiering=True, promote_threshold=0.5)
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    engine = DecisionEngine(tracker, store, config)
    chunk = FakeChunk("c1", tier=Tier.COLD)
    store.chunks.append(chunk)  # type: ignore[arg-type]
    view = base_view(chunk_temperatures={"c1": 0.9})
    assert engine._plan_promotes(view) == [PromoteChunkAction(chunk_id="c1")]


@pytest.mark.asyncio
async def test_tick_skips_promotes_when_dynamic_tiering_disabled():
    """The wrapper logic in _tick skips _plan_promotes when toggle is off."""
    from self_balancing_storage.tracker.tracker import QueryEvent

    config = Config(dynamic_tiering=False)
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    engine = DecisionEngine(tracker, store, config)
    chunk = FakeChunk("c1", tier=Tier.COLD)
    store.chunks.append(chunk)  # type: ignore[arg-type]
    """Seed heatmap so chunk c1 looks very hot."""
    for _ in range(20):
        tracker.on_query(QueryEvent(ts=1000.0, predicates=[], chunks_scanned=["c1"]))

    promotes_seen: list[PromoteChunkAction] = []
    original_apply = engine._apply

    async def spy_apply(action):
        if isinstance(action, PromoteChunkAction):
            promotes_seen.append(action)
        await original_apply(action)

    engine._apply = spy_apply  # type: ignore[method-assign]
    await engine._tick()
    assert promotes_seen == []


# === static_indexes ===

def test_ensure_static_indexes_builds_on_sealed_hot_chunk():
    config = Config(static_indexes=("service", "level"), dynamic_indexing=False)
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    engine = DecisionEngine(tracker, store, config)
    for i in range(3):
        store.append(LogEntry(ts=float(i), service="auth", level="INFO", msg="m"))
    chunk = store.chunks[0]
    chunk.header.state = ChunkState.PERSISTED
    chunk.tier = Tier.HOT

    engine._ensure_static_indexes()

    fields = {idx.field for idx in chunk.indexes.values()}
    assert fields == {"service", "level"}


def test_ensure_static_indexes_idempotent():
    """Calling twice produces no extra indexes."""
    config = Config(static_indexes=("service",), dynamic_indexing=False)
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    engine = DecisionEngine(tracker, store, config)
    for i in range(3):
        store.append(LogEntry(ts=float(i), service="auth", level="INFO", msg="m"))
    chunk = store.chunks[0]
    chunk.header.state = ChunkState.PERSISTED
    chunk.tier = Tier.HOT

    engine._ensure_static_indexes()
    n_first = len(chunk.indexes)
    engine._ensure_static_indexes()
    assert len(chunk.indexes) == n_first


def test_ensure_static_indexes_skips_cold_chunk():
    config = Config(static_indexes=("service",))
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    engine = DecisionEngine(tracker, store, config)
    for i in range(3):
        store.append(LogEntry(ts=float(i), service="auth", level="INFO", msg="m"))
    chunk = store.chunks[0]
    chunk.tier = Tier.COLD
    chunk.header.state = ChunkState.PERSISTED

    engine._ensure_static_indexes()
    assert chunk.indexes == {}


def test_plan_index_drops_skips_static_fields():
    config = Config(static_indexes=("service",))
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    engine = DecisionEngine(tracker, store, config)

    static_info = IndexInfo(
        index_id="c1:hash:service",
        chunk_id="c1",
        field="service",
        op=PredicateOp.EQ,
        index_type=IndexType.HASH,
        memory_bytes=1024,
    )
    other_info = IndexInfo(
        index_id="c1:hash:tenant",
        chunk_id="c1",
        field="tenant",
        op=PredicateOp.EQ,
        index_type=IndexType.HASH,
        memory_bytes=1024,
    )
    """View where both indexes look idle enough to drop."""
    view = base_view(
        now=10_000.0,
        index_usage={"c1:hash:service": 0, "c1:hash:tenant": 0},
        index_last_used={"c1:hash:service": 0.0, "c1:hash:tenant": 0.0},
    )

    drops = engine._plan_index_drops(view, [static_info, other_info])
    dropped_ids = {d.index_id for d in drops}
    assert "c1:hash:service" not in dropped_ids
    assert "c1:hash:tenant" in dropped_ids


# === max_hot_chunks (hard cap force-demote) ===

def test_plan_demotes_force_demotes_excess_hot_chunks():
    """When HOT count exceeds max_hot_chunks, the coldest are force-demoted."""
    config = Config(max_hot_chunks=2, demote_idle_sec=10**9)
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    engine = DecisionEngine(tracker, store, config)
    """5 persisted-HOT chunks. Cap is 2 -> 3 must be force-demoted, coldest first."""
    for i, t in enumerate([0.9, 0.1, 0.5, 0.3, 0.7]):
        c = FakeChunk(f"c{i}", tier=Tier.HOT, state="persisted")
        store.chunks.append(c)  # type: ignore[arg-type]
    view = base_view(
        chunk_temperatures={f"c{i}": t for i, t in enumerate([0.9, 0.1, 0.5, 0.3, 0.7])},
    )

    actions = engine._plan_demotes(view)
    demoted = {a.chunk_id for a in actions}
    """c1 (0.1), c3 (0.3), c2 (0.5) are coldest; c0 (0.9) and c4 (0.7) survive."""
    assert demoted == {"c1", "c3", "c2"}


def test_plan_demotes_skips_open_chunks_when_force_demoting():
    """Open chunks cannot be demoted; the cap pass must skip them entirely."""
    config = Config(max_hot_chunks=2, demote_idle_sec=10**9)
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    engine = DecisionEngine(tracker, store, config)
    """4 HOT: 3 persisted, 1 open. Cap is 2 -> 2 force-demotes among persisted."""
    chunks = [
        FakeChunk("c0", tier=Tier.HOT, state="persisted"),
        FakeChunk("c1", tier=Tier.HOT, state="open"),
        FakeChunk("c2", tier=Tier.HOT, state="persisted"),
        FakeChunk("c3", tier=Tier.HOT, state="persisted"),
    ]
    for c in chunks:
        store.chunks.append(c)  # type: ignore[arg-type]
    view = base_view(
        chunk_temperatures={"c0": 0.2, "c1": 0.1, "c2": 0.8, "c3": 0.3},
    )

    actions = engine._plan_demotes(view)
    demoted = {a.chunk_id for a in actions}
    """c1 (open) skipped. Among persisted, c0 (0.2) and c3 (0.3) are coldest."""
    assert demoted == {"c0", "c3"}


def test_plan_demotes_no_force_when_under_cap():
    """If HOT count is at or below cap, no force-demote happens."""
    config = Config(max_hot_chunks=10, demote_idle_sec=10**9)
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    engine = DecisionEngine(tracker, store, config)
    for i in range(5):
        c = FakeChunk(f"c{i}", tier=Tier.HOT, state="persisted")
        store.chunks.append(c)  # type: ignore[arg-type]
    view = base_view(chunk_temperatures={f"c{i}": 0.1 for i in range(5)})

    actions = engine._plan_demotes(view)
    assert actions == []


def test_plan_demotes_disabled_when_cap_is_zero():
    """max_hot_chunks=0 disables the hard cap entirely."""
    config = Config(max_hot_chunks=0, demote_idle_sec=10**9)
    tracker = AccessTracker(config)
    store = ChunkStore(config)
    engine = DecisionEngine(tracker, store, config)
    for i in range(50):
        c = FakeChunk(f"c{i}", tier=Tier.HOT, state="persisted")
        store.chunks.append(c)  # type: ignore[arg-type]
    view = base_view(chunk_temperatures={f"c{i}": 0.1 for i in range(50)})

    assert engine._plan_demotes(view) == []
