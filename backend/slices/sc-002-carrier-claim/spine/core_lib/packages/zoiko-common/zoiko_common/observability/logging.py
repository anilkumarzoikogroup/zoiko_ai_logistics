"""
Structured JSON logging for Zoiko services.

All log records include:
  - service   — name of the emitting service
  - tenant_id — current request tenant (injected via contextvars)
  - trace_id  — W3C traceparent trace-id segment (injected via contextvars)
  - level, message, timestamp
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

_current_tenant: ContextVar[Optional[str]] = ContextVar("current_tenant", default=None)
_current_trace:  ContextVar[Optional[str]] = ContextVar("current_trace",  default=None)


def set_tenant(tenant_id: str) -> None:
    _current_tenant.set(tenant_id)


def set_trace(trace_id: str) -> None:
    _current_trace.set(trace_id)


class _JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        doc = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level":     record.levelname,
            "service":   self._service,
            "message":   record.getMessage(),
            "logger":    record.name,
        }
        if record.exc_info:
            doc["exception"] = self.formatException(record.exc_info)
        tenant = _current_tenant.get()
        if tenant:
            doc["tenant_id"] = tenant
        trace = _current_trace.get()
        if trace:
            doc["trace_id"] = trace
        return json.dumps(doc, ensure_ascii=False)


def configure(service: str, level: str = "INFO") -> None:
    """Configure root logger with JSON output for the given service name."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter(service))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
