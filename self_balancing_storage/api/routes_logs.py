from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException

from ..runtime import Runtime
from ..types import LogEntry
from .models import LogEntryIn


router = APIRouter()


def get_runtime() -> Runtime:
    raise NotImplementedError("override in app.py")


@router.post("/logs", status_code=202)
async def ingest(
    payload: LogEntryIn | list[LogEntryIn],
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    items = [payload] if isinstance(payload, LogEntryIn) else payload
    accepted = 0
    for item in items:
        entry = LogEntry(
            ts=item.ts, service=item.service, level=item.level,
            msg=item.msg, fields=dict(item.fields),
        )
        if not await runtime.try_append(entry):
            raise HTTPException(
                status_code=429,
                detail="ingestion queue full",
                headers={"Retry-After": "1"},
            )
        accepted += 1
    return {"accepted": accepted}
