"""
Kafka abstractions for Zoiko services.

All 17 registered topics follow the convention: zoiko.<aggregate>.<event>

Topic partition key convention:
  partition_key = f"{tenant_id}:{case_id}"
  This guarantees ordered delivery per case, enabling deterministic FSM replay.

Public API:
  TOPICS              — dict of short alias → full topic name
  REGISTERED_TOPICS   — set of all valid full topic names
  KafkaEventEnvelope  — standard event wrapper (use this for all publishes)
  OutboxRelay         — polls outbox table and publishes to Kafka
  partition_key()     — build a standard partition key string
"""
from __future__ import annotations

from zoiko_common.kafka.schemas import TOPICS, REGISTERED_TOPICS, KafkaEventEnvelope, KafkaMessage
from zoiko_common.kafka.outbox_relay import OutboxRelay


def partition_key(tenant_id: str, case_id: str) -> str:
    """Return the Kafka partition key that guarantees per-case ordering."""
    return f"{tenant_id}:{case_id}"


__all__ = [
    "TOPICS",
    "REGISTERED_TOPICS",
    "KafkaEventEnvelope",
    "KafkaMessage",
    "OutboxRelay",
    "partition_key",
]
