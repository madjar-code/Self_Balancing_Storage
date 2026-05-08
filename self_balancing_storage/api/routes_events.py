from __future__ import annotations
import json
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from ..runtime import Runtime


router = APIRouter()


def get_runtime() -> Runtime:
    raise NotImplementedError


@router.get("/events")
async def events(runtime: Runtime = Depends(get_runtime)):
    async def event_generator():
        async with runtime.event_broker.subscribe() as queue:
            while True:
                event = await queue.get()
                yield {
                    "event": event.get("type", "message"),
                    "data": json.dumps(event),
                }
    return EventSourceResponse(event_generator())
