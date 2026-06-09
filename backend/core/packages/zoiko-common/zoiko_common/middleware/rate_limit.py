"""
Sliding-window rate limiter middleware (T-024).

Limits per (tenant_id, route_class):
  ingestion   — 100 req/min  (POST /v1/ingestion/*)
  governance  — 20  req/min  (POST /v1/cases/*/propose, /v1/cases/*/decide, /v1/evidence/*)
  execution   — 10  req/min  (POST /v1/execute)

In dev: rate limiting is disabled unless ZOIKO_RATE_LIMIT_ENABLED=true.
In prod: set ZOIKO_RATE_LIMIT_ENABLED=true (always true in real deployments).

Usage in FastAPI:
  from zoiko_common.middleware.rate_limit import RateLimitMiddleware
  app.add_middleware(RateLimitMiddleware)

  # Or use as a dependency on specific routes:
  from zoiko_common.middleware.rate_limit import require_rate_limit
  @router.post("/execute")
  def execute(claims=Depends(get_claims), _=Depends(require_rate_limit("execution"))):
      ...
"""
from __future__ import annotations

import os
import time
import threading
import collections
from typing import Callable

_ENABLED = os.getenv("ZOIKO_RATE_LIMIT_ENABLED", "false").lower() == "true"

# Limits: requests per 60-second window
_LIMITS: dict[str, int] = {
    "ingestion":  int(os.getenv("RATE_LIMIT_INGESTION",  "100")),
    "governance": int(os.getenv("RATE_LIMIT_GOVERNANCE", "20")),
    "execution":  int(os.getenv("RATE_LIMIT_EXECUTION",  "10")),
    "default":    int(os.getenv("RATE_LIMIT_DEFAULT",    "200")),
}

_WINDOW = 60   # seconds


class RateLimitExceeded(Exception):
    def __init__(self, route_class: str, limit: int, window: int):
        self.route_class = route_class
        self.limit       = limit
        self.window      = window
        super().__init__(f"Rate limit exceeded: {limit} req/{window}s for '{route_class}'")


class _SlidingWindowCounter:
    """Thread-safe per-key sliding window counter."""

    def __init__(self) -> None:
        self._windows: dict[str, collections.deque] = {}
        self._lock = threading.Lock()

    def check_and_increment(self, key: str, limit: int, window: int) -> bool:
        """
        Returns True if the request is allowed, False if rate-limited.
        Atomically records the request timestamp if allowed.
        """
        now = time.monotonic()
        cutoff = now - window
        with self._lock:
            dq = self._windows.setdefault(key, collections.deque())
            # Evict timestamps outside the window
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True

    def current_count(self, key: str, window: int) -> int:
        now    = time.monotonic()
        cutoff = now - window
        with self._lock:
            dq = self._windows.get(key, collections.deque())
            return sum(1 for ts in dq if ts >= cutoff)


_counter = _SlidingWindowCounter()


def _route_class(path: str, method: str) -> str:
    """Classify a request path into a rate-limit bucket."""
    path = path.lower()
    if method == "POST" and ("/ingestion/" in path or "/parse-invoice" in path):
        return "ingestion"
    if method == "POST" and (
        "/propose" in path or "/decide" in path or
        "/evidence/" in path or "/transition" in path
    ):
        return "governance"
    if method == "POST" and "/execute" in path:
        return "execution"
    return "default"


def check_rate_limit(tenant_id: str, route_class: str) -> None:
    """
    Raise RateLimitExceeded if this tenant has exceeded the limit for route_class.
    No-op if ZOIKO_RATE_LIMIT_ENABLED=false.
    """
    if not _ENABLED:
        return
    limit = _LIMITS.get(route_class, _LIMITS["default"])
    key   = f"{tenant_id}:{route_class}"
    if not _counter.check_and_increment(key, limit, _WINDOW):
        raise RateLimitExceeded(route_class, limit, _WINDOW)


# ── FastAPI ASGI middleware ────────────────────────────────────────────────────

class RateLimitMiddleware:
    """
    Starlette/FastAPI ASGI middleware.
    Reads X-Tenant-ID header; returns 429 on limit exceeded.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and _ENABLED:
            path   = scope.get("path", "")
            method = scope.get("method", "GET")
            rclass = _route_class(path, method)
            if rclass != "default":
                headers = dict(scope.get("headers", []))
                tenant_id = (
                    headers.get(b"x-tenant-id", b"").decode() or "anonymous"
                )
                limit = _LIMITS.get(rclass, _LIMITS["default"])
                key   = f"{tenant_id}:{rclass}"
                if not _counter.check_and_increment(key, limit, _WINDOW):
                    body = (
                        f'{{"detail":"Rate limit exceeded: {limit} req/min '
                        f'for {rclass} endpoints"}}'
                    ).encode()
                    await send({
                        "type": "http.response.start",
                        "status": 429,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                            (b"retry-after", b"60"),
                        ],
                    })
                    await send({"type": "http.response.body", "body": body})
                    return
        await self.app(scope, receive, send)


# ── FastAPI dependency ────────────────────────────────────────────────────────

def require_rate_limit(route_class: str) -> Callable:
    """FastAPI dependency. Use as: Depends(require_rate_limit('execution'))"""
    from fastapi import Depends, Header, HTTPException

    def _dep(x_tenant_id: str = Header("anonymous", alias="X-Tenant-ID")):
        try:
            check_rate_limit(x_tenant_id, route_class)
        except RateLimitExceeded as e:
            raise HTTPException(
                status_code=429,
                detail=str(e),
                headers={"Retry-After": "60"},
            )

    return _dep
