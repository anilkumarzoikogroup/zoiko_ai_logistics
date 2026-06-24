"""
SQLAlchemy declarative base with tenant-scoped audit columns (FR-003).

Every table that extends ZoikoBase automatically gets:
  - id          (UUID primary key)
  - tenant_id   (UUID, not null — Row Level Security column)
  - created_at  (timestamptz, server default NOW())

Append-only tables (case_events, lineage_records, etc.) should NOT have
updated_at — mutations on them are prohibited by the 9 non-negotiable rules.

Usage:
  from zoiko_common.models.base import ZoikoBase, AppendOnlyMixin
  from sqlalchemy import Column, String

  class MyTable(ZoikoBase):
      __tablename__ = "my_table"
      name = Column(String, nullable=False)

  class MyAuditLog(ZoikoBase, AppendOnlyMixin):
      __tablename__ = "my_audit_log"
      event_type = Column(String, nullable=False)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class ZoikoBase(DeclarativeBase):
    """Base class for all Zoiko database models."""

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class AppendOnlyMixin:
    """
    Marker mixin for append-only tables.

    Tables with this mixin must NEVER have UPDATE or DELETE executed against them.
    Enforced by convention + OPA policy (not by SQLAlchemy itself).

    Included in: lineage_records, case_events, evidence_items, audit_worm_index.
    """
    __append_only__ = True
