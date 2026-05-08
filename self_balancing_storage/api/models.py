from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field, field_validator
import time


class LogEntryIn(BaseModel):
    ts: float
    service: str = Field(min_length=1, max_length=128)
    level: str = Field(pattern=r"^(DEBUG|INFO|WARN|ERROR|FATAL)$")
    msg: str = Field(max_length=10_000)
    fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ts")
    @classmethod
    def ts_must_be_recent(cls, v: float) -> float:
        if v < 0 or v > time.time() + 86400:
            raise ValueError("ts must be a recent unix timestamp")
        return v


class QueryRequest(BaseModel):
    q: str = Field(min_length=1, max_length=10_000)


class QueryResponse(BaseModel):
    results: list[dict]
    rows_returned: int
    duration_ms: float
