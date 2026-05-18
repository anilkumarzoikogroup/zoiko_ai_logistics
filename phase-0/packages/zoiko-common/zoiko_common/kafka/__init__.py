"""Kafka topic registry and partition key helpers for Zoiko services.

All 17 topics follow the same partition key convention:
  partition_key = f"{tenant_id}:{case_id}"

This guarantees ordered delivery per case, enabling deterministic FSM replay
from the Kafka log.
"""
from __future__ import annotations

from dataclasses import dataclass

# Canonical topic names — must match Strimzi KafkaTopic resources in kafka/
TOPICS = {
    "source-record-created": "zoiko.ingestion.source-record-created.v1",
    "validation-completed": "zoiko.validation.validation-completed.v1",
    "canonical-truth-created": "zoiko.canonical.canonical-truth-created.v1",
    "case-opened": "zoiko.case.case-opened.v1",
    "case-state-changed": "zoiko.case.case-state-changed.v1",
    "evidence-bundle-created": "zoiko.evidence.evidence-bundle-created.v1",
    "finding-generated": "zoiko.reasoning.finding-generated.v1",
    "decision-proposed": "zoiko.reasoning.decision-proposed.v1",
    "governance-review-requested": "zoiko.governance.governance-review-requested.v1",
    "governance-decision-made": "zoiko.governance.governance-decision-made.v1",
    "token-issued": "zoiko.token.token-issued.v1",
    "execution-requested": "zoiko.execution.execution-requested.v1",
    "execution-completed": "zoiko.execution.execution-completed.v1",
    "reconciliation-completed": "zoiko.reconciliation.reconciliation-completed.v1",
    "acr-created": "zoiko.audit.acr-created.v1",
    "outbox-relay": "zoiko.infra.outbox-relay.v1",
    "dead-letter": "zoiko.infra.dead-letter.v1",
}


def partition_key(tenant_id: str, case_id: str) -> str:
    """Return the Kafka partition key that guarantees per-case ordering."""
    return f"{tenant_id}:{case_id}"


@dataclass(frozen=True)
class KafkaMessage:
    topic: str
    key: str       # partition key
    value: bytes   # serialised event payload
    headers: dict[str, str]
