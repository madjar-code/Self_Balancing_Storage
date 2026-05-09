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
    for info in runtime.engine.collect_index_infos():
        out.append({
            "index_id": info.index_id,
            "chunk_id": info.chunk_id,
            "type": info.index_type.value,
            "field": info.field,
            "op": info.op.value,
            "memory_bytes": info.memory_bytes,
            "usage": runtime.tracker.index_usage(info.index_id),
            "last_used": runtime.tracker.index_last_used(info.index_id),
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
