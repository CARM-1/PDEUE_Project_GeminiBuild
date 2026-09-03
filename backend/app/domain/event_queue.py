import heapq
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

@dataclass(order=True)
class QueuedEvent:
    priority: int
    timestamp: float
    event_id: str = field(compare=False)
    payload: Dict[str, Any] = field(compare=False)

class EventIngestionQueue:
    def __init__(self, max_capacity: int = 1000):
        self.max_capacity = max_capacity
        self._queue: List[QueuedEvent] = []
        self.dropped_count = 0
        self.processed_count = 0

    def enqueue(self, event_id: str, payload: Dict[str, Any], priority: int = 10) -> bool:
        if len(self._queue) >= self.max_capacity:
            self.dropped_count += 1
            return False
        item = QueuedEvent(
            priority=priority,
            timestamp=time.time(),
            event_id=event_id,
            payload=payload
        )
        heapq.heappush(self._queue, item)
        return True

    def dequeue(self) -> Optional[Dict[str, Any]]:
        if not self._queue:
            return None
        item = heapq.heappop(self._queue)
        self.processed_count += 1
        return {
            "event_id": item.event_id,
            "priority": item.priority,
            "timestamp": item.timestamp,
            "payload": item.payload
        }

    def queue_depth(self) -> int:
        return len(self._queue)

    def flush(self) -> List[Dict[str, Any]]:
        items = []
        while self._queue:
            item = self.dequeue()
            if item:
                items.append(item)
        return items

    def get_telemetry(self) -> Dict[str, Any]:
        return {
            "depth": len(self._queue),
            "max_capacity": self.max_capacity,
            "dropped_count": self.dropped_count,
            "processed_count": self.processed_count
        }
