from self_balancing_storage.indexes.skip_index import SkipIndex
from self_balancing_storage.types import LogEntry


def make_entry(ts: float) -> LogEntry:
    return LogEntry(ts=ts, service="svc", level="INFO", msg="m")


def test_range_spanning_multiple_blocks():
    idx = SkipIndex(chunk_id="c1", block_size=3)
    idx.build([make_entry(x) for x in range(10)])
    # blocks: [0..2], [3..5], [6..8], [9]
    print(idx._blocks)
    positions = idx.lookup((4.0, 7.0))
    assert positions == [3, 4, 5, 6, 7, 8]


def test_range_outside_returns_empty():
    idx = SkipIndex(chunk_id="c1", block_size=3)
    idx.build([make_entry(float(i)) for i in range(10)])
    assert idx.lookup((100.0, 200.0)) == []


def test_range_at_exact_boundary():
    idx = SkipIndex(chunk_id="c1", block_size=3)
    idx.build([make_entry(float(i)) for i in range(6)])
    positions = idx.lookup((2.0, 2.0))
    assert 2 in positions


def test_empty_build():
    idx = SkipIndex(chunk_id="c1", block_size=3)
    idx.build([])
    assert idx.lookup((0.0, 100.0)) == []
