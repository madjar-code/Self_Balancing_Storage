from __future__ import annotations
import asyncio
import logging
import time

from self_balancing_storage.config import Config
from self_balancing_storage.runtime import Runtime, runtime

from .workload import Phase, WorkloadGenerator


_STD_LOG_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message", "asctime",
}


class ExtraFormatter(logging.Formatter):
    """Render logging.extra={...} kwargs inline so structured engine logs are visible."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {k: v for k, v in record.__dict__.items() if k not in _STD_LOG_ATTRS}
        if not extras:
            return base
        rendered = " ".join(f"{k}={v}" for k, v in extras.items())
        return f"{base} {rendered}"


_handler = logging.StreamHandler()
_handler.setFormatter(ExtraFormatter("%(asctime)s [%(name)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler], force=True)


async def _periodic_snapshot(rt: Runtime, started_at: float, interval_sec: float = 5.0) -> None:
    """Print a compact human-readable snapshot of engine state at a fixed cadence."""
    while True:
        await asyncio.sleep(interval_sec)
        elapsed = time.time() - started_at
        top = rt.tracker.top_predicates(k=1)
        if top:
            p, f = top[0]
            top_str = f"{p.field}|{p.op.value}={p.value!r}({f})"
        else:
            top_str = "(no queries yet)"
        n_chunks = len(rt.store.chunks)
        n_sealed = sum(1 for c in rt.store.chunks if c.header.state.value == "sealed")
        n_indexed = sum(1 for c in rt.store.chunks if c.indexes)
        print(
            f"  [t={elapsed:>5.1f}s] writes={rt.tracker.write_rate():>4.1f}/s "
            f"top={top_str:<30s} "
            f"chunks={n_chunks} (sealed={n_sealed}, indexed={n_indexed})",
            flush=True,
        )


async def main() -> None:
    # Shorter intervals for the demo
    config = Config(
        tick_interval_sec=2.0,
        chunk_max_seconds=10.0,
        chunk_max_entries=200,
        build_threshold_freq=3,
        write_window_sec=10,
    )

    phases = [
        # A: writes only, NO trace_id, no queries
        Phase(duration_sec=20, writes_per_sec=20, queries_per_sec=0,
              services=["auth-api", "billing", "frontend"], write_trace_id=False),
        # B: writes WITH trace_id, queries by trace_id
        Phase(duration_sec=40, writes_per_sec=20, queries_per_sec=5,
              services=["auth-api", "billing", "frontend"], write_trace_id=True),
        # C: same as B, observation
        Phase(duration_sec=20, writes_per_sec=20, queries_per_sec=5,
              services=["auth-api", "billing", "frontend"], write_trace_id=True),
    ]

    print(
        "Per-chunk divergence demo: same logical 'table', different chunks get\n"
        "different index strategies based on observed workload.\n",
        flush=True,
    )

    async with runtime(config) as rt:
        started_at = time.time()
        snapshot_task = asyncio.create_task(_periodic_snapshot(rt, started_at))
        try:
            gen = WorkloadGenerator(rt, phases)
            await gen.run()
        finally:
            snapshot_task.cancel()

        # Final report — group SEALED chunks by phase via trace_id presence in schema.
        # OPEN chunks have an empty schema_sketch (built only at seal), so they're
        # labelled separately rather than misattributed to phase A.
        print("\n=== FINAL STATE ===", flush=True)
        for chunk in rt.store.chunks:
            indexes_str = ", ".join(chunk.indexes) if chunk.indexes else "NONE"
            if chunk.header.state.value != "sealed":
                phase = "open"
            elif "trace_id" in chunk.header.schema_sketch:
                phase = "B/C"
            else:
                phase = "A"
            print(
                f"  [phase {phase:>4s}] {chunk.header.chunk_id} "
                f"state={chunk.header.state.value} "
                f"count={chunk.header.count} "
                f"indexes=[{indexes_str}]",
                flush=True,
            )

        sealed = [c for c in rt.store.chunks if c.header.state.value == "sealed"]
        phase_a = [c for c in sealed if "trace_id" not in c.header.schema_sketch]
        phase_bc = [c for c in sealed if "trace_id" in c.header.schema_sketch]
        a_clean = all(not c.indexes for c in phase_a)
        bc_indexed = sum(1 for c in phase_bc if c.indexes)
        divergent = a_clean and len(phase_bc) > 0 and bc_indexed == len(phase_bc)

        print(
            f"\nPhase A chunks without indexes:   {sum(1 for c in phase_a if not c.indexes)}/{len(phase_a)}",
            flush=True,
        )
        print(
            f"Phase B/C sealed chunks indexed:  {bc_indexed}/{len(phase_bc)}",
            flush=True,
        )
        print(f"\nDivergence detected: {divergent}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
