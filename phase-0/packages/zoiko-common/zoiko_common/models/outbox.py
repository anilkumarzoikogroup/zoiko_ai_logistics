"""
Outbox table model for reliable Kafka publishing (transactional outbox pattern).

The OutboxRelay polls this table and publishes to Kafka AFTER the DB transaction
commits. This ensures no message is lost if the service crashes between DB write
and Kafka publish.

Column layout matches the outbox table created in migration 0001.
"""
from __future__ import annotations

from sqlalchemy import Column, String, Boolean, DateTime, text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from zoiko_common.models.base import ZoikoBase, AppendOnlyMixin


class OutboxEvent(ZoikoBase, AppendOnlyMixin):
    """
    Transactional outbox event.

    Fields:
      id             — UUID PK
      tenant_id      — tenant scope
      topic          — Kafka topic (must be in REGISTERED_TOPICS)
      partition_key  — Kafka partition key (usually case_id or entity_id)
      payload        — JSONB event body
      published      — set to TRUE by OutboxRelay after Kafka ack
      created_at     — timestamp of DB write (same txn as business data)
      published_at   — timestamp of Kafka publish
    """
    __tablename__ = "outbox"

    topic         = Column(String(128), nullable=False)
    partition_key = Column(String(128), nullable=False)
    payload       = Column(JSONB, nullable=False)
    published     = Column(Boolean, nullable=False, server_default=text("FALSE"))
    published_at  = Column(DateTime(timezone=True), nullable=True)
