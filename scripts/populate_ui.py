"""
Drive a running Self-Balancing Storage backend with synthetic log entries
so the UI dashboard has something to display.

Usage:
    1. In one terminal, start the backend:
         uv run python -m self_balancing_storage.main
    2. In another terminal, run this:
         uv run python scripts/populate_ui.py
    Optional flags: --url http://localhost:8000  --wps 100

The script runs forever (Ctrl-C to stop). Use the UI's Query page to
trigger queries - that is what makes the engine learn predicate
frequencies and start building indexes, which in turn fills the
Decisions feed and the Indexes page.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import time
from typing import Any

import httpx


SERVICES = ["auth-api", "billing", "frontend", "notification", "search", "worker"]
LEVELS = ["INFO", "WARN", "ERROR", "DEBUG"]
TENANTS = [f"t{i:03d}" for i in range(50)]
REGIONS = ["eu-west", "us-east", "us-west", "ap-south"]
HOT_KEYS = [f"hk-{i}" for i in range(20)]


def make_entry(rng: random.Random) -> dict[str, Any]:
    return {
        "ts": time.time(),
        "service": rng.choices(SERVICES, weights=[40, 25, 15, 10, 5, 5])[0],
        "level": rng.choices(LEVELS, weights=[80, 12, 5, 3])[0],
        "msg": "m",
        "fields": {
            "tenant": rng.choice(TENANTS),
            "region": rng.choice(REGIONS),
            "user_no": rng.randint(1, 100_000),
            "req_key": (
                rng.choice(HOT_KEYS) if rng.random() < 0.3
                else f"req-{rng.randint(1, 1_000_000)}"
            ),
        },
    }


async def writer_loop(
    client: httpx.AsyncClient,
    rng: random.Random,
    wps: int,
    stats: dict[str, int],
) -> None:
    batch_size = 50
    interval = batch_size / wps if wps > 0 else 1.0
    while True:
        t0 = time.time()
        batch = [make_entry(rng) for _ in range(batch_size)]
        try:
            resp = await client.post("/api/logs", json=batch, timeout=2.0)
            if resp.status_code == 202:
                stats["w"] += batch_size
            elif resp.status_code == 429:
                """Ingest queue full; back off briefly."""
                await asyncio.sleep(0.5)
            else:
                print(f"  write got {resp.status_code}: {resp.text[:120]}")
        except httpx.HTTPError as e:
            print(f"  write failed: {e}")
            await asyncio.sleep(1.0)
        elapsed = time.time() - t0
        await asyncio.sleep(max(0.0, interval - elapsed))


async def progress_loop(stats: dict[str, int]) -> None:
    started = time.time()
    while True:
        await asyncio.sleep(2.0)
        elapsed = time.time() - started
        rate = stats["w"] / elapsed if elapsed > 0 else 0
        print(f"  +{elapsed:5.0f}s   wrote {stats['w']:>7}   ({rate:.0f} /s)")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Populate a running SBS backend with synthetic log entries.",
    )
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--wps", type=int, default=100, help="Writes per second (default 100)")
    args = parser.parse_args()

    rng = random.Random()
    stats = {"w": 0}

    print(f"Populating {args.url} at {args.wps} wps. Ctrl-C to stop.\n")

    async with httpx.AsyncClient(base_url=args.url) as client:
        try:
            await client.get("/api/health", timeout=2.0)
        except httpx.HTTPError as e:
            print(f"Backend not reachable at {args.url}: {e}")
            return

        try:
            await asyncio.gather(
                writer_loop(client, rng, args.wps, stats),
                progress_loop(stats),
            )
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

    print(f"\nStopped. Total: {stats['w']} entries.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
