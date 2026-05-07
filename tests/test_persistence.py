import pytest
from pathlib import Path

from self_balancing_storage.chunk import Chunk
from self_balancing_storage.persistence.chunk_writer import ChunkPersistence
from self_balancing_storage.persistence.chunk_reader import ChunkReader
from self_balancing_storage.types import ChunkState, LogEntry


@pytest.mark.asyncio
async def test_persist_then_reload(tmp_path: Path):
    persistence = ChunkPersistence(tmp_path)

    chunk = Chunk.new(seq=1, now=0.0)
    for i in range(50):
        chunk.append(LogEntry(
            ts=float(i), service="auth", level="INFO", msg=f"m{i}",
            fields={"user_id": i},
        ))
    chunk.seal()

    await persistence.persist_chunk(chunk)

    assert chunk.header.state == ChunkState.PERSISTED
    assert chunk.header.persisted_at is not None

    reader = ChunkReader(tmp_path)
    headers = await reader.load_metadata()
    assert len(headers) == 1
    assert headers[0].chunk_id == chunk.header.chunk_id
    assert headers[0].count == 50

    entries = await reader.load_entries(chunk.header.chunk_id)
    assert len(entries) == 50
    assert entries[0].ts == 0.0
    assert entries[-1].fields["user_id"] == 49


@pytest.mark.asyncio
async def test_callback_invoked_on_persist(tmp_path: Path):
    invoked: list[str] = []

    async def callback(chunk_id: str) -> None:
        invoked.append(chunk_id)

    persistence = ChunkPersistence(tmp_path, on_chunk_persisted=callback)

    chunk = Chunk.new(seq=1, now=0.0)
    chunk.append(LogEntry(ts=0, service="a", level="INFO", msg="m"))
    chunk.seal()

    await persistence.persist_chunk(chunk)

    assert invoked == [chunk.header.chunk_id]
