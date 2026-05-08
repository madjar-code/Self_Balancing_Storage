from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ..types import Predicate, PredicateOp
from .ast import And, Expr, Not, Or, Query

if TYPE_CHECKING:
    from ..chunk import Chunk
    from ..store import ChunkStore


@dataclass
class ChunkPlan:
    chunk: "Chunk"
    expr: Expr


@dataclass
class ExecutionPlan:
    chunk_plans: list[ChunkPlan]
    limit: int | None
    order_by: tuple[str, Literal["asc", "desc"]] | None


def plan_query(query: Query, store: "ChunkStore") -> ExecutionPlan:
    """Build execution plan for query. Filters chunks down to candidates."""
    plans: list[ChunkPlan] = []
    for chunk in store.chunks:
        # 1) Filter by time_range
        if query.time_range is not None:
            lo, hi = query.time_range
            if chunk.header.ts_max < lo or chunk.header.ts_min > hi:
                continue
        # 2) Filter by schema heuristic
        if not _chunk_could_match(chunk, query.where):
            continue
        plans.append(ChunkPlan(chunk=chunk, expr=query.where))
    return ExecutionPlan(chunk_plans=plans, limit=query.limit, order_by=query.order_by)


def _chunk_could_match(chunk: "Chunk", expr: Expr) -> bool:
    """Quick check: does this chunk's schema allow the predicate at all?"""
    if isinstance(expr, Predicate):
        if expr.op == PredicateOp.EXISTS:
            return expr.field in chunk.header.schema_sketch
        top_level = {"ts", "service", "level", "msg"}
        if expr.field in top_level:
            return True
        return expr.field in chunk.header.schema_sketch
    if isinstance(expr, And):
        return all(_chunk_could_match(chunk, p) for p in expr.parts)
    if isinstance(expr, Or):
        return any(_chunk_could_match(chunk, p) for p in expr.parts)
    if isinstance(expr, Not):
        return True  # can't easily prune NOT
    return True
