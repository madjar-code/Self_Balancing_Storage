from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING

from ..chunk import Chunk, make_matcher
from ..store import _pick_index
from ..types import (
    LogEntry,
    Predicate,
    IndexId,
    ChunkId,
    Tier,
)
from .ast import And, Expr, Not, Or
from .planner import ExecutionPlan

if TYPE_CHECKING:
    from ..persistence.chunk_reader import ChunkReader
    from ..store import ChunkStore


def _evaluate_positions(
    chunk: "Chunk",
    entries: list[LogEntry] | None,
    expr: Expr,
    used_indexes: list[IndexId],
) -> set[int] | None:
    if isinstance(expr, Predicate):
        idx = _pick_index(chunk, expr)
        if idx is None:
            if entries is None:
                return None
            match = make_matcher(expr)
            return {i for i, e in enumerate(entries) if match(e)}
        used_indexes.append(idx.index_id)
        positions = idx.lookup(expr.value)
        if idx.precise:
            return set(positions)
        if not positions:
            return set()
        if entries is None:
            return None
        if not entries:
            return set()
        match = make_matcher(expr)
        return {p for p in positions if match(entries[p])}

    if isinstance(expr, And):
        sub: list[set[int]] = []
        for p in expr.parts:
            r = _evaluate_positions(chunk, entries, p, used_indexes)
            if r is None:
                return None
            sub.append(r)
        return set.intersection(*sub) if sub else set()

    if isinstance(expr, Or):
        sub = []
        for p in expr.parts:
            r = _evaluate_positions(chunk, entries, p, used_indexes)
            if r is None:
                return None
            sub.append(r)
        return set.union(*sub) if sub else set()

    if isinstance(expr, Not):
        inner = _evaluate_positions(chunk, entries, expr.expr, used_indexes)
        if inner is None:
            return None
        return set(range(chunk.header.count)) - inner

    return set()


async def execute(
    plan: ExecutionPlan,
    store: "ChunkStore",
    reader: "ChunkReader | None" = None,
) -> tuple[list[LogEntry], list[ChunkId], list[IndexId]]:
    results: list[LogEntry] = []
    scanned: list[ChunkId] = []
    used_indexes: list[IndexId] = []

    pending: list[dict] = []

    # Pass 1: try to answer each chunk using only indexes; mark which need
    # entries from disk.
    for chunk_plan in plan.chunk_plans:
        chunk = chunk_plan.chunk
        scanned.append(chunk.header.chunk_id)

        chunk_used: list[IndexId] = []
        positions = _evaluate_positions(chunk, None, chunk_plan.expr, chunk_used)

        needs_entries = positions is None or bool(positions)
        load_from_disk = (
            needs_entries
            and chunk.tier == Tier.COLD
            and not chunk.entries
            and reader is not None
        )

        pending.append({
            "chunk": chunk,
            "expr": chunk_plan.expr,
            "positions": positions,
            "chunk_used": chunk_used,
            "needs_reeval": positions is None,
            "load_from_disk": load_from_disk,
            "entries": None,
        })

    # Pass 2: load all required cold chunks in parallel.
    to_load_idx = [i for i, p in enumerate(pending) if p["load_from_disk"]]
    if to_load_idx and reader is not None:
        loaded = await asyncio.gather(*[
            reader.load_entries(pending[i]["chunk"].header.chunk_id)
            for i in to_load_idx
        ])
        for i, entries in zip(to_load_idx, loaded):
            pending[i]["entries"] = entries

    # Pass 3: re-evaluate where needed and materialize results.
    for p in pending:
        chunk = p["chunk"]
        entries = p["entries"] if p["entries"] is not None else chunk.entries
        positions = p["positions"]
        chunk_used = p["chunk_used"]

        if p["needs_reeval"]:
            chunk_used = []
            positions = _evaluate_positions(chunk, entries, p["expr"], chunk_used)

        used_indexes.extend(chunk_used)
        for pos in sorted(positions):
            results.append(entries[pos])

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
