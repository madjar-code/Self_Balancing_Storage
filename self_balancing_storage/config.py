from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    # === Chunks ===
    chunk_max_entries: int = 10_000
    chunk_max_bytes: int = 5_000_000
    chunk_max_seconds: float = 60.0

    # === Engine Loop ===
    tick_interval_sec: float = 10.0
    actions_per_tick_budget: int = 10
    builds_per_tick: int = 3

    # === Index decisions ===
    dynamic_indexing: bool = True
    build_threshold_freq: int = 5
    min_temp_for_index: float = 0.3
    idle_drop_sec: float = 600.0
    cooldown_sec: float = 600.0
    min_roi: float = 0.1

    # === Memory ===
    mem_pressure_drop: float = 0.7
    mem_pressure_high: float = 0.8
    mem_pressure_critical: float = 0.95
    max_memory_bytes: int = 512 * 1024 * 1024  # 512 MB process memory budget

    # === Burst mode ===
    burst_enter: float = 3.0
    burst_exit: float = 1.5
    burst_stability_n: int = 3

    # === Tracker ===
    cms_d: int = 5
    cms_w: int = 1024
    topk_k: int = 20
    ema_alpha_write_rate: float = 0.2
    ema_alpha_chunk_temp: float = 0.1
    write_window_sec: int = 60
    # Decay accumulated counters every N engine ticks by `decay_factor`.
    decay_every_n_ticks: int = 30
    decay_factor: float = 0.5

    # === Bloom ===
    bloom_fp_rate: float = 0.01

    # === Skip index ===
    skip_block_size: int = 100

    # === Persistence ===
    data_path: Path = Path("./data")
    cold_path: Path = Path("./data")
    wal_path: Path = Path("./data/wal/current.log")
    wal_fsync_interval_ms: int = 100

    # === Tiers ===
    heavy_index_threshold: int = 100 * 1024
    disk_cost_factor: int = 100
    demote_threshold: float = 0.1
    demote_idle_sec: float = 300.0
    demote_grace_sec: float = 30.0
    promote_threshold: float = 0.5

    # === HTTP API ===
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    ingest_queue_size: int = 1000

    # === EventBroker ===
    metric_tick_interval_sec: float = 2.0
    event_subscriber_buffer: int = 1000
