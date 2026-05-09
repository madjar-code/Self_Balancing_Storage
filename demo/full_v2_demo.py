from __future__ import annotations
import asyncio
import logging
import random
import shutil
import time
from collections import Counter
from pathlib import Path
from typing import Any

from self_balancing_storage.config import Config
from self_balancing_storage.runtime import Runtime
from self_balancing_storage.types import LogEntry, Predicate, PredicateOp


logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(name)s] %(message)s")


# Isolated data dir so the demo never picks up stale chunks from previous
# experiments or from `./data/` polluted by older test runs.
DEMO_DATA_DIR = Path("./data/demo")

SERVICES = ["auth-api", "billing", "frontend", "notification"]
SERVICE_WEIGHTS = [40, 30, 20, 10]
LEVELS = ["INFO", "WARN", "ERROR"]
LEVEL_WEIGHTS = [80, 15, 5]
HOT_TRACES = [f"hot-trace-{i}" for i in range(10)]

# Fixed RANGE so MisraGries accumulates frequency on a single Predicate
# (the parser currently emits the same value for every RANGE query, but the
# demo bypasses the parser and uses the Predicate API directly).
TS_RANGE_VALUE = (1.0, 1e10)


def random_entry(with_trace_id: bool) -> LogEntry:
    fields: dict[str, Any] = {"user_id": random.randint(1, 100)}
    if with_trace_id:
        # 30% reuse a hot trace_id (so tracker top-K notices recurrence),
        # 70% unique noise to mimic high-cardinality real traffic.
        if random.random() < 0.3:
            fields["trace_id"] = random.choice(HOT_TRACES)
        else:
            fields["trace_id"] = f"trace-{random.randint(1, 100000)}"
    return LogEntry(
        ts=time.time(),
        service=random.choices(SERVICES, weights=SERVICE_WEIGHTS)[0],
        level=random.choices(LEVELS, weights=LEVEL_WEIGHTS)[0],
        msg="m",
        fields=fields,
    )


async def phase_a_warmup(rt: Runtime, duration: float) -> None:
    print(f"\n=== Phase A: warmup writes, no trace_id, no queries ({duration:.0f}s) ===")
    end = time.time() + duration
    n = 0
    while time.time() < end:
        await rt.try_append(random_entry(with_trace_id=False))
        n += 1
        await asyncio.sleep(0.04)
    print(f"  wrote {n} entries")


async def phase_b_diverse_queries(rt: Runtime, duration: float) -> None:
    print(
        f"\n=== Phase B: writes + diverse queries "
        f"(service / level / trace_id / AND / ts RANGE) ({duration:.0f}s) ==="
    )
    end = time.time() + duration
    n_writes = 0
    n_queries: Counter[str] = Counter()
    last_query = 0.0
    while time.time() < end:
        await rt.try_append(random_entry(with_trace_id=True))
        n_writes += 1
        if time.time() - last_query > 0.15:
            kind = random.choice(["service", "level", "trace_id", "and", "ts_range"])
            try:
                if kind == "service":
                    await rt.find('service="auth-api"')
                elif kind == "level":
                    await rt.find('level="ERROR"')
                elif kind == "trace_id":
                    await rt.find(f'trace_id="{random.choice(HOT_TRACES)}"')
                elif kind == "and":
                    await rt.find('service="auth-api" and level="ERROR"')
                else:
                    # ts RANGE goes through the Predicate API: parser maps `>`/`<`
                    # to EQ in the V2 prototype, so RANGE on `ts` is constructed
                    # by hand to exercise the SkipIndex path.
                    await rt.find(Predicate("ts", PredicateOp.RANGE, TS_RANGE_VALUE))
                n_queries[kind] += 1
            except Exception as e:
                print(f"  query {kind!r} failed: {e}")
            last_query = time.time()
        await asyncio.sleep(0.04)
    print(f"  wrote {n_writes} entries, queries: {dict(n_queries)}")


async def phase_c_burst(rt: Runtime, duration: float) -> None:
    print(f"\n=== Phase C: WRITE BURST (10x rate, no queries) ({duration:.0f}s) ===")
    end = time.time() + duration
    n = 0
    while time.time() < end:
        for _ in range(10):
            await rt.try_append(random_entry(with_trace_id=True))
            n += 1
        await asyncio.sleep(0.05)
    print(f"  wrote {n} entries (burst)")


async def phase_d_post_burst(rt: Runtime, duration: float) -> None:
    print(f"\n=== Phase D: post-burst, queries resume ({duration:.0f}s) ===")
    end = time.time() + duration
    n_writes, n_queries = 0, 0
    last_query = 0.0
    while time.time() < end:
        await rt.try_append(random_entry(with_trace_id=True))
        n_writes += 1
        if time.time() - last_query > 0.2:
            try:
                await rt.find(f'trace_id="{random.choice(HOT_TRACES)}"')
                await rt.find('service="auth-api"')
                await rt.find(Predicate("ts", PredicateOp.RANGE, TS_RANGE_VALUE))
                n_queries += 3
            except Exception:
                pass
            last_query = time.time()
        await asyncio.sleep(0.08)
    print(f"  wrote {n_writes} entries, ran {n_queries} queries")


async def phase_e_quiet(rt: Runtime, duration: float) -> None:
    print(
        f"\n=== Phase E: QUIET (no writes, no queries -> chunks cool down, "
        f"indexes drop on idle) ({duration:.0f}s) ==="
    )
    # No writes, no queries. Engine ticks decay temperatures via cool_down,
    # idle indexes cross idle_drop_sec and are dropped, demoted chunks pile up.
    end = time.time() + duration
    interval = 10.0
    while time.time() < end:
        await asyncio.sleep(min(interval, end - time.time()))
        n_active = sum(len(c.indexes) for c in rt.store.chunks)
        n_dropped = len(rt.engine.dropped_indexes)
        n_cold = sum(1 for c in rt.store.chunks if c.tier.value == "cold")
        elapsed = duration - max(0.0, end - time.time())
        print(
            f"  t+{elapsed:>4.0f}s: active_indexes={n_active}, "
            f"dropped={n_dropped}, cold_chunks={n_cold}"
        )


async def phase_f_resume(rt: Runtime, duration: float) -> None:
    print(
        f"\n=== Phase F: queries return -> cold chunks promote, dropped "
        f"indexes restore from cooldown ({duration:.0f}s) ==="
    )
    end = time.time() + duration
    last_progress = time.time()
    n_queries = 0
    while time.time() < end:
        try:
            await rt.find(f'trace_id="{random.choice(HOT_TRACES)}"')
            await rt.find('service="auth-api"')
            await rt.find('level="ERROR"')
            await rt.find(Predicate("ts", PredicateOp.RANGE, TS_RANGE_VALUE))
            n_queries += 4
        except Exception as e:
            print(f"  query failed: {e}")
        if time.time() - last_progress > 5.0:
            n_active = sum(len(c.indexes) for c in rt.store.chunks)
            n_dropped = len(rt.engine.dropped_indexes)
            n_cold = sum(1 for c in rt.store.chunks if c.tier.value == "cold")
            elapsed = duration - max(0.0, end - time.time())
            print(
                f"  t+{elapsed:>4.0f}s: queries={n_queries}, "
                f"active_indexes={n_active}, dropped={n_dropped}, cold_chunks={n_cold}"
            )
            last_progress = time.time()
        await asyncio.sleep(0.1)
    print(f"  ran {n_queries} queries total")


def _short_index_id(iid: str) -> str:
    """Strip chunk_id prefix: 'chunk_000552_xxx:bloom:trace_id' becomes 'bloom:trace_id'."""
    parts = iid.split(":", 2)
    return ":".join(parts[1:]) if len(parts) > 1 else iid


def snapshot(rt: Runtime, label: str) -> None:
    chunks = rt.store.chunks
    n = len(chunks)
    n_hot = sum(1 for c in chunks if c.tier.value == "hot")
    n_cold = sum(1 for c in chunks if c.tier.value == "cold")
    n_open = sum(1 for c in chunks if c.header.state.value == "open")
    n_sealed = sum(1 for c in chunks if c.header.state.value == "sealed")
    n_persisted = sum(1 for c in chunks if c.header.state.value == "persisted")

    idx_by_type: Counter[str] = Counter()
    for c in chunks:
        for iid in c.indexes:
            for t in ("hash", "skip", "bloom"):
                if f":{t}:" in iid:
                    idx_by_type[t] += 1
                    break
    n_with_idx = sum(1 for c in chunks if c.indexes)
    n_dropped = len(rt.engine.dropped_indexes)

    print(f"\n--- snapshot: {label} ---")
    print(
        f"  chunks: {n} (hot={n_hot}, cold={n_cold} | "
        f"open={n_open}, sealed={n_sealed}, persisted={n_persisted})"
    )
    print(
        f"  active indexes: {sum(idx_by_type.values())} across {n_with_idx} chunks "
        f"(hash={idx_by_type.get('hash', 0)}, "
        f"skip={idx_by_type.get('skip', 0)}, "
        f"bloom={idx_by_type.get('bloom', 0)})"
    )
    print(f"  dropped indexes (in cooldown): {n_dropped}")
    print(
        f"  tracker: write_rate={rt.tracker.write_rate():.1f}/s, "
        f"burst_ratio={rt.tracker.burst_ratio():.2f}, "
        f"mem_pressure={rt.tracker.memory_pressure():.2f}"
    )
    top = rt.tracker.top_predicates(5)
    if top:
        print("  top predicates:")
        for p, freq in top:
            print(f"    {p.field} {p.op.value} {p.value!r}  ({freq})")


async def main() -> None:
    if DEMO_DATA_DIR.exists():
        shutil.rmtree(DEMO_DATA_DIR)

    config = Config(
        data_path=DEMO_DATA_DIR,
        cold_path=DEMO_DATA_DIR,
        wal_path=DEMO_DATA_DIR / "wal" / "current.log",
        # Smaller chunks => more of them => more interesting per-chunk picture.
        chunk_max_seconds=8.0,
        chunk_max_entries=500,
        tick_interval_sec=2.0,
        build_threshold_freq=3,
        # alpha=0.2: ~22s for an idle temp to decay below 0.1, ~3-4 queries
        # to recover above 0.5. Fits Phase E (35s) and Phase F (18s).
        ema_alpha_chunk_temp=0.2,
        demote_idle_sec=20.0,
        idle_drop_sec=20.0,
        cooldown_sec=180.0,
        min_roi=20.0,
        wal_fsync_interval_ms=50,
        write_window_sec=10,
    )

    rt = Runtime(config)
    await rt.start()

    try:
        snapshot(rt, "start")
        await phase_a_warmup(rt, 12)
        snapshot(rt, "after Phase A")
        await phase_b_diverse_queries(rt, 25)
        snapshot(rt, "after Phase B")
        await phase_c_burst(rt, 10)
        snapshot(rt, "after Phase C")
        await phase_d_post_burst(rt, 12)
        snapshot(rt, "after Phase D")
        await phase_e_quiet(rt, 35)
        snapshot(rt, "after Phase E (quiet)")
        await phase_f_resume(rt, 18)
        snapshot(rt, "after Phase F (resume)")

        print("\n=== INTERESTING CHUNKS (with indexes or cold) ===")
        shown = 0
        for chunk in rt.store.chunks:
            if not chunk.indexes and chunk.tier.value == "hot":
                continue
            indexes = ", ".join(_short_index_id(iid) for iid in chunk.indexes) or "-"
            has_trace = "trace_id" in chunk.header.schema_sketch
            print(
                f"  [{chunk.tier.value:5s}] [{chunk.header.state.value:10s}] "
                f"{chunk.header.chunk_id} count={chunk.header.count:4d} "
                f"trace_id_in_schema={has_trace} indexes=[{indexes}]"
            )
            shown += 1
        if shown == 0:
            print("  (none)")
    finally:
        await rt.stop()


if __name__ == "__main__":
    asyncio.run(main())
