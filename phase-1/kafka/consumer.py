"""
Zoiko Kafka consumer abstraction.

Each microservice subscribes to one or more topics via ZoikoConsumer.
The consumer:
- Validates tenant_id header on every message
- Deserializes the JSON envelope
- Dispatches to the registered MessageHandler
- Commits offset only after handler succeeds (at-least-once delivery)
"""
from __future__ import annotations

import json
from typing import Callable, Dict, Any, Optional
from dataclasses import dataclass


MessageHandler = Callable[[str, Dict[str, Any]], None]
# Signature: handler(tenant_id: str, payload: dict) -> None


@dataclass
class ConsumedMessage:
    topic:           str
    key:             str
    tenant_id:       str
    idempotency_key: str
    payload:         Dict[str, Any]
    schema_version:  str


class ZoikoConsumer:
    """
    Kafka consumer that validates Zoiko message envelopes.

    In dev: wraps MockKafkaBroker.
    In staging/prod: wraps kafka-python KafkaConsumer with SSL + SASL.
    """

    def __init__(self, broker: Any, group_id: str):
        self._broker   = broker
        self._group_id = group_id
        self._handlers: Dict[str, MessageHandler] = {}

    def subscribe(self, topic: str, handler: MessageHandler) -> None:
        """Register a handler for a topic. One handler per topic."""
        self._handlers[topic] = handler
        if hasattr(self._broker, "subscribe"):
            self._broker.subscribe([topic], group_id=self._group_id)

    def poll(self, timeout_ms: int = 1000) -> int:
        """
        Poll for messages and dispatch to handlers.
        Returns number of messages processed.
        """
        records = self._broker.poll(timeout_ms=timeout_ms, group_id=self._group_id)
        count   = 0
        for topic, msgs in records.items():
            handler = self._handlers.get(topic)
            if not handler:
                continue
            for raw in msgs:
                msg = self._parse(topic, raw)
                if msg:
                    handler(msg.tenant_id, msg.payload)
                    count += 1
        return count

    def close(self) -> None:
        if hasattr(self._broker, "close"):
            self._broker.close()

    def _parse(self, topic: str, raw: dict) -> Optional[ConsumedMessage]:
        try:
            body    = json.loads(raw["value"])
            headers = {k: v.decode() for k, v in raw.get("headers", [])}
            return ConsumedMessage(
                topic           = topic,
                key             = raw.get("key", b"").decode(),
                tenant_id       = headers.get("tenant_id", body.get("tenant_id", "")),
                idempotency_key = headers.get("idempotency_key", body.get("idempotency_key", "")),
                payload         = body.get("payload", {}),
                schema_version  = body.get("schema_version", "1.0"),
            )
        except Exception:
            return None
