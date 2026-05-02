from self_balancing_storage.indexes.hash_index import HashIndex
from self_balancing_storage.types import LogEntry


def make_entry(service: str = "svc", **fields) -> LogEntry:
    return LogEntry(ts=0.0, service=service, level="INFO", msg="m", fields=fields)


def test_build_and_lookup_top_level_field():
    idx = HashIndex(chunk_id="c1", field="service")
    entries = [
        make_entry("auth"),
        make_entry("billing"),
        make_entry("auth"),
        make_entry("frontend"),
        make_entry("auth"),
    ]
    idx.build(entries)
    assert idx.lookup("auth") == [0, 2, 4]
    assert idx.lookup("billing") == [1]
    assert idx.lookup("missing") == []


def test_lookup_field_inside_fields_dict():
    idx = HashIndex(chunk_id="c1", field="user_id")
    entries = [
        make_entry(user_id=1),
        make_entry(user_id=2),
        make_entry(user_id=1),
    ]
    idx.build(entries)
    assert idx.lookup(1) == [0, 2]


def test_lookup_many_returns_union():
    idx = HashIndex(chunk_id="c1", field="service")
    entries = [make_entry("a"), make_entry("b"), make_entry("c"), make_entry("a")]
    idx.build(entries)
    assert idx.lookup_many(["a", "c"]) == [0, 2, 3]


def test_memory_bytes_is_positive():
    idx = HashIndex(chunk_id="c1", field="service")
    idx.build([make_entry("auth") for _ in range(100)])
    assert idx.memory_bytes > 0
