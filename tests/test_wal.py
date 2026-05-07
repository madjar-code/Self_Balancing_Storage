import asyncio
from pathlib import Path
import pytest

from self_balancing_storage.persistence.wal import WAL
from self_balancing_storage.types import LogEntry


@pytest.mark.asyncio
async def test_append_and_replay(tmp_path: Path):
    log_path = tmp_path / "wal.log"
    wal = WAL(log_path, fsync_interval_ms=10)
    await wal.start()

    for i in range(5):
        await wal.append(LogEntry(
            ts=float(i), service="svc", level="INFO", msg=f"m{i}",
        ))

    await asyncio.sleep(0.05)
    await wal.stop()

    wal2 = WAL(log_path)
    replayed = await wal2.replay()
    assert len(replayed) == 5
    assert replayed[0].msg == "m0"
    assert replayed[-1].msg == "m4"


@pytest.mark.asyncio
async def test_truncate_clears_log(tmp_path: Path):
    log_path = tmp_path / "wal.log"
    wal = WAL(log_path, fsync_interval_ms=10)
    await wal.start()
    await wal.append(LogEntry(ts=1, service="a", level="INFO", msg="m"))
    await asyncio.sleep(0.05)
    await wal.truncate()

    replayed = await wal.replay()
    assert replayed == []
    await wal.stop()


@pytest.mark.asyncio
async def test_corrupt_lines_skipped(tmp_path: Path):
    log_path = tmp_path / "wal.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        '{"ts": 1, "service": "a", "level": "INFO", "msg": "valid"}\n'
        'this is not json\n'
        '{"ts": 2, "service": "b", "level": "INFO", "msg": "also valid"}\n'
    )
    wal = WAL(log_path)
    replayed = await wal.replay()
    assert len(replayed) == 2
    assert replayed[0].msg == "valid"
