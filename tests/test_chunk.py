from typing import Any

from self_balancing_storage.chunk import _extract_field, make_matcher
from self_balancing_storage.types import LogEntry, Predicate, PredicateOp


def make_entry(**kwargs: Any) -> LogEntry:
    defaults: dict[str, Any] = dict(ts=1.0, service="a", level="INFO", msg="m", fields={})
    defaults.update(kwargs)
    return LogEntry(**defaults)


def test_extract_field_top_level():
    e = make_entry(ts=42.5, service="auth", level="ERROR", msg="hello")
    assert _extract_field(e, "ts") == 42.5
    assert _extract_field(e, "service") == "auth"
    assert _extract_field(e, "level") == "ERROR"
    assert _extract_field(e, "msg") == "hello"


def test_extract_field_inside_fields():
    e = make_entry(fields={"user_id": 7, "trace": "abc"})
    assert _extract_field(e, "user_id") == 7
    assert _extract_field(e, "trace") == "abc"
    assert _extract_field(e, "missing") is None


def test_make_matcher_eq():
    e = make_entry(service="auth")
    assert make_matcher(Predicate("service", PredicateOp.EQ, "auth"))(e) is True
    assert make_matcher(Predicate("service", PredicateOp.EQ, "billing"))(e) is False


def test_make_matcher_in_with_list():
    e = make_entry(level="ERROR")
    assert make_matcher(Predicate("level", PredicateOp.IN, ["INFO", "ERROR"]))(e) is True
    assert make_matcher(Predicate("level", PredicateOp.IN, ["WARN"]))(e) is False


def test_make_matcher_in_with_set():
    e = make_entry(level="ERROR")
    p = Predicate("level", PredicateOp.IN, frozenset({"ERROR", "WARN"}))
    assert make_matcher(p)(e) is True


def test_make_matcher_range_on_ts():
    e = make_entry(ts=42.5)
    assert make_matcher(Predicate("ts", PredicateOp.RANGE, (40.0, 50.0)))(e) is True
    assert make_matcher(Predicate("ts", PredicateOp.RANGE, (50.0, 60.0)))(e) is False


def test_make_matcher_range_on_field_with_none_value():
    e = make_entry(fields={})  # no field "x"
    p = Predicate("x", PredicateOp.RANGE, (0.0, 10.0))
    assert make_matcher(p)(e) is False


def test_make_matcher_exists():
    e = make_entry(fields={"trace": "abc"})
    assert make_matcher(Predicate("trace", PredicateOp.EXISTS))(e) is True
    assert make_matcher(Predicate("missing", PredicateOp.EXISTS))(e) is False
