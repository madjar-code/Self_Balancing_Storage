from self_balancing_storage.config import Config
from self_balancing_storage.tracker.tracker import (
    AccessTracker,
    QueryEvent,
    WriteEvent,
)
from self_balancing_storage.types import Predicate, PredicateOp


def test_on_write_increases_write_rate():
    tracker = AccessTracker(Config(write_window_sec=10))
    for i in range(100):
        tracker.on_write(WriteEvent(ts=float(i), n_entries=1, n_bytes=64))
    assert tracker.write_rate() > 0


def test_on_query_records_predicate_frequency():
    tracker = AccessTracker(Config())
    pred = Predicate("service", PredicateOp.EQ, "auth")
    for _ in range(10):
        tracker.on_query(QueryEvent(
            ts=0.0,
            predicates=[pred],
            chunks_scanned=["c1"],
        ))
    assert tracker.predicate_frequency(pred) >= 10


def test_top_predicates_returns_heavy_hitter_first():
    tracker = AccessTracker(Config())
    heavy = Predicate("service", PredicateOp.EQ, "auth")
    for _ in range(50):
        tracker.on_query(QueryEvent(ts=0.0, predicates=[heavy], chunks_scanned=[]))
    for i in range(5):
        rare = Predicate(f"x{i}", PredicateOp.EQ, i)
        tracker.on_query(QueryEvent(ts=0.0, predicates=[rare], chunks_scanned=[]))

    top = tracker.top_predicates()
    assert top[0][0] == heavy


def test_chunk_temperature_grows_with_queries():
    tracker = AccessTracker(Config())
    for _ in range(5):
        tracker.on_query(QueryEvent(ts=0.0, predicates=[], chunks_scanned=["c1"]))
    assert tracker.chunk_temperature("c1") > 0


def test_index_usage_counter_and_last_used():
    tracker = AccessTracker(Config())
    tracker.on_index_use("idx1", now=10.0)
    tracker.on_index_use("idx1", now=20.0)
    tracker.on_index_use("idx1", now=30.0)
    assert tracker.index_usage("idx1") == 3
    assert tracker.index_last_used("idx1") == 30.0


def test_memory_pressure_in_unit_range():
    tracker = AccessTracker(Config(max_memory_bytes=1024 * 1024))
    p = tracker.memory_pressure()
    assert 0.0 <= p <= 1.0


def test_is_burst_after_spike():
    config = Config(burst_enter=2.0)
    tracker = AccessTracker(config)
    # baseline
    for _ in range(50):
        tracker.on_write(WriteEvent(ts=0.0, n_entries=1, n_bytes=64))
    # spike
    for _ in range(10):
        tracker.on_write(WriteEvent(ts=1.0, n_entries=1000, n_bytes=64000))
    assert tracker.is_burst() is True
