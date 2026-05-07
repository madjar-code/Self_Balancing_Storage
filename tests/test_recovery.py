import asyncio
import pytest
from pathlib import Path

from self_balancing_storage.config import Config
from self_balancing_storage.runtime import Runtime
from self_balancing_storage.types import LogEntry


def make_config(tmp_path: Path) -> Config:
    return Config(
        data_path=tmp_path,
        cold_path=tmp_path,
        wal_path=tmp_path / "wal" / "current.log",
        chunk_max_entries=5,
        chunk_max_seconds=10**9,
        wal_fsync_interval_ms=10,
        tick_interval_sec=10**9,  # disable engine ticks during test
    )

@pytest.mark.asyncio
async def test_recovery_restores_sealed_chunks(tmp_path: Path):
    config = make_config(tmp_path)

    rt1 = Runtime(config)
    await rt1.start()

    for i in range(12):
        await rt1.try_append(LogEntry(
            ts=float(i), service="a", level="INFO", msg="m",
        ))
    await asyncio.sleep(0.5)
    await rt1.stop()

    rt2 = Runtime(config)
    await rt2.start()

    persisted_count = sum(c.header.count for c in rt2.store.chunks if c.header.state.value == "persisted")
    assert persisted_count == 12  # graceful stop drains open chunk too

    await rt2.stop()


@pytest.mark.asyncio
async def test_wal_replay_recovers_open_chunk(tmp_path: Path):
    config = make_config(tmp_path)

    rt1 = Runtime(config)
    await rt1.start()
    for i in range(3):  # all in one open chunk (chunk_max_entries=5)
        await rt1.try_append(LogEntry(
            ts=float(i), service="a", level="INFO", msg="m",
        ))
    await asyncio.sleep(0.2)
    # Stop without sealing — entries should be in WAL only
    await rt1.stop()

    rt2 = Runtime(config)
    await rt2.start()
    total = sum(c.header.count for c in rt2.store.chunks)
    assert total == 3  # all 3 recovered from WAL
    await rt2.stop()
