"""
Security event publisher (FR-024).

Publishes security-relevant events to the zoiko.security.event-detected.v1 topic.
Three event kinds are defined:

  CROSS_TENANT_ACCESS   — a request attempted to access data belonging to a different tenant
  TOKEN_REPLAY          — a governance token was presented after being consumed (replay attack)
  FORBIDDEN_FSM_TRANSITION — a case state transition was attempted that violates the FSM

All events are published asynchronously and never block the request path.
If the broker is unavailable, the event is logged at WARNING level and dropped
(security events must NOT cause request failures).

Usage:
  from zoiko_common.security.events import SecurityEventPublisher, SecurityEventKind

  _sec = SecurityEventPublisher(broker=_BROKER)

  # In a route handler:
  _sec.publish(SecurityEventKind.CROSS_TENANT_ACCESS, tenant_id, {
      "actor_sub":        claims.sub,
      "requested_tenant": bad_tenant_id,
      "route":            request.url.path,
  })
"""
from __future__ import annotations

import logging
import threading
import uuid
from enum import Enum
from typing import Any, Dict

logger = logging.getLogger(__name__)

_SECURITY_TOPIC = "zoiko.security.event-detected.v1"


class SecurityEventKind(str, Enum):
    CROSS_TENANT_ACCESS        = "CROSS_TENANT_ACCESS"
    TOKEN_REPLAY               = "TOKEN_REPLAY"
    FORBIDDEN_FSM_TRANSITION   = "FORBIDDEN_FSM_TRANSITION"


class SecurityEventPublisher:
    """
    Thin wrapper that formats and publishes security events to Kafka.

    Thread-safe: publish() dispatches on a daemon thread so it never blocks.
    """

    def __init__(self, broker: Any) -> None:
        self._broker = broker

    def publish(
        self,
        kind: SecurityEventKind,
        tenant_id: str,
        details: Dict[str, Any],
        correlation_id: str | None = None,
    ) -> None:
        """
        Fire-and-forget security event. Never raises — logs on error.
        """
        event_id = str(uuid.uuid4())
        payload = {
            "event_id":       event_id,
            "kind":           kind.value,
            "tenant_id":      tenant_id,
            "correlation_id": correlation_id,
            "details":        details,
        }
        t = threading.Thread(
            target=self._send,
            args=(tenant_id, event_id, payload),
            daemon=True,
            name=f"sec-event-{event_id[:8]}",
        )
        t.start()

    def _send(self, tenant_id: str, event_id: str, payload: dict) -> None:
        try:
            from zoiko_common.kafka.schemas import KafkaEventEnvelope
            env = KafkaEventEnvelope(
                topic          = _SECURITY_TOPIC,
                tenant_id      = tenant_id,
                aggregate_type = "security_event",
                aggregate_id   = event_id,
                payload        = payload,
                producer       = "spiffe://zoiko.internal/service/security-publisher",
            )
            self._broker.send(
                topic   = _SECURITY_TOPIC,
                key     = tenant_id.encode(),
                value   = env.to_bytes(),
                headers = env.headers(),
            )
            logger.info(
                "security_event published kind=%s tenant=%s event_id=%s",
                payload["kind"], tenant_id, event_id,
            )
        except Exception as exc:
            logger.warning(
                "security_event publish failed (dropped) kind=%s error=%s",
                payload.get("kind"), exc,
            )
