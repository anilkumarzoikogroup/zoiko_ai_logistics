"""
Zoiko Kafka producer abstraction.

Wraps kafka-python (or mock) with:
- Mandatory tenant_id in every message header
- Mandatory idempotency_key in every message header
- JSON serialization (sort_keys=True for determinism; not strict RFC 8785 JCS)
- Outbox pattern: messages are persisted to DB outbox before Kafka publish

31 registered topics (zoiko. prefix, spec-aligned):
  zoiko.source.record.received, zoiko.source.record.validated, zoiko.canonical.invoice.created,
  zoiko.case.opened, zoiko.case.updated, zoiko.case.closed,
  zoiko.evidence.bundled, zoiko.finding.generated, zoiko.proposal.created,
  zoiko.governance.decision.issued, zoiko.governance.token.issued, zoiko.governance.token.consumed,
  zoiko.execution.dispatched, zoiko.execution.completed,
  zoiko.reconciliation.updated, zoiko.acr.generated, zoiko.audit.artifact.written,
  zoiko.security.event-detected.v1,
  *.retry (6 critical-path retry topics), *.dlq (6 dead-letter topics)
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# Operational topic registry — must stay in sync with PRODUCER_TOPICS in
# zoiko_common/kafka/schemas.py (the outbox relay validates against that copy).
REGISTERED_TOPICS = {
    "zoiko.source.record.received",    "zoiko.source.record.validated",   "zoiko.canonical.invoice.created",
    "zoiko.canonical.claim.created",   # SC-002 — canonicalize_claim()
    "zoiko.claim.submitted",           # SC-002 — claim case opened
    "zoiko.claim.negotiated",          # SC-002 — counter-offer round completed
    "zoiko.claim.settled",             # SC-002 — carrier settlement response received
    "zoiko.claim.disputed",            # SC-002 — escalation triggered
    "zoiko.case.opened",               "zoiko.case.updated",              "zoiko.case.closed",
    "zoiko.evidence.bundled",          "zoiko.finding.generated",         "zoiko.proposal.created",
    "zoiko.governance.decision.issued","zoiko.governance.token.issued",   "zoiko.governance.token.consumed",
    "zoiko.execution.dispatched",      "zoiko.execution.completed",
    "zoiko.reconciliation.updated",    "zoiko.acr.generated",             "zoiko.audit.artifact.written",
    "zoiko.security.event-detected.v1",
    "zoiko.evidence.bundled.retry",           "zoiko.finding.generated.retry",
    "zoiko.governance.decision.issued.retry", "zoiko.governance.token.issued.retry",
    "zoiko.execution.dispatched.retry",       "zoiko.reconciliation.updated.retry",
    "zoiko.evidence.bundled.dlq",             "zoiko.finding.generated.dlq",
    "zoiko.governance.decision.issued.dlq",   "zoiko.governance.token.issued.dlq",
    "zoiko.execution.dispatched.dlq",         "zoiko.reconciliation.updated.dlq",

    # Phase 6 (Clarification 06 Slice 1) — financial recovery layer
    "zoiko.recovery.expected.created",        "zoiko.recovery.instrument.received",
    "zoiko.recovery.expected.created.retry",  "zoiko.recovery.instrument.received.retry",
    "zoiko.recovery.expected.created.dlq",    "zoiko.recovery.instrument.received.dlq",
    "zoiko.recovery.match.created",           "zoiko.recovery.match.reversed",
    "zoiko.recovery.match.created.retry",     "zoiko.recovery.match.reversed.retry",
    "zoiko.recovery.match.created.dlq",       "zoiko.recovery.match.reversed.dlq",
    "zoiko.ledger.entry.posted",              "zoiko.ledger.entry.reversed",
    "zoiko.ledger.entry.posted.retry",        "zoiko.ledger.entry.reversed.retry",
    "zoiko.ledger.entry.posted.dlq",          "zoiko.ledger.entry.reversed.dlq",
    "zoiko.recovery.writeoff.requested",      "zoiko.recovery.writeoff.posted",
    "zoiko.recovery.writeoff.requested.retry","zoiko.recovery.writeoff.posted.retry",
    "zoiko.recovery.writeoff.requested.dlq",  "zoiko.recovery.writeoff.posted.dlq",
    "zoiko.recovery.proof.generated",
    "zoiko.recovery.proof.generated.retry",
    "zoiko.recovery.proof.generated.dlq",

    # Clarification 07 — Data Residency, Retention, Legal Hold, Crypto-Shred, Archive, Restore, Purge
    "zoiko.legal_hold.created",            "zoiko.legal_hold.released",
    "zoiko.legal_hold.blocked_purge",
    "zoiko.crypto_shred.requested",        "zoiko.crypto_shred.completed",
    "zoiko.crypto_shred.blocked",          "zoiko.crypto_shred.verified",
    "zoiko.restore.requested",             "zoiko.restore.verification_passed",
    "zoiko.restore.verification_failed",   "zoiko.restore.completed",
    "zoiko.archive.started",               "zoiko.archive.completed",
    "zoiko.archive.failed",
    "zoiko.purge.requested",               "zoiko.purge.approved",
    "zoiko.purge.blocked",                 "zoiko.purge.completed",
    "zoiko.purge.failed",
    "zoiko.data.residency.assigned",       "zoiko.data.retention.assigned",
    "zoiko.data.retention.expired",
}


@dataclass
class KafkaMessage:
    """A single Kafka message with Zoiko envelope."""
    topic:           str
    key:             str                    # Partition key — usually case_id or tenant_id
    payload:         Dict[str, Any]
    tenant_id:       str
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:       datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version:  str = "1.0"
    # A-15 §8: event causality chain — set by callers that have a parent event
    correlation_id:  Optional[str] = None  # ties all events for one business transaction
    causation_id:    Optional[str] = None  # id of the event that directly caused this one

    def __post_init__(self):
        if self.topic not in REGISTERED_TOPICS:
            raise ValueError(f"Unknown topic '{self.topic}'. Must be one of: {sorted(REGISTERED_TOPICS)}")

    def to_bytes(self) -> bytes:
        envelope: Dict[str, Any] = {
            "schema_version":  self.schema_version,
            "tenant_id":       self.tenant_id,
            "idempotency_key": self.idempotency_key,
            "timestamp":       self.timestamp.isoformat(),
            "payload":         self.payload,
        }
        if self.correlation_id is not None:
            envelope["correlation_id"] = self.correlation_id
        if self.causation_id is not None:
            envelope["causation_id"] = self.causation_id
        return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def headers(self) -> list[tuple[str, bytes]]:
        hdrs = [
            ("tenant_id",       self.tenant_id.encode()),
            ("idempotency_key", self.idempotency_key.encode()),
            ("schema_version",  self.schema_version.encode()),
        ]
        if self.correlation_id is not None:
            hdrs.append(("correlation_id", self.correlation_id.encode()))
        if self.causation_id is not None:
            hdrs.append(("causation_id", self.causation_id.encode()))
        return hdrs


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
        """Publish all messages. Raises on first failure — earlier messages are already sent."""
        for msg in messages:
            self.publish(msg)

    def close(self) -> None:
        if hasattr(self._broker, "close"):
            self._broker.close()
