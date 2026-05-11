"""
Drive a running SBS backend with a phased query workload so the engine
emits decisions and the UI's Decisions feed and Indexes page come alive.

This script does NOT write logs. Run scripts/populate_ui.py in parallel
for that.

Phases (cycle forever, ~115s per cycle):
  1. hot-set-A   - 30s of EQ queries on service= and level=.
                   Builds HASH indexes on those fields.
  2. hot-set-B   - 30s of EQ queries on tenant=, region=, host=, shard=.
                   Builds HASH indexes on those fields too.
  3. range-ts    - 20s of RANGE queries on ts (`ts > X`, `ts <= Y`).
                   Builds SKIP indexes on ts. The cutoffs are stable so
                   predicate frequency accumulates.
  4. in-list     - 20s of IN-list queries (`level in [...]`, etc).
                   Exercises the IN op via HashIndex.lookup_many.
  5. quiet       - 15s with no queries. Lets predicate counters and
                   index_usage decay.

Selecting which chunks to heat with --chunks:
  By default ('all'), every query touches every chunk because no time
  filter is applied - heat spreads evenly.
  Pass indices to target specific chunks. Indices count from the newest
  (0 = newest, 1 = second newest, ...). The script periodically refreshes
  the chunks list from /api/chunks and rotates through your selection.

  Examples:
    --chunks all          (default) hit every chunk
    --chunks 0            only the newest chunk
    --chunks 0,1,2        three newest chunks
    --chunks 5,8          two specific chunks by recency
  Each targeted query gets a `| between "<ts_min>" and "<ts_max>"` clause
  so the planner only scans that one chunk.

Notes on what you will and will not see with default backend config:
  * build_index decisions: yes, within ~10s of each phase start.
  * burst events: no - this script does not write, so no rate spike.
  * tier_change (promote/demote): not in one cycle. Default config has
    demote_idle_sec=300s, demote_grace_sec=30s, idle_drop_sec=600s. To
    see those quickly, run a backend with a custom Config that lowers
    those values.

Usage:
  1. Start the backend in another terminal:
       uv run python -m self_balancing_storage.main
  2. Optionally, in a third terminal, run the writer:
       uv run python scripts/populate_ui.py
  3. Run this:
       uv run python scripts/simulate_load.py
       uv run python scripts/simulate_load.py --chunks 0
       uv run python scripts/simulate_load.py --chunks 0,1,2
"""
from __future__ import annotations

import argparse
import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx


HOT_SET_A = [
    'service="auth-api"',
    'service="billing"',
    'service="frontend"',
    'level="ERROR"',
    'level="WARN"',
]

HOT_SET_B = [
    'tenant="t007"',
    'tenant="t017"',
    'region="eu-west"',
    'region="us-east"',
    'host="host-001"',
    'shard="sh-3"',
]

"""
Stable RANGE queries on `ts`. Same predicate value repeats across calls so
predicate frequency accumulates and the engine builds a SkipIndex on `ts`.
The cutoffs are deliberately generous so any real entry matches.
"""
RANGE_SET = [
    'ts > 1700000000',
    'ts >= 1750000000',
    'ts < 2000000000',
    'ts <= 1900000000',
]

"""
IN-list queries on multiple values per field. Still HASH-indexed but
exercises the IN op path in the parser and the lookup_many code path on
HashIndex.
"""
IN_SET = [
    'service in ["auth-api", "billing"]',
    'level in ["ERROR", "WARN"]',
    'tenant in ["t007", "t017", "t023"]',
    'region in ["eu-west", "us-east"]',
]


"""Phase registry: name -> (queries, qps, default_duration_seconds)."""
PHASES: dict[str, tuple[list[str] | None, int, int]] = {
    "hot-set-A": (HOT_SET_A, 5, 30),
    "hot-set-B": (HOT_SET_B, 5, 30),
    "range-ts":  (RANGE_SET, 5, 20),
    "in-list":   (IN_SET,    5, 20),
    "quiet":     (None,      0, 15),
}


@dataclass
class State:
    """Shared knobs the director mutates while loops keep running."""
    qps: float = 0.0
    queries: list[str] = field(default_factory=lambda: HOT_SET_A)
    phase: str = "starting"
    queries_run: int = 0
    """'all' or list[int] of chunk indices (0 = newest, 1 = next newest, ...)."""
    target: str | list[int] = "all"
    """Latest /api/chunks snapshot, sorted newest-first."""
    chunks_newest_first: list[dict[str, Any]] = field(default_factory=list)
    rotate_idx: int = 0
    """Configured by the user; director cycles through this list forever."""
    enabled_phases: list[str] = field(default_factory=list)
    """If >0, overrides every phase's default duration (seconds)."""
    phase_duration_override: float = 0.0
    """Per-request timeout for /api/query (seconds)."""
    request_timeout: float = 10.0
    """Override default qps if >0."""
    qps_override: float = 0.0


def parse_phases_arg(arg: str) -> list[str]:
    """`all` (default) keeps the full cycle; otherwise comma list of phase names."""
    if arg == "all":
        return list(PHASES.keys())
    items = [s.strip() for s in arg.split(",") if s.strip()]
    if not items:
        raise argparse.ArgumentTypeError("--phases cannot be empty")
    for it in items:
        if it not in PHASES:
            valid = ", ".join(PHASES.keys())
            raise argparse.ArgumentTypeError(
                f"unknown phase {it!r}. valid: {valid}"
            )
    return items


def parse_chunks_arg(arg: str) -> str | list[int]:
    if arg == "all":
        return "all"
    try:
        items = [int(s.strip()) for s in arg.split(",") if s.strip()]
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"--chunks must be 'all' or a comma list of non-negative ints (got {arg!r})",
        ) from e
    if not items or any(i < 0 for i in items):
        raise argparse.ArgumentTypeError(
            f"--chunks indices must be non-negative ints (got {arg!r})",
        )
    return items


def chunk_time_range_clause(chunk: dict[str, Any]) -> str | None:
    """
    Build a `between` clause that overlaps ONLY this chunk, never neighbors.

    We center the window on the chunk's mid-timestamp with a 1ms half-span.
    Neighbors do not span the middle of this chunk, so the planner's range
    filter excludes them even when chunks share exact boundary timestamps.
    """
    ts_min = chunk.get("ts_min")
    ts_max = chunk.get("ts_max")
    if not isinstance(ts_min, (int, float)) or not isinstance(ts_max, (int, float)):
        return None
    if ts_max <= 0 or ts_min <= 0:
        return None
    mid = (ts_min + ts_max) / 2
    lo = datetime.fromtimestamp(mid - 0.001).isoformat()
    hi = datetime.fromtimestamp(mid + 0.001).isoformat()
    return f'between "{lo}" and "{hi}"'


def pick_target_chunk(state: State) -> dict[str, Any] | None:
    """Round-robin through state.target indices; returns None if not resolvable."""
    if state.target == "all" or not isinstance(state.target, list):
        return None
    if not state.chunks_newest_first:
        return None
    idx_in_target = state.rotate_idx % len(state.target)
    state.rotate_idx += 1
    chunk_index = state.target[idx_in_target]
    if chunk_index >= len(state.chunks_newest_first):
        return None
    return state.chunks_newest_first[chunk_index]


async def chunks_refresher(client: httpx.AsyncClient, state: State) -> None:
    """Poll /api/chunks every 3s, sort newest-first by ts_min."""
    while True:
        try:
            resp = await client.get("/api/chunks", timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                state.chunks_newest_first = sorted(
                    data,
                    key=lambda c: c.get("ts_min", 0.0),
                    reverse=True,
                )
        except httpx.HTTPError:
            pass
        await asyncio.sleep(3.0)


async def querier_loop(
    client: httpx.AsyncClient,
    rng: random.Random,
    state: State,
) -> None:
    while True:
        qps = state.qps
        if qps <= 0:
            await asyncio.sleep(0.2)
            continue
        interval = 1.0 / qps
        base = rng.choice(state.queries)

        if state.target == "all":
            q = base
        else:
            chunk = pick_target_chunk(state)
            if chunk is None:
                await asyncio.sleep(0.2)
                continue
            clause = chunk_time_range_clause(chunk)
            if clause is None:
                await asyncio.sleep(0.2)
                continue
            q = f"{base} | {clause}"

        try:
            resp = await client.post(
                "/api/query", json={"q": q}, timeout=state.request_timeout,
            )
            if resp.status_code == 200:
                state.queries_run += 1
            else:
                print(f"  query {resp.status_code}: q={q!r}  body={resp.text[:200]}")
        except httpx.HTTPError as e:
            print(f"  query failed [{type(e).__name__}]: {e!r}  q={q!r}")
        await asyncio.sleep(interval)


async def reporter_loop(state: State) -> None:
    started = time.time()
    while True:
        await asyncio.sleep(2.0)
        elapsed = time.time() - started
        target_repr = (
            "all" if state.target == "all"
            else f"chunks={state.target} ({len(state.chunks_newest_first)} known)"
        )
        print(
            f"  +{elapsed:5.0f}s   phase: {state.phase:<12}   "
            f"queries {state.queries_run:>5}   target: {target_repr}"
        )


async def director(state: State) -> None:
    cycle = 0
    while True:
        cycle += 1
        print(f"\n=== Cycle {cycle} ===")
        for name in state.enabled_phases:
            queries, default_qps, default_duration = PHASES[name]
            state.phase = name
            if queries is not None:
                state.queries = queries
            state.qps = state.qps_override if state.qps_override > 0 else default_qps
            duration = (
                state.phase_duration_override
                if state.phase_duration_override > 0
                else default_duration
            )
            await asyncio.sleep(duration)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate a phased query workload against an SBS backend.",
    )
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument(
        "--chunks",
        type=parse_chunks_arg,
        default="all",
        help="Which chunks to query: 'all' (default), or 0-based indices "
             "from newest, e.g. '0' or '0,1,2'.",
    )
    parser.add_argument(
        "--phases",
        type=parse_phases_arg,
        default="all",
        help="Which phases to cycle through. 'all' (default) runs every "
             f"phase. Or comma list from: {', '.join(PHASES.keys())}. "
             "Pass a single name to loop only that phase, e.g. "
             "'--phases range-ts'.",
    )
    parser.add_argument(
        "--phase-duration",
        type=float,
        default=0.0,
        help="Override the duration (seconds) of every selected phase. "
             "Default: each phase keeps its built-in duration.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Per-request timeout in seconds (default 10).",
    )
    parser.add_argument(
        "--qps",
        type=float,
        default=0.0,
        help="Override every active phase's qps. Default: 5 qps for each "
             "non-quiet phase.",
    )
    args = parser.parse_args()

    rng = random.Random()
    state = State(
        target=args.chunks,
        enabled_phases=args.phases,
        phase_duration_override=args.phase_duration,
        request_timeout=args.timeout,
        qps_override=args.qps,
    )

    print(f"Simulating query workload against {args.url}. Ctrl-C to stop.")
    if state.target == "all":
        print("  Target: all chunks (no time filter)")
    else:
        print(f"  Target: chunks at recency-indices {state.target} (newest first)")
    duration_repr = (
        f"{args.phase_duration:g}s each"
        if args.phase_duration > 0
        else "default per-phase durations"
    )
    print(f"  Phases: {', '.join(state.enabled_phases)}  ({duration_repr})")

    async with httpx.AsyncClient(base_url=args.url) as client:
        try:
            await client.get("/api/health", timeout=2.0)
        except httpx.HTTPError as e:
            print(f"Backend not reachable at {args.url}: {e}")
            return

        try:
            await asyncio.gather(
                chunks_refresher(client, state),
                querier_loop(client, rng, state),
                reporter_loop(state),
                director(state),
            )
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

    print(f"\nStopped. Total queries: {state.queries_run}.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
