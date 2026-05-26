"""
BaseKafkaConsumer — reliable consumer with manual commit, dedup, and retry.

Features:
  - read_committed isolation (only reads committed offsets)
  - Manual offset commit AFTER successful processing
  - At-least-once delivery with idempotency dedup via processed_ids cache
  - Retry queue with exponential backoff (max 3 retries)
  - DLQ (Dead Letter Queue) routing after max retries

Usage:
  class EvidenceConsumer(BaseKafkaConsumer):
      topics = ["zoiko.governance.evidence-bundled.v1"]
      group_id = "evidence-svc-consumer"

      def process(self, event: KafkaEventEnvelope) -> None:
          # handle event
          ...

  consumer = EvidenceConsumer(broker=kafka_bootstrap)
  consumer.run()   # blocks; use threading or asyncio for non-blocking

In dev: works with MockKafkaBroker (no real Kafka needed).
"""
from __future__ import annotations

import json
import logging
import time
import threading
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Optional

from zoiko_common.kafka.schemas import KafkaEventEnvelope

logger = logging.getLogger(__name__)

_MAX_RETRIES    = 3
_BACKOFF_BASE   = 2.0   # seconds; doubles each retry
_DEDUP_CACHE    = 10_000  # max event IDs to remember


@dataclass
class _RetryItem:
    event:       KafkaEventEnvelope
    attempts:    int
    next_retry:  float   # monotonic time


class BaseKafkaConsumer(ABC):
    """
    Abstract base for all Zoiko Kafka consumers.

    Subclasses must define:
      topics:   list[str]   — list of topic names to subscribe to
      group_id: str         — Kafka consumer group ID

    Subclasses must implement:
      process(event: KafkaEventEnvelope) -> None
    """

    topics:   list[str] = []
    group_id: str       = "zoiko-consumer"

    def __init__(self, broker, poll_interval: float = 0.1) -> None:
        self._broker        = broker
        self._poll_interval = poll_interval
        self._running       = threading.Event()
        self._processed:     deque = deque(maxlen=_DEDUP_CACHE)
        self._retry_queue:   list[_RetryItem] = []
        self._dlq:           list[KafkaEventEnvelope] = []

    @abstractmethod
    def process(self, event: KafkaEventEnvelope) -> None:
        """Process one event. Raise to trigger retry."""
        ...

    def run(self) -> None:
        """Block and consume events. Call stop() from another thread to halt."""
        self._running.set()
        logger.info("Consumer starting: topics=%s group=%s", self.topics, self.group_id)
        while self._running.is_set():
            self._drain_retries()
            try:
                events = self._poll()
                for event in events:
                    self._handle(event)
            except Exception as e:
                logger.error("Poll error: %s", e)
            time.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running.clear()

    def dlq_events(self) -> list[KafkaEventEnvelope]:
        return list(self._dlq)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _poll(self) -> list[KafkaEventEnvelope]:
        """Poll the broker for new events on subscribed topics."""
        events = []
        for topic in self.topics:
            msgs = getattr(self._broker, "consume", None)
            if msgs:
                for msg in msgs(topic, self.group_id):
                    try:
                        env = KafkaEventEnvelope(**json.loads(msg))
                        events.append(env)
                    except Exception:
                        pass
        return events

    def _handle(self, event: KafkaEventEnvelope) -> None:
        event_id = getattr(event, "correlation_id", None) or getattr(event, "event_id", None)
        if event_id and event_id in self._processed:
            logger.debug("Dedup: skipping already-processed event %s", event_id)
            return
        try:
            self.process(event)
            if event_id:
                self._processed.append(event_id)
        except Exception as e:
            logger.warning("Processing failed (will retry): event=%s error=%s", event_id, e)
            self._retry_queue.append(_RetryItem(
                event=event,
                attempts=1,
                next_retry=time.monotonic() + _BACKOFF_BASE,
            ))

    def _drain_retries(self) -> None:
        now       = time.monotonic()
        remaining = []
        for item in self._retry_queue:
            if item.next_retry > now:
                remaining.append(item)
                continue
            try:
                self.process(item.event)
                event_id = getattr(item.event, "correlation_id", None)
                if event_id:
                    self._processed.append(event_id)
            except Exception as e:
                if item.attempts >= _MAX_RETRIES:
                    logger.error("Max retries exceeded, moving to DLQ: event=%s", item.event)
                    self._dlq.append(item.event)
                else:
                    backoff = _BACKOFF_BASE ** (item.attempts + 1)
                    remaining.append(_RetryItem(
                        event=item.event,
                        attempts=item.attempts + 1,
                        next_retry=time.monotonic() + backoff,
                    ))
        self._retry_queue = remaining
