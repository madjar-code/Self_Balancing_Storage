import pytest

from self_balancing_storage.query.ast import And, Or
from self_balancing_storage.query.parser import parse, QueryParseError
from self_balancing_storage.types import Predicate, PredicateOp


def test_parse_simple_eq():
    q = parse('service="auth"')
    assert isinstance(q.where, Predicate)
    assert q.where.field == "service"
    assert q.where.value == "auth"


def test_parse_and():
    q = parse('service="auth" and level="ERROR"')
    assert isinstance(q.where, And)
    assert len(q.where.parts) == 2


def test_parse_or():
    q = parse('service="auth" or service="billing"')
    assert isinstance(q.where, Or)


def test_parse_label_set():
    q = parse('{service="auth", level="ERROR"}')
    assert isinstance(q.where, And)


def test_parse_pipeline():
    q = parse('service="auth" | last 1h | limit 100 | order by ts desc')
    assert q.time_range is not None
    assert q.limit == 100
    assert q.order_by == ("ts", "desc")


def test_parse_error_on_unterminated_string():
    with pytest.raises(QueryParseError):
        parse('service="auth')


def test_parse_in_list():
    q = parse('level in ["ERROR", "WARN"]')
    assert q.where.op == PredicateOp.IN
    assert q.where.value == ["ERROR", "WARN"]


def test_parse_exists():
    q = parse('user_id exists')
    assert q.where.op == PredicateOp.EXISTS


def test_parse_gt_produces_range_with_inf_upper_bound():
    """`ts > 100` becomes a RANGE predicate of (100.0, +inf)."""
    import math
    q = parse('ts > 100')
    assert isinstance(q.where, Predicate)
    assert q.where.field == "ts"
    assert q.where.op == PredicateOp.RANGE
    assert q.where.value == (100.0, math.inf)


def test_parse_le_produces_range_with_minus_inf_lower_bound():
    """`ts <= 200` becomes a RANGE predicate of (-inf, 200.0)."""
    import math
    q = parse('ts <= 200')
    assert q.where.op == PredicateOp.RANGE
    assert q.where.value == (-math.inf, 200.0)


def test_parse_ne_stays_eq_for_now():
    """`!=`, `=~`, `!~` remain EQ until full negation/regex support lands."""
    q = parse('service != "auth"')
    assert q.where.op == PredicateOp.EQ
    assert q.where.value == "auth"
