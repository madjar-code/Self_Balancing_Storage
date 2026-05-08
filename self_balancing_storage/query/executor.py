from __future__ import annotations
from typing import TYPE_CHECKING

from ..chunk import Chunk
from ..store import _pick_index   # reuse V1 field+op -> Index matcher
from ..types import LogEntry, Predicate, PredicateOp, IndexId, ChunkId
from .ast import And, Expr, Not, Or
from .planner import ExecutionPlan

if TYPE_CHECKING:
    from ..store import ChunkStore


def _evaluate_positions(
    chunk: "Chunk",
    expr: Expr,
    used_indexes: list[IndexId],
) -> set[int]:
    """Return positions in chunk.entries matching expr.

    Predicate leaves consult `_pick_index`: if an index is available, they
    use `idx.lookup`, otherwise a full scan via `Chunk._matches`. And/Or
    reduce to intersection/union over position sets, Not is a complement.
    `used_indexes` is mutated in place (executor aggregates and forwards
    it to the tracker).
    """
    if isinstance(expr, Predicate):
        idx = _pick_index(chunk, expr)
        if idx is None:
            return {
                i for i, e in enumerate(chunk.entries)
                if Chunk._matches(e, expr)
            }
        used_indexes.append(idx.index_id)
        positions = idx.lookup(expr.value)
        if idx.precise:
            return set(positions)
        # Bloom: positions = list(range(count)) → post-filter required
        return {
            p for p in positions
            if Chunk._matches(chunk.entries[p], expr)
        }

    if isinstance(expr, And):
        sets = [_evaluate_positions(chunk, p, used_indexes) for p in expr.parts]
        return set.intersection(*sets) if sets else set()

    if isinstance(expr, Or):
        sets = [_evaluate_positions(chunk, p, used_indexes) for p in expr.parts]
        return set.union(*sets) if sets else set()

    if isinstance(expr, Not):
        all_positions = set(range(len(chunk.entries)))
        return all_positions - _evaluate_positions(chunk, expr.expr, used_indexes)

    return set()


async def execute(
    plan: ExecutionPlan,
    store: "ChunkStore",
) -> tuple[list[LogEntry], list[ChunkId], list[IndexId]]:
    results: list[LogEntry] = []
    scanned: list[ChunkId] = []
    used_indexes: list[IndexId] = []

    for chunk_plan in plan.chunk_plans:
        chunk = chunk_plan.chunk
        scanned.append(chunk.header.chunk_id)
        positions = _evaluate_positions(chunk, chunk_plan.expr, used_indexes)
        for p in sorted(positions):  # arrival order = ts-ascending
            results.append(chunk.entries[p])

    if plan.order_by:
        field, direction = plan.order_by
        results.sort(
            key=lambda e: _extract_for_sort(e, field),
            reverse=(direction == "desc"),
        )

    if plan.limit is not None:
        results = results[:plan.limit]

    return results, scanned, used_indexes


def _extract_for_sort(entry: LogEntry, field: str):
    if field == "ts":
        return entry.ts
    if field == "service":
        return entry.service
    if field == "level":
        return entry.level
    return entry.fields.get(field, 0)
