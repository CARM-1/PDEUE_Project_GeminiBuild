from app.domain.event_queue import EventIngestionQueue

def test_event_queue_priority_ordering():
    q = EventIngestionQueue(max_capacity=10)
    q.enqueue("low_prio", {"msg": "low"}, priority=50)
    q.enqueue("urgent_prio", {"msg": "urgent"}, priority=1)
    q.enqueue("med_prio", {"msg": "med"}, priority=10)
    assert q.dequeue()["event_id"] == "urgent_prio"
    assert q.dequeue()["event_id"] == "med_prio"
    assert q.dequeue()["event_id"] == "low_prio"

def test_event_queue_capacity_overflow():
    q = EventIngestionQueue(max_capacity=2)
    assert q.enqueue("evt_1", {"data": 1}, priority=1) is True
    assert q.enqueue("evt_2", {"data": 2}, priority=1) is True
    assert q.enqueue("evt_3", {"data": 3}, priority=1) is False
    assert q.dropped_count == 1
    assert q.queue_depth() == 2

def test_event_queue_flush_and_telemetry():
    q = EventIngestionQueue(max_capacity=5)
    q.enqueue("evt_a", {"a": 1})
    q.enqueue("evt_b", {"b": 2})
    flushed = q.flush()
    assert len(flushed) == 2
    assert q.queue_depth() == 0
    telemetry = q.get_telemetry()
    assert telemetry["processed_count"] == 2
    assert telemetry["depth"] == 0
