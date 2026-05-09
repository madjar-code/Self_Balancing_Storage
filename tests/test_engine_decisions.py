from typing import Any
from self_balancing_storage.config import Config
from self_balancing_storage.engine.actions import (
    DemoteChunkAction,
    DropIndexAction,
    DroppedIndex,
)
from self_balancing_storage.engine.decisions import (
    IndexInfo,
    TrackerView,
    choose_index_type,
    plan_memory_relief,
    should_build_index,
    should_drop_index,
    should_restore_dropped_index,
)
from self_balancing_storage.types import IndexType, Predicate, PredicateOp, Tier


class FakeChunk:
    """Minimal chunk stand-in for decision-function tests."""
    def __init__(
        self,
        chunk_id: str,
        schema: dict[str, set[type]],
        tier: Tier = Tier.HOT,
        state: str = "persisted",
    ):
        state_obj = type("S", (), {"value": state})()
        self.header = type(
            "H", (),
            {
                "chunk_id": chunk_id,
                "schema_sketch": schema,
                "state": state_obj,
                "persisted_at": None,
            },
        )()
        self.tier = tier


def base_view(**overrides) -> TrackerView:
    defaults: dict[str, Any] = dict(
        now=100.0,
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


# === should_build_index ===

def test_build_happy_path():
    config = Config(build_threshold_freq=5, min_temp_for_index=0.3)
    chunk = FakeChunk("c1", {"service": {str}})
    pred = Predicate("service", PredicateOp.EQ, "auth")
    view = base_view(
        predicate_freqs={pred: 10},
        chunk_temperatures={"c1": 0.5},
    )
    assert should_build_index(chunk, pred, view, config) is True


def test_build_veto_when_predicate_freq_below_threshold():
    config = Config(build_threshold_freq=5)
    chunk = FakeChunk("c1", {"service": {str}})
    pred = Predicate("service", PredicateOp.EQ, "auth")
    view = base_view(predicate_freqs={pred: 2}, chunk_temperatures={"c1": 0.5})
    assert should_build_index(chunk, pred, view, config) is False


def test_build_veto_during_burst():
    config = Config(build_threshold_freq=5, min_temp_for_index=0.0)
    chunk = FakeChunk("c1", {"service": {str}})
    pred = Predicate("service", PredicateOp.EQ, "auth")
    view = base_view(
        is_burst=True,
        predicate_freqs={pred: 20},
        chunk_temperatures={"c1": 0.5},
    )
    assert should_build_index(chunk, pred, view, config) is False


def test_build_veto_when_chunk_too_cold():
    config = Config(build_threshold_freq=5, min_temp_for_index=0.5)
    chunk = FakeChunk("c1", {"service": {str}})
    pred = Predicate("service", PredicateOp.EQ, "auth")
    view = base_view(
        predicate_freqs={pred: 10},
        chunk_temperatures={"c1": 0.1},
    )
    assert should_build_index(chunk, pred, view, config) is False


# === should_drop_index ===

def test_drop_when_idle_and_low_roi():
    config = Config(idle_drop_sec=600.0, min_roi=1.0)
    info = IndexInfo("i1", "c1", "service", PredicateOp.EQ, IndexType.HASH, memory_bytes=10_000_000)
    view = base_view(
        now=10_000,
        index_last_used={"i1": 0.0},  # 10000s idle
        index_usage={"i1": 0},
    )
    assert should_drop_index(info, view, config) is True


def test_drop_under_memory_pressure_even_with_recent_use():
    config = Config(mem_pressure_drop=0.7)
    info = IndexInfo("i1", "c1", "x", PredicateOp.EQ, IndexType.HASH, memory_bytes=1000)
    view = base_view(
        memory_pressure=0.85,
        now=1000,
        index_last_used={"i1": 800},  # 200s ago > 60s grace
    )
    assert should_drop_index(info, view, config) is True


def test_no_drop_when_actively_used_and_pressure_normal():
    config = Config(idle_drop_sec=600.0, min_roi=0.0, mem_pressure_drop=0.7)
    info = IndexInfo("i1", "c1", "x", PredicateOp.EQ, IndexType.HASH, memory_bytes=1000)
    view = base_view(
        now=1000,
        index_last_used={"i1": 999},  # 1s ago
        index_usage={"i1": 500},
        memory_pressure=0.3,
    )
    assert should_drop_index(info, view, config) is False


# === should_restore_dropped_index ===

def test_restore_within_cooldown_and_predicate_returned():
    config = Config(cooldown_sec=600, build_threshold_freq=5)
    dropped = DroppedIndex(
        "i1", "c1", "service", PredicateOp.EQ, IndexType.HASH,
        dropped_at=900, prior_usage=20,
    )
    pred = Predicate("service", PredicateOp.EQ)
    view = base_view(
        now=1000,
        predicate_freqs={pred: 10},
        predicate_last_seen={("service", PredicateOp.EQ): 950.0},  # after drop
    )
    assert should_restore_dropped_index(dropped, view, config) is True


def test_no_restore_after_cooldown_expired():
    config = Config(cooldown_sec=600, build_threshold_freq=5)
    dropped = DroppedIndex(
        "i1", "c1", "service", PredicateOp.EQ, IndexType.HASH,
        dropped_at=0, prior_usage=20,
    )
    pred = Predicate("service", PredicateOp.EQ)
    view = base_view(now=1000, predicate_freqs={pred: 10})
    assert should_restore_dropped_index(dropped, view, config) is False


def test_restore_matches_value_keyed_predicates():
    # Regression: predicate_freqs is keyed by full Predicate (incl. value),
    # so restore must aggregate over (field, op) regardless of values.
    config = Config(cooldown_sec=600, build_threshold_freq=5)
    dropped = DroppedIndex(
        "i1", "c1", "trace_id", PredicateOp.EQ, IndexType.BLOOM,
        dropped_at=900, prior_usage=20,
    )
    view = base_view(
        now=1000,
        predicate_freqs={
            Predicate("trace_id", PredicateOp.EQ, "trace-42"): 7,
            Predicate("trace_id", PredicateOp.EQ, "trace-7"): 3,
            Predicate("service", PredicateOp.EQ, "auth"): 50,  # noise
        },
        predicate_last_seen={("trace_id", PredicateOp.EQ): 980.0},
    )
    # 7 + 3 = 10 >= threshold 5
    assert should_restore_dropped_index(dropped, view, config) is True


def test_no_restore_when_aggregated_freq_below_threshold():
    config = Config(cooldown_sec=600, build_threshold_freq=20)
    dropped = DroppedIndex(
        "i1", "c1", "trace_id", PredicateOp.EQ, IndexType.BLOOM,
        dropped_at=900, prior_usage=20,
    )
    view = base_view(
        now=1000,
        predicate_freqs={
            Predicate("trace_id", PredicateOp.EQ, "trace-42"): 5,
            Predicate("trace_id", PredicateOp.EQ, "trace-7"): 5,
        },
        predicate_last_seen={("trace_id", PredicateOp.EQ): 980.0},
    )
    # 5 + 5 = 10 < threshold 20
    assert should_restore_dropped_index(dropped, view, config) is False


def test_no_restore_when_predicate_not_seen_since_drop():
    # Drop/restore ping-pong guard: stale predicate freqs (no fresh queries
    # since the drop) must not trigger a restore.
    config = Config(cooldown_sec=600, build_threshold_freq=5)
    dropped = DroppedIndex(
        "i1", "c1", "service", PredicateOp.EQ, IndexType.HASH,
        dropped_at=900, prior_usage=20,
    )
    pred = Predicate("service", PredicateOp.EQ, "auth")
    view = base_view(
        now=1000,
        predicate_freqs={pred: 50},  # high freq from before the drop
        predicate_last_seen={("service", PredicateOp.EQ): 800.0},  # before drop
    )
    assert should_restore_dropped_index(dropped, view, config) is False


def test_no_restore_when_predicate_never_seen():
    config = Config(cooldown_sec=600, build_threshold_freq=5)
    dropped = DroppedIndex(
        "i1", "c1", "service", PredicateOp.EQ, IndexType.HASH,
        dropped_at=900, prior_usage=20,
    )
    pred = Predicate("service", PredicateOp.EQ, "auth")
    view = base_view(
        now=1000,
        predicate_freqs={pred: 50},
        predicate_last_seen={},  # tracker has no record
    )
    assert should_restore_dropped_index(dropped, view, config) is False


def test_no_drop_for_freshly_built_index_with_recorded_birth():
    config = Config(idle_drop_sec=600.0, min_roi=10.0, mem_pressure_drop=0.7)
    info = IndexInfo("i1", "c1", "trace_id", PredicateOp.EQ, IndexType.BLOOM, memory_bytes=200)
    view = base_view(
        now=1000,
        index_last_used={"i1": 999.0},  # built 1 second ago
        index_usage={"i1": 0},          # never queried
        memory_pressure=0.3,
    )
    assert should_drop_index(info, view, config) is False


# === plan_memory_relief ===

def test_relief_no_action_below_threshold():
    config = Config(mem_pressure_drop=0.7)
    actions = plan_memory_relief(base_view(memory_pressure=0.5), [], [], config)
    assert actions == []


def test_relief_demotes_25_percent_coldest_at_elevated():
    config = Config(mem_pressure_drop=0.7, mem_pressure_high=0.8, mem_pressure_critical=0.95)
    chunks = [FakeChunk(f"c{i}", {}, tier=Tier.HOT) for i in range(8)]
    temperatures = {f"c{i}": float(i) * 0.1 for i in range(8)}  # c0 coldest, c7 hottest
    actions = plan_memory_relief(
        base_view(memory_pressure=0.75, chunk_temperatures=temperatures),
        [],
        chunks,
        config,
    )
    assert len(actions) == 2  # 25% of 8
    assert all(isinstance(a, DemoteChunkAction) for a in actions)
    assert {a.chunk_id for a in actions} == {"c0", "c1"}  # the two coldest


def test_relief_critical_demotes_all_hot_and_keeps_top_3_indexes():
    config = Config(mem_pressure_drop=0.7, mem_pressure_high=0.8, mem_pressure_critical=0.95)
    chunks = [FakeChunk(f"c{i}", {}, tier=Tier.HOT) for i in range(4)]
    indexes = [
        IndexInfo(f"i{i}", "c1", "x", PredicateOp.EQ, IndexType.HASH, memory_bytes=1000)
        for i in range(10)
    ]
    actions = plan_memory_relief(
        base_view(memory_pressure=0.97), indexes, chunks, config,
    )
    demotes = [a for a in actions if isinstance(a, DemoteChunkAction)]
    drops = [a for a in actions if isinstance(a, DropIndexAction)]
    assert len(demotes) == 4  # all hot chunks demoted
    assert len(drops) == 7    # all indexes but top-3 dropped


# === choose_index_type ===

def test_choose_index_type_eq_picks_hash_even_for_id_fields():
    """V2 picks Hash for any equality predicate (no Bloom auto-build)."""
    p = Predicate("trace_id", PredicateOp.EQ, "abc")
    assert choose_index_type(p, {}) == IndexType.HASH


def test_choose_index_type_range_on_ts_picks_skip():
    p = Predicate("ts", PredicateOp.RANGE, (0.0, 100.0))
    assert choose_index_type(p, {}) == IndexType.SKIP


def test_choose_index_type_range_on_other_field_falls_back_to_hash():
    p = Predicate("user_no", PredicateOp.RANGE, (1, 50))
    assert choose_index_type(p, {}) == IndexType.HASH
