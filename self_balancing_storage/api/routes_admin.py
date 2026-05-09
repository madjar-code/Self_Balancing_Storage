from __future__ import annotations
from fastapi import APIRouter, Depends

from ..runtime import Runtime


router = APIRouter()


def get_runtime() -> Runtime:
    raise NotImplementedError


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/engine/state")
async def engine_state(runtime: Runtime = Depends(get_runtime)) -> dict:
    return {
        "write_rate": runtime.tracker.write_rate(),
        "burst_ratio": runtime.tracker.burst_ratio(),
        "is_burst": runtime.tracker.is_burst(),
        "memory_pressure": runtime.tracker.memory_pressure(),
        "n_chunks": len(runtime.store.chunks),
        "n_sealed": sum(1 for c in runtime.store.chunks if c.header.state.value in ("sealed", "persisted")),
        "n_indexed": sum(1 for c in runtime.store.chunks if c.indexes),
    }


@router.get("/chunks")
async def chunks(runtime: Runtime = Depends(get_runtime)) -> list[dict]:
    return [
        {
            "chunk_id": c.header.chunk_id,
            "tier": c.tier.value,
            "state": c.header.state.value,
            "count": c.header.count,
            "ts_min": c.header.ts_min,
            "ts_max": c.header.ts_max,
            "services": list(c.header.services),
            "indexes": list(c.indexes.keys()),
            "indexes_on_disk": c.header.indexes_on_disk,
            "temperature": runtime.tracker.chunk_temperature(c.header.chunk_id),
        }
        for c in runtime.store.chunks
    ]

@router.get("/indexes")
async def indexes(runtime: Runtime = Depends(get_runtime)) -> list[dict]:
    out: list[dict] = []
    for chunk in runtime.store.chunks:
        for iid, idx in chunk.indexes.items():
            out.append({
                "index_id": iid,
                "chunk_id": chunk.header.chunk_id,
                "type": _index_type_name(idx),
                "field": idx.field,
                "op": idx.op.value if idx.op is not None else None,
                "memory_bytes": idx.memory_bytes,
                "usage": runtime.tracker.index_usage(iid),
                "last_used": runtime.tracker.index_last_used(iid),
                "status": "active",
            })
    for iid, d in runtime.engine.dropped_indexes.items():
        out.append({
            "index_id": iid,
            "chunk_id": d.chunk_id,
            "type": d.index_type.value,
            "field": d.field,
            "op": d.op.value,
            "memory_bytes": 0,
            "usage": 0,
            "last_used": None,
            "status": "dropped",
            "dropped_at": d.dropped_at,
            "prior_usage": d.prior_usage,
        })
    return out


def _index_type_name(idx) -> str:
    """Map an index instance to its public type string."""
    from ..indexes.hash_index import HashIndex
    from ..indexes.skip_index import SkipIndex
    from ..indexes.bloom import BloomIndex
    if isinstance(idx, HashIndex):
        return "hash"
    if isinstance(idx, SkipIndex):
        return "skip"
    if isinstance(idx, BloomIndex):
        return "bloom"
    return "unknown"


@router.get("/tracker/top-predicates")
async def top_predicates(
    k: int = 20,
    runtime: Runtime = Depends(get_runtime),
) -> list[dict]:
    return [
        {
            "field": p.field,
            "op": p.op.value,
            "value": p.value,
            "freq": freq,
        }
        for p, freq in runtime.tracker.top_predicates(k=k)
    ]
