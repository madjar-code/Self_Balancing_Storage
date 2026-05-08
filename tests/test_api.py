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
    resp = await ac.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_post_logs(client):
    ac, _ = client
    resp = await ac.post("/logs", json={
        "ts": 1.0, "service": "auth", "level": "INFO",
        "msg": "test", "fields": {},
    })
    assert resp.status_code == 202
    assert resp.json()["accepted"] == 1


@pytest.mark.asyncio
async def test_post_logs_validation(client):
    ac, _ = client
    resp = await ac.post("/logs", json={
        "ts": 1.0, "service": "", "level": "INFO",  # service empty
        "msg": "test", "fields": {},
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_query(client):
    import asyncio as aio
    ac, _ = client
    # Ingest first
    await ac.post("/logs", json={
        "ts": 1.0, "service": "auth", "level": "INFO",
        "msg": "test", "fields": {},
    })
    await aio.sleep(0.2)
    resp = await ac.post("/query", json={"q": 'service="auth"'})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_returned"] >= 1


@pytest.mark.asyncio
async def test_query_parse_error_400(client):
    ac, _ = client
    resp = await ac.post("/query", json={"q": "garbage syntax {"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_engine_state(client):
    ac, _ = client
    resp = await ac.get("/engine/state")
    assert resp.status_code == 200
    body = resp.json()
    assert "write_rate" in body
    assert "n_chunks" in body
