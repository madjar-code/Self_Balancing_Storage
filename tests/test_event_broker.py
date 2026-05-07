import asyncio
import pytest

from self_balancing_storage.observability.event_broker import EventBroker


@pytest.mark.asyncio
async def test_publish_to_single_subscriber():
    broker = EventBroker()
    async with broker.subscribe() as q:
        broker.publish({"type": "test", "value": 1})
        event = await q.get()
        assert event["value"] == 1


@pytest.mark.asyncio
async def test_publish_fans_out_to_multiple_subscribers():
    broker = EventBroker()
    async with broker.subscribe() as q1, broker.subscribe() as q2:
        broker.publish({"type": "test", "value": 42})
        e1 = await q1.get()
        e2 = await q2.get()
        assert e1["value"] == 42
        assert e2["value"] == 42


@pytest.mark.asyncio
async def test_subscriber_removed_on_context_exit():
    broker = EventBroker()
    async with broker.subscribe() as _q:
        assert len(broker._subscribers) == 1
    assert len(broker._subscribers) == 0


@pytest.mark.asyncio
async def test_publish_with_no_subscribers():
    broker = EventBroker()
    broker.publish({"type": "test"})


@pytest.mark.asyncio
async def test_slow_subscriber_drops_events():
    broker = EventBroker()
    async with broker.subscribe(max_buffer=2) as q:
        for i in range(10):
            broker.publish({"id": i})
        events = []
        try:
            while True:
                events.append(q.get_nowait())
        except asyncio.QueueEmpty:
            pass
        assert len(events) == 2
        assert events[0]["id"] == 0


@pytest.mark.asyncio
async def test_other_subscribers_not_affected_by_slow_one():
    broker = EventBroker()
    async with broker.subscribe(max_buffer=2) as _slow, broker.subscribe(max_buffer=100) as fast:
        for i in range(10):
            broker.publish({"id": i})
        fast_events = []
        try:
            while True:
                fast_events.append(fast.get_nowait())
        except asyncio.QueueEmpty:
            pass
        assert len(fast_events) == 10
