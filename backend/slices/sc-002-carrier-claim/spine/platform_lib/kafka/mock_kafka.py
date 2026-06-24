"""
In-memory Kafka broker for local dev and unit tests.

Replaces kafka-python so Phase 1 can be tested without a running Kafka cluster.
Supports multiple topics, consumer groups, and per-group offset tracking.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Dict, List


class MockKafkaBroker:
    """
    Thread-safe in-memory Kafka broker.

    - publish to any topic via .send()
    - consume via .poll() with consumer-group offset tracking
    - inspect state via .messages_for(topic)
    """

    def __init__(self):
        self._lock = threading.Lock()
        # topic → list of raw message dicts
        self._topics:  Dict[str, List[dict]] = defaultdict(list)
        # group_id → topic → offset
        self._offsets: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def send(self, topic: str, key: bytes, value: bytes, headers: list = None) -> None:
        with self._lock:
            self._topics[topic].append({
                "key":     key,
                "value":   value,
                "headers": headers or [],
            })

    def subscribe(self, topics: list[str], group_id: str = "default") -> None:
        with self._lock:
            for t in topics:
                if t not in self._offsets[group_id]:
                    self._offsets[group_id][t] = 0

    def poll(self, timeout_ms: int = 1000, group_id: str = "default") -> Dict[str, List[dict]]:
        """
        Return all unread messages for this consumer group.
        Advances offsets after returning.
        """
        with self._lock:
            result = {}
            for topic, messages in self._topics.items():
                offset = self._offsets[group_id][topic]
                unread = messages[offset:]
                if unread:
                    result[topic] = list(unread)  # snapshot to avoid holding lock during dispatch
                    self._offsets[group_id][topic] = len(messages)
        return result

    def messages_for(self, topic: str) -> List[dict]:
        """Return all messages ever sent to a topic (for assertions in tests)."""
        with self._lock:
            return list(self._topics[topic])

    def message_count(self, topic: str) -> int:
        with self._lock:
            return len(self._topics[topic])

    def reset(self) -> None:
        """Clear all messages and offsets (useful between tests)."""
        with self._lock:
            self._topics.clear()
            self._offsets.clear()

    def topic_names(self) -> List[str]:
        with self._lock:
            return list(self._topics.keys())
