from __future__ import annotations
import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any

from self_balancing_storage.runtime import Runtime
from self_balancing_storage.types import LogEntry, Predicate, PredicateOp


@dataclass
class Phase:
    duration_sec: float
    writes_per_sec: int
    queries_per_sec: int
    services: list[str]
    write_trace_id: bool = False   # if True, writes include trace_id field


class WorkloadGenerator:
    def __init__(self, rt: Runtime, phases: list[Phase]):
        self.rt = rt
        self.phases = phases

    async def run(self) -> None:
        for i, phase in enumerate(self.phases):
            label = chr(ord("A") + i)
            print(
                f"\n=== Phase {label}: writes={phase.writes_per_sec}/s, "
                f"queries={phase.queries_per_sec}/s, trace_id={phase.write_trace_id} ===",
                flush=True,
            )
            await self._run_phase(phase)

    async def _run_phase(self, phase: Phase) -> None:
        end = time.time() + phase.duration_sec
        write_interval = 1.0 / phase.writes_per_sec if phase.writes_per_sec else 0
        query_interval = 1.0 / phase.queries_per_sec if phase.queries_per_sec else 0
        last_write = time.time()
        last_query = time.time()

        while time.time() < end:
            now = time.time()
            if write_interval and now - last_write >= write_interval:
                self._do_write(phase)
                last_write = now
            if query_interval and now - last_query >= query_interval:
                self._do_query(phase)
                last_query = now
            await asyncio.sleep(0.01)

    def _do_write(self, phase: Phase) -> None:
        service = random.choice(phase.services)
        fields: dict[str, Any] = {"user_id": random.randint(1, 10_000)}
        if phase.write_trace_id:
            fields["trace_id"] = f"trace-{random.randint(1, 1000)}"

        self.rt.append(LogEntry(
            ts=time.time(),
            service=service,
            level=random.choice(["INFO", "INFO", "INFO", "WARN", "ERROR"]),
            msg="event",
            fields=fields,
        ))

    def _do_query(self, phase: Phase) -> None:
        # Query by trace_id — chunks without this field are vetoed by schema check
        self.rt.find(Predicate(field="trace_id", op=PredicateOp.EQ, value="trace-42"))
