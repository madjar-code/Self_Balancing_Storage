from __future__ import annotations
import time
from fastapi import APIRouter, Depends, HTTPException

from ..runtime import Runtime
from ..query.parser import QueryParseError
from .models import QueryRequest, QueryResponse


router = APIRouter()


def get_runtime() -> Runtime:
    raise NotImplementedError


@router.post("/query")
async def query(
    req: QueryRequest,
    runtime: Runtime = Depends(get_runtime),
) -> QueryResponse:
    t0 = time.time()
    try:
        results = await runtime.find(req.q)
    except QueryParseError as e:
        raise HTTPException(400, e.pretty())
    return QueryResponse(
        results=[
            {"ts": e.ts, "service": e.service, "level": e.level, "msg": e.msg, "fields": e.fields}
            for e in results
        ],
        rows_returned=len(results),
        duration_ms=(time.time() - t0) * 1000,
    )
