import asyncio

import pytest

from self_balancing_storage.config import Config
from self_balancing_storage.runtime import runtime
from self_balancing_storage.types import LogEntry, Predicate, PredicateOp


@pytest.mark.asyncio
async def test_end_to_end_basic(tmp_path):
    config = Config(
        tick_interval_sec=0.1,
        build_threshold_freq=2,
        data_path=tmp_path,
        cold_path=tmp_path,
        wal_path=tmp_path / "wal" / "current.log",
    )
    async with runtime(config) as rt:
        # writes
        for i in range(50):
            rt.append(LogEntry(
                ts=i,
                service="auth-api" if i % 2 else "billing",
                level="INFO",
                msg=f"event {i}",
                fields={"user_id": i},
            ))
        # queries that should make Engine notice predicate
        for _ in range(5):
            await rt.find(Predicate(field="service", op=PredicateOp.EQ, value="auth-api"))
        # let the engine run a few ticks
        await asyncio.sleep(0.5)

        # at least one index should appear somewhere
        any_index = any(c.indexes for c in rt.store.chunks)
        print(rt.engine.collect_index_infos())
        assert any_index
