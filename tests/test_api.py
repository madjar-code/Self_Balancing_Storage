import pytest
import pytest_asyncio
from pathlib import Path
import httpx

from self_balancing_storage.config import Config
from self_balancing_storage.runtime import Runtime
from self_balancing_storage.api.app import create_app


@pytest_asyncio.fixture
async def client(tmp_path: Path):
    config = Config(
        data_path=tmp_path,
        cold_path=tmp_path,
        wal_path=tmp_path / "wal" / "current.log",
        chunk_max_seconds=10**9,
        wal_fsync_interval_ms=10,
        tick_interval_sec=10**9,
        ingest_queue_size=10,
    )
    runtime = Runtime(config)
    await runtime.start()
    app = create_app(runtime)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, runtime
    await runtime.stop()


@pytest.mark.asyncio
async def test_health(client):
    ac, _ = client
    resp = await ac.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_post_logs(client):
    ac, _ = client
    resp = await ac.post("/api/logs", json={
        "ts": 1.0, "service": "auth", "level": "INFO",
        "msg": "test", "fields": {},
    })
    assert resp.status_code == 202
    assert resp.json()["accepted"] == 1


@pytest.mark.asyncio
async def test_post_logs_validation(client):
    ac, _ = client
    resp = await ac.post("/api/logs", json={
        "ts": 1.0, "service": "", "level": "INFO",  # service empty
        "msg": "test", "fields": {},
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_query(client):
    import asyncio as aio
    ac, _ = client
    # Ingest first
    await ac.post("/api/logs", json={
        "ts": 1.0, "service": "auth", "level": "INFO",
        "msg": "test", "fields": {},
    })
    await aio.sleep(0.2)
    resp = await ac.post("/api/query", json={"q": 'service="auth"'})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_returned"] >= 1


@pytest.mark.asyncio
async def test_query_parse_error_400(client):
    ac, _ = client
    resp = await ac.post("/api/query", json={"q": "garbage syntax {"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_engine_state(client):
    ac, _ = client
    resp = await ac.get("/api/engine/state")
    assert resp.status_code == 200
    body = resp.json()
    assert "write_rate" in body
    assert "n_chunks" in body


@pytest.mark.asyncio
async def test_api_prefix_routing(client):
    """All endpoints live under /api/. Bare /health returns 404."""
    ac, _ = client
    assert (await ac.get("/api/health")).status_code == 200
    assert (await ac.get("/health")).status_code == 404


@pytest.mark.asyncio
async def test_get_indexes_returns_active_and_dropped(client):
    """Endpoint returns both active per-chunk indexes and engine.dropped_indexes."""
    import asyncio as aio
    from self_balancing_storage.engine.actions import DroppedIndex
    from self_balancing_storage.types import IndexType, PredicateOp
    from self_balancing_storage.indexes.hash_index import HashIndex

    ac, runtime = client

    # Ingest a couple of entries so the open chunk has data, then seal it.
    for ts in (1.0, 2.0):
        await ac.post("/api/logs", json={
            "ts": ts, "service": "auth", "level": "INFO",
            "msg": "m", "fields": {},
        })
    await aio.sleep(0.2)
    runtime.store._seal_open_chunk()
    chunk = runtime.store.chunks[0]

    # Build one active index on the sealed chunk.
    idx = HashIndex(chunk_id=chunk.header.chunk_id, field="service")
    idx.build(chunk.entries)
    chunk.indexes[idx.index_id] = idx

    # Plant one dropped index entry on the engine.
    runtime.engine.dropped_indexes["chunk_xx:hash:tenant"] = DroppedIndex(
        index_id="chunk_xx:hash:tenant",
        chunk_id="chunk_xx",
        field="tenant",
        op=PredicateOp.EQ,
        index_type=IndexType.HASH,
        dropped_at=42.0,
        prior_usage=7,
    )

    resp = await ac.get("/api/indexes")
    assert resp.status_code == 200
    body = resp.json()
    statuses = {item["status"] for item in body}
    assert statuses == {"active", "dropped"}

    active = next(item for item in body if item["status"] == "active")
    assert active["field"] == "service"
    assert active["type"] == "hash"
    assert active["chunk_id"] == chunk.header.chunk_id
    assert active["memory_bytes"] > 0

    dropped = next(item for item in body if item["status"] == "dropped")
    assert dropped["field"] == "tenant"
    assert dropped["dropped_at"] == 42.0
    assert dropped["prior_usage"] == 7


@pytest.mark.asyncio
async def test_top_predicates_returns_sorted_by_freq(client):
    """Endpoint returns predicates ordered by frequency desc."""
    from self_balancing_storage.types import Predicate, PredicateOp
    from self_balancing_storage.tracker.tracker import QueryEvent

    ac, runtime = client
    hot = Predicate("service", PredicateOp.EQ, "auth")
    warm = Predicate("level", PredicateOp.EQ, "ERROR")

    for _ in range(20):
        runtime.tracker.on_query(QueryEvent(ts=0.0, predicates=[hot], chunks_scanned=[]))
    for _ in range(5):
        runtime.tracker.on_query(QueryEvent(ts=0.0, predicates=[warm], chunks_scanned=[]))

    resp = await ac.get("/api/tracker/top-predicates")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 2
    assert body[0]["field"] == "service"
    assert body[0]["value"] == "auth"
    assert body[0]["freq"] >= 20
    fields = [p["field"] for p in body]
    assert fields.index("service") < fields.index("level")
