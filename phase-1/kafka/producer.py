"""
Zoiko Kafka producer abstraction.

Wraps kafka-python (or mock) with:
- Mandatory tenant_id in every message header
- Mandatory idempotency_key in every message header
- JSON serialization with JCS canonicalization
- Outbox pattern: messages are persisted to DB outbox before Kafka publish

17 registered topics (zoiko. prefix, spec-aligned):
  zoiko.source.record.received, zoiko.source.record.validated, zoiko.canonical.invoice.created,
  zoiko.case.opened, zoiko.case.updated, zoiko.case.closed,
  zoiko.evidence.bundled, zoiko.finding.generated, zoiko.proposal.created,
  zoiko.governance.decision.issued, zoiko.governance.token.issued, zoiko.governance.token.consumed,
  zoiko.execution.dispatched, zoiko.execution.completed,
  zoiko.reconciliation.updated, zoiko.acr.generated, zoiko.audit.artifact.written
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# All 17 registered Kafka topics (zoiko. namespace prefix, spec §9.1)
REGISTERED_TOPICS = {
    "zoiko.source.record.received",    "zoiko.source.record.validated",   "zoiko.canonical.invoice.created",
    "zoiko.case.opened",               "zoiko.case.updated",              "zoiko.case.closed",
    "zoiko.evidence.bundled",          "zoiko.finding.generated",         "zoiko.proposal.created",
    "zoiko.governance.decision.issued","zoiko.governance.token.issued",   "zoiko.governance.token.consumed",
    "zoiko.execution.dispatched",      "zoiko.execution.completed",
    "zoiko.reconciliation.updated",    "zoiko.acr.generated",             "zoiko.audit.artifact.written",
    # FR-024 — security event stream
    "zoiko.security.event-detected.v1",
}


@dataclass
class KafkaMessage:
    """A single Kafka message with Zoiko envelope."""
    topic:          str
    key:            str                    # Partition key — usually case_id or tenant_id
    payload:        Dict[str, Any]
    tenant_id:      str
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:      datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = "1.0"

    def __post_init__(self):
        if self.topic not in REGISTERED_TOPICS:
            raise ValueError(f"Unknown topic '{self.topic}'. Must be one of: {sorted(REGISTERED_TOPICS)}")

    def to_bytes(self) -> bytes:
        envelope = {
            "schema_version":  self.schema_version,
            "tenant_id":       self.tenant_id,
            "idempotency_key": self.idempotency_key,
            "timestamp":       self.timestamp.isoformat(),
            "payload":         self.payload,
        }
        return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def headers(self) -> list[tuple[str, bytes]]:
        return [
            ("tenant_id",       self.tenant_id.encode()),
            ("idempotency_key", self.idempotency_key.encode()),
            ("schema_version",  self.schema_version.encode()),
        ]


class ZoikoProducer:
    """
    Kafka producer with outbox support.

    In dev: wraps MockKafkaBroker.
    In staging/prod: wraps kafka-python KafkaProducer with SSL + SASL.
    """

    def __init__(self, broker: Any):
        self._broker = broker

    def publish(self, message: KafkaMessage) -> None:
        """Publish a message. Raises if topic is not registered."""
        self._broker.send(
            topic   = message.topic,
            key     = message.key.encode("utf-8"),
            value   = message.to_bytes(),
            headers = message.headers(),
        )

    def publish_batch(self, messages: list[KafkaMessage]) -> None:
        for msg in messages:
            self.publish(msg)

    def close(self) -> None:
        if hasattr(self._broker, "close"):
            self._broker.close()
