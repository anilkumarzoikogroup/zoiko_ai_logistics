"""
KafkaEventEnvelope — the standard Zoiko event wrapper for all 17 topics.

Every event published to Kafka MUST be serialized as a KafkaEventEnvelope.
The envelope provides:
  - Idempotent delivery (event_id dedup)
  - Schema versioning
  - Distributed tracing (traceparent, correlation_id, causation_id)
  - Cross-service audit trail (producer SPIFFE URI)
  - Payload integrity (payload_hash = SHA-256 of JCS payload bytes)
  - Tenant isolation (tenant_id on every message)
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from zoiko_common.crypto.jcs import canonicalize

# ── Canonical topic registry — 17 topics, zoiko.<aggregate>.<event> ──────────

TOPICS: Dict[str, str] = {
    # Phase 2 — Ingestion pipeline
    "source.record.received":    "zoiko.ingestion.source-record-received.v1",
    "source.record.validated":   "zoiko.ingestion.source-record-validated.v1",
    "canonical.invoice.created": "zoiko.ingestion.canonical-invoice-created.v1",
    # Case orchestration
    "case.opened":               "zoiko.case.case-opened.v1",
    "case.updated":              "zoiko.case.case-updated.v1",
    "case.closed":               "zoiko.case.case-closed.v1",
    # Phase 3 — Governance pipeline
    "evidence.bundled":          "zoiko.governance.evidence-bundled.v1",
    "finding.generated":         "zoiko.governance.finding-generated.v1",
    "proposal.created":          "zoiko.governance.proposal-created.v1",
    "governance.decision.issued":"zoiko.governance.decision-issued.v1",
    "governance.token.issued":   "zoiko.governance.token-issued.v1",
    "governance.token.consumed": "zoiko.governance.token-consumed.v1",
    # Phase 4 — Execution pipeline
    "execution.dispatched":      "zoiko.execution.dispatched.v1",
    "execution.completed":       "zoiko.execution.completed.v1",
    "reconciliation.updated":    "zoiko.execution.reconciliation-updated.v1",
    "acr.generated":             "zoiko.audit.acr-generated.v1",
    "audit.artifact.written":    "zoiko.audit.artifact-written.v1",
    # FR-024 — security event stream (cross-tenant, token replay, forbidden transitions)
    "security.event.detected":   "zoiko.security.event-detected.v1",
}

REGISTERED_TOPICS = set(TOPICS.values())

# Operational topic names used by ZoikoProducer and written to the outbox table.
# Kept in sync with REGISTERED_TOPICS in phase-1/kafka/producer.py.
# The outbox relay validates against this copy (producer.py is in a different package).
PRODUCER_TOPICS: set = {
    # Core pipeline
    "zoiko.source.record.received",     "zoiko.source.record.validated",    "zoiko.canonical.invoice.created",
    "zoiko.canonical.claim.created",    # SC-002 — canonicalize_claim()
    "zoiko.case.opened",                "zoiko.case.updated",               "zoiko.case.closed",
    "zoiko.evidence.bundled",           "zoiko.finding.generated",          "zoiko.proposal.created",
    "zoiko.governance.decision.issued", "zoiko.governance.token.issued",    "zoiko.governance.token.consumed",
    "zoiko.execution.dispatched",       "zoiko.execution.completed",
    "zoiko.reconciliation.updated",     "zoiko.acr.generated",              "zoiko.audit.artifact.written",
    # Security event stream (FR-024)
    "zoiko.security.event-detected.v1",
    # Retry topics — transient failures re-queued for backoff/retry
    "zoiko.evidence.bundled.retry",           "zoiko.finding.generated.retry",
    "zoiko.governance.decision.issued.retry", "zoiko.governance.token.issued.retry",
    "zoiko.execution.dispatched.retry",       "zoiko.reconciliation.updated.retry",
    # DLQ topics — exhausted retries land here for manual review / alerting
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
}


@dataclass
class KafkaMessage:
    """Low-level Kafka transport message.  No topic validation — use for raw send/receive."""
    topic:   str
    key:     str
    value:   bytes
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class KafkaEventEnvelope:
    """
    Standard Zoiko Kafka event envelope (spec §9.1).

    Fields:
      event_id        — UUID4, globally unique, used for dedup
      schema_version  — semver string e.g. "1.0"
      tenant_id       — UUID string, RLS partition key
      aggregate_type  — e.g. "case", "source_record", "governance_token"
      aggregate_id    — UUID string of the aggregate root
      occurred_at     — ISO-8601 UTC timestamp of the domain event
      producer        — SPIFFE URI of the publishing service
      traceparent     — W3C trace context header value
      correlation_id  — UUID linking events across a business transaction
      causation_id    — event_id of the event that caused this one
      payload_hash    — SHA-256 hex of JCS-serialised payload (integrity check)
      payload         — the domain event data dict
      signature       — Ed25519 hex signature over payload_hash (optional in dev)
    """
    topic:          str
    tenant_id:      str
    aggregate_type: str
    aggregate_id:   str
    payload:        Dict[str, Any]

    event_id:       str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: str = "1.1"
    occurred_at:    str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    producer:       str = "spiffe://zoiko.internal/service/unknown"
    traceparent:    Optional[str] = None
    correlation_id: Optional[str] = None
    causation_id:   Optional[str] = None
    # Actor that triggered the event (USER | SERVICE | SYSTEM)
    actor_type:     Optional[str] = None
    actor_id:       Optional[str] = None
    payload_hash:   str = field(init=False)
    signature:      Optional[str] = None

    def __post_init__(self) -> None:
        if self.topic not in REGISTERED_TOPICS:
            raise ValueError(
                f"Unknown topic '{self.topic}'. Must be one of: {sorted(REGISTERED_TOPICS)}"
            )
        payload_bytes = canonicalize(self.payload)
        self.payload_hash = hashlib.sha256(payload_bytes).hexdigest()

    def to_bytes(self) -> bytes:
        """Serialise envelope to UTF-8 bytes (JCS-sorted keys for determinism)."""
        doc = {
            "actor_id":        self.actor_id,
            "actor_type":      self.actor_type,
            "aggregate_id":    self.aggregate_id,
            "aggregate_type":  self.aggregate_type,
            "causation_id":    self.causation_id,
            "correlation_id":  self.correlation_id,
            "event_id":        self.event_id,
            "occurred_at":     self.occurred_at,
            "payload":         self.payload,
            "payload_hash":    self.payload_hash,
            "producer":        self.producer,
            "schema_version":  self.schema_version,
            "signature":       self.signature,
            "tenant_id":       self.tenant_id,
            "topic":           self.topic,
            "traceparent":     self.traceparent,
        }
        return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def headers(self) -> list[tuple[str, bytes]]:
        headers = [
            ("tenant_id",      self.tenant_id.encode()),
            ("event_id",       self.event_id.encode()),
            ("schema_version", self.schema_version.encode()),
            ("aggregate_type", self.aggregate_type.encode()),
        ]
        if self.correlation_id:
            headers.append(("correlation_id", self.correlation_id.encode()))
        if self.traceparent:
            headers.append(("traceparent", self.traceparent.encode()))
        if self.actor_type:
            headers.append(("actor_type", self.actor_type.encode()))
        if self.actor_id:
            headers.append(("actor_id", self.actor_id.encode()))
        return headers

    @classmethod
    def from_bytes(cls, data: bytes) -> "KafkaEventEnvelope":
        doc = json.loads(data.decode("utf-8"))
        # Reconstruct via __init__ so __post_init__ runs validation and
        # recomputes payload_hash — prevents tampered messages from bypassing
        # the integrity check by supplying a forged payload_hash field.
        return cls(
            topic          = doc["topic"],
            tenant_id      = doc["tenant_id"],
            aggregate_type = doc["aggregate_type"],
            aggregate_id   = doc["aggregate_id"],
            payload        = doc["payload"],
            event_id       = doc.get("event_id", str(uuid.uuid4())),
            schema_version = doc.get("schema_version", "1.1"),
            occurred_at    = doc.get("occurred_at", datetime.now(timezone.utc).isoformat()),
            producer       = doc.get("producer", "spiffe://zoiko.internal/service/unknown"),
            traceparent    = doc.get("traceparent"),
            correlation_id = doc.get("correlation_id"),
            causation_id   = doc.get("causation_id"),
            actor_type     = doc.get("actor_type"),
            actor_id       = doc.get("actor_id"),
            signature      = doc.get("signature"),
        )
