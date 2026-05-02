from self_balancing_storage.tracker.heatmap import ChunkHeatmap


def test_record_access_increases_temperature():
    heatmap = ChunkHeatmap(alpha=0.3)
    assert heatmap.temperature("c1") == 0.0
    heatmap.record_access("c1", now=0.0)
    assert heatmap.temperature("c1") > 0.0


def test_cool_down_decreases_temperature_over_time():
    heatmap = ChunkHeatmap(alpha=0.3)
    for _ in range(10):
        heatmap.record_access("c1", now=0.0)
    hot = heatmap.temperature("c1")

    for _ in range(20):
        heatmap.cool_down(["c1"])
    cool = heatmap.temperature("c1")
    assert cool < hot


def test_hottest_returns_top_n_in_order():
    heatmap = ChunkHeatmap(alpha=0.3)
    for _ in range(10):
        heatmap.record_access("c1", now=0.0)
    for _ in range(5):
        heatmap.record_access("c2", now=0.0)
    heatmap.record_access("c3", now=0.0)

    top = heatmap.hottest(2)
    assert top == ["c1", "c2"]


def test_remove_drops_chunk_from_heatmap():
    heatmap = ChunkHeatmap(alpha=0.3)
    heatmap.record_access("c1", now=0.0)
    heatmap.remove("c1")
    assert heatmap.temperature("c1") == 0.0
