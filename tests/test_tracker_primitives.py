import random

from self_balancing_storage.tracker.primitives import (
    BurstDetector,
    CountMinSketch,
    EMA,
    MisraGries,
    SlidingCounter,
)


# === EMA ===

def test_ema_first_update_uses_value_directly():
    ema = EMA(alpha=0.5)
    ema.update(10.0)
    assert ema.value == 10.0


def test_ema_converges_to_constant_input():
    ema = EMA(alpha=0.3)
    for _ in range(100):
        ema.update(5.0)
    assert abs(ema.value - 5.0) < 0.01


def test_higher_alpha_reacts_faster():
    fast = EMA(alpha=0.5)
    slow = EMA(alpha=0.05)
    fast.update(0.0)
    slow.update(0.0)
    fast.update(10.0)
    slow.update(10.0)
    assert fast.value > slow.value


# === SlidingCounter ===

def test_sliding_counter_counts_within_window():
    counter = SlidingCounter(window_sec=10, n_buckets=10)
    counter.increment(now=0.0, by=5)
    counter.increment(now=5.0, by=3)
    assert counter.value(now=8.0) == 8


def test_sliding_counter_evicts_old_buckets():
    counter = SlidingCounter(window_sec=10, n_buckets=10)
    counter.increment(now=0.0, by=5)
    counter.increment(now=15.0, by=3)
    # bucket from t=0 falls out of the 10s window at t=15
    assert counter.value(now=15.0) == 3


# === BurstDetector ===

def test_burst_ratio_close_to_one_under_steady_load():
    detector = BurstDetector()
    for _ in range(50):
        detector.update(100.0)
    assert 0.9 < detector.burst_ratio < 1.1


def test_burst_ratio_grows_on_spike():
    detector = BurstDetector()
    for _ in range(50):
        detector.update(100.0)
    for _ in range(3):
        detector.update(1000.0)
    assert detector.burst_ratio > 3.0




# === CountMinSketch ===

def test_cms_estimate_never_below_true_count():
    cms = CountMinSketch(d=5, w=1024)
    for _ in range(100):
        cms.increment(b"key_a")
    for _ in range(50):
        cms.increment(b"key_b")
    assert cms.estimate(b"key_a") >= 100
    assert cms.estimate(b"key_b") >= 50


def test_cms_unseen_key_estimate_is_small():
    random.seed(42)
    cms = CountMinSketch(d=5, w=1024)
    for k in range(10):
        for _ in range(100):
            cms.increment(f"k{k}".encode())
    # collision-induced overestimate should still be small
    assert cms.estimate(b"unseen_key") < 20


# === MisraGries ===

def test_misra_gries_finds_heavy_hitter():
    mg = MisraGries(k=5)
    for _ in range(50):
        mg.add("HEAVY")
    for i in range(20):
        mg.add(f"x{i}")  # one-shots

    top_keys = [key for key, _ in mg.top()]
    assert "HEAVY" in top_keys


def test_misra_gries_capacity_limited_to_k():
    mg = MisraGries(k=3)
    for i in range(100):
        mg.add(f"x{i}")
    # internal slot count must never exceed k
    assert len(mg.top()) <= 3
