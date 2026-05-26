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
    schema_version: str = "1.0"
    occurred_at:    str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    producer:       str = "spiffe://zoiko.internal/service/unknown"
    traceparent:    Optional[str] = None
    correlation_id: Optional[str] = None
    causation_id:   Optional[str] = None
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
        return headers

    @classmethod
    def from_bytes(cls, data: bytes) -> "KafkaEventEnvelope":
        doc = json.loads(data.decode("utf-8"))
        env = cls.__new__(cls)
        for k, v in doc.items():
            object.__setattr__(env, k, v)
        return env
