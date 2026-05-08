from __future__ import annotations
from typing import TYPE_CHECKING

from ..chunk import Chunk
from ..store import _pick_index   # reuse V1 field+op -> Index matcher
from ..types import LogEntry, Predicate, PredicateOp, IndexId, ChunkId, Tier
from .ast import And, Expr, Not, Or
from .planner import ExecutionPlan

if TYPE_CHECKING:
    from ..persistence.chunk_reader import ChunkReader
    from ..store import ChunkStore


def _evaluate_positions(
    chunk: "Chunk",
    entries: list[LogEntry],
    expr: Expr,
    used_indexes: list[IndexId],
) -> set[int]:
    if not entries:
        return set()

    if isinstance(expr, Predicate):
        idx = _pick_index(chunk, expr)
        if idx is None:
            return {
                i for i, e in enumerate(entries)
                if Chunk._matches(e, expr)
            }
        used_indexes.append(idx.index_id)
        positions = idx.lookup(expr.value)
        if idx.precise:
            return set(positions)
        return {
            p for p in positions
            if Chunk._matches(entries[p], expr)
        }

    if isinstance(expr, And):
        sets = [_evaluate_positions(chunk, entries, p, used_indexes) for p in expr.parts]
        return set.intersection(*sets) if sets else set()

    if isinstance(expr, Or):
        sets = [_evaluate_positions(chunk, entries, p, used_indexes) for p in expr.parts]
        return set.union(*sets) if sets else set()

    if isinstance(expr, Not):
        all_positions = set(range(len(entries)))
        return all_positions - _evaluate_positions(chunk, entries, expr.expr, used_indexes)

    return set()


async def execute(
    plan: ExecutionPlan,
    store: "ChunkStore",
    reader: "ChunkReader | None" = None,
) -> tuple[list[LogEntry], list[ChunkId], list[IndexId]]:
    results: list[LogEntry] = []
    scanned: list[ChunkId] = []
    used_indexes: list[IndexId] = []

    for chunk_plan in plan.chunk_plans:
        chunk = chunk_plan.chunk
        scanned.append(chunk.header.chunk_id)

        if chunk.tier == Tier.COLD and reader is not None:
            entries = await reader.load_entries(chunk.header.chunk_id)
        else:
            entries = chunk.entries

        positions = _evaluate_positions(chunk, entries, chunk_plan.expr, used_indexes)
        for p in sorted(positions):
            results.append(entries[p])

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
