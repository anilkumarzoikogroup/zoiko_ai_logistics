"""
Circuit breaker for outbound carrier connector calls.

States: CLOSED (normal) → OPEN (tripped) → HALF_OPEN (probing)

Transitions:
  CLOSED  → OPEN      : failure_count >= threshold (default 3)
  OPEN    → HALF_OPEN : recovery_timeout elapsed (default 30s)
  HALF_OPEN → CLOSED  : probe call succeeds
  HALF_OPEN → OPEN    : probe call fails (reset timer)

Backoff: exponential, capped at max_backoff_s (default 60s).
"""
from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class CircuitBreakerState:
    failures:         int   = 0
    state:            str   = "CLOSED"   # CLOSED | OPEN | HALF_OPEN
    last_failure_at:  float = 0.0
    backoff_s:        float = 1.0


class CircuitBreaker:
    def __init__(
        self,
        name:             str,
        failure_threshold: int   = 3,
        recovery_timeout_s: float = 30.0,
        max_backoff_s:    float  = 60.0,
    ) -> None:
        self.name               = name
        self._threshold         = failure_threshold
        self._recovery_timeout  = recovery_timeout_s
        self._max_backoff       = max_backoff_s
        self._state             = CircuitBreakerState()
        self._lock              = threading.Lock()

    # ── Public ──────────────────────────────────────────────────────────────────

    def call(self, fn: Callable[[], Any]) -> Any:
        """Execute fn through the circuit breaker. Raises CircuitOpenError if OPEN."""
        with self._lock:
            self._maybe_transition()
            if self._state.state == "OPEN":
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is OPEN — retry after "
                    f"{self._seconds_until_recovery():.0f}s"
                )

        try:
            result = fn()
        except Exception:
            self._record_failure()
            raise
        else:
            self._record_success()
            return result

    @property
    def state(self) -> str:
        with self._lock:
            self._maybe_transition()
            return self._state.state

    def reset(self) -> None:
        with self._lock:
            self._state = CircuitBreakerState()

    # ── Internal ─────────────────────────────────────────────────────────────────

    def _maybe_transition(self) -> None:
        """OPEN → HALF_OPEN if recovery window elapsed."""
        s = self._state
        if s.state == "OPEN":
            elapsed = time.monotonic() - s.last_failure_at
            if elapsed >= self._recovery_timeout:
                s.state = "HALF_OPEN"

    def _record_failure(self) -> None:
        with self._lock:
            s = self._state
            s.failures        += 1
            s.last_failure_at  = time.monotonic()
            s.backoff_s        = min(s.backoff_s * 2, self._max_backoff)
            if s.state in ("CLOSED", "HALF_OPEN") and s.failures >= self._threshold:
                s.state = "OPEN"

    def _record_success(self) -> None:
        with self._lock:
            s = self._state
            if s.state == "HALF_OPEN":
                self._state = CircuitBreakerState()   # fully reset
            elif s.state == "CLOSED":
                s.failures = 0
                s.backoff_s = 1.0

    def _seconds_until_recovery(self) -> float:
        elapsed = time.monotonic() - self._state.last_failure_at
        return max(0.0, self._recovery_timeout - elapsed)


class CircuitOpenError(RuntimeError):
    pass
