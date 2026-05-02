import random

from self_balancing_storage.indexes.bloom import BloomFilter, BloomIndex
from self_balancing_storage.types import LogEntry


def test_added_values_always_match():
    bf = BloomFilter(n_items=1000, fp_rate=0.01)
    values = [f"trace_{i}".encode() for i in range(1000)]
    for v in values:
        bf.add(v)
    for v in values:
        assert v in bf  # no false negatives ever


def test_false_positive_rate_within_bound():
    random.seed(42)
    bf = BloomFilter(n_items=1000, fp_rate=0.01)
    added = {f"in_{i}".encode() for i in range(1000)}
    for v in added:
        bf.add(v)

    queries = [f"out_{random.randint(0, 10**9)}".encode() for _ in range(10_000)]
    fp = sum(1 for q in queries if q in bf and q not in added)
    rate = fp / len(queries)
    # tolerant bound around the 1% target
    assert rate <= 0.03


def test_bloom_index_lookup_returns_full_range_or_empty():
    idx = BloomIndex(chunk_id="c1", field="trace_id", n_items=10)
    entries = [
        LogEntry(ts=0, service="s", level="I", msg="m", fields={"trace_id": f"t{i}"})
        for i in range(5)
    ]
    idx.build(entries)
    # added trace_id → bloom returns the whole chunk (post-filter required)
    assert idx.lookup("t1") == list(range(5))
    # never added trace_id → bloom returns []
    assert idx.lookup("definitely_not_there_xyz") == []
