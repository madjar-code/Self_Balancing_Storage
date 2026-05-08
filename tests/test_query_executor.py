import pytest

from self_balancing_storage.config import Config
from self_balancing_storage.indexes.bloom import BloomIndex
from self_balancing_storage.indexes.hash_index import HashIndex
from self_balancing_storage.query.executor import execute
from self_balancing_storage.query.parser import parse
from self_balancing_storage.query.planner import plan_query
from self_balancing_storage.store import ChunkStore
from self_balancing_storage.types import LogEntry


@pytest.fixture
def populated_store():
    """3 sealed chunks of 5 entries each. Half are service="auth", every
    third has level="ERROR", each entry has a unique trace_id "trace-{i}"."""
    config = Config(chunk_max_entries=5)
    store = ChunkStore(config)
    for i in range(15):
        store.append(LogEntry(
            ts=float(i),
            service="auth" if i % 2 == 0 else "billing",
            level="ERROR" if i % 3 == 0 else "INFO",
            msg=f"m{i}",
            fields={"trace_id": f"trace-{i}"},
        ))
    return store


@pytest.fixture
def populated_store_with_hash_index(populated_store):
    """populated_store + HashIndex on `service` for every sealed chunk."""
    for chunk in populated_store.chunks:
        if chunk.header.state.value == "open":
            continue
        idx = HashIndex(chunk_id=chunk.header.chunk_id, field="service")
        idx.build(chunk.entries)
        chunk.indexes[idx.index_id] = idx
    return populated_store


@pytest.fixture
def populated_store_with_bloom(populated_store):
    """populated_store + BloomIndex on `trace_id` for every sealed chunk."""
    for chunk in populated_store.chunks:
        if chunk.header.state.value == "open":
            continue
        idx = BloomIndex(
            chunk_id=chunk.header.chunk_id,
            field="trace_id",
            n_items=max(chunk.header.count, 1),
            fp_rate=0.01,
        )
        idx.build(chunk.entries)
        chunk.indexes[idx.index_id] = idx
    return populated_store


@pytest.mark.asyncio
async def test_execute_simple_query(populated_store):
    plan = plan_query(parse('service="auth"'), populated_store)
    results, _, _ = await execute(plan, populated_store)
    assert all(e.service == "auth" for e in results)


@pytest.mark.asyncio
async def test_execute_and(populated_store):
    plan = plan_query(parse('service="auth" and level="ERROR"'), populated_store)
    results, _, _ = await execute(plan, populated_store)
    assert all(e.service == "auth" and e.level == "ERROR" for e in results)


@pytest.mark.asyncio
async def test_execute_limit(populated_store):
    plan = plan_query(parse('service="auth" | limit 5'), populated_store)
    results, _, _ = await execute(plan, populated_store)
    assert len(results) <= 5


@pytest.mark.asyncio
async def test_execute_uses_index_when_available(populated_store_with_hash_index):
    """With a HashIndex on `service`, executor should consult it and
    report the index_id in the third return value."""
    plan = plan_query(parse('service="auth"'), populated_store_with_hash_index)
    results, scanned, used = await execute(plan, populated_store_with_hash_index)
    assert all(e.service == "auth" for e in results)
    assert len(used) > 0  # at least one index was used


@pytest.mark.asyncio
async def test_execute_bloom_post_filter(populated_store_with_bloom):
    """BloomIndex(precise=False): lookup may return all positions, but
    post-filter must narrow to actual matches."""
    plan = plan_query(parse('trace_id="trace-7"'), populated_store_with_bloom)
    results, _, used = await execute(plan, populated_store_with_bloom)
    assert all(e.fields.get("trace_id") == "trace-7" for e in results)
    assert len(used) > 0
