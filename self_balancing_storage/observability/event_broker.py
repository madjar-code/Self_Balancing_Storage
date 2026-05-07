from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


class EventBroker:
    """
    In-process pub/sub for engine events.

    Publishers (Engine, Runtime, Persistence) call publish() to broadcast events.
    Subscribers (e.g. SSE handler in Phase 18) call subscribe() to consume.
    Slow subscribers drop events instead of blocking publishers.
    """
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def publish(self, event: dict) -> None:
        """Sync - Engine can call without await. Slow subscribers lose events."""
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    @asynccontextmanager
    async def subscribe(self, max_buffer: int = 100) -> AsyncIterator[asyncio.Queue]:
        q: asyncio.Queue = asyncio.Queue(maxsize=max_buffer)
        self._subscribers.append(q)
        try:
            yield q
        finally:
            if q in self._subscribers:
                self._subscribers.remove(q)
