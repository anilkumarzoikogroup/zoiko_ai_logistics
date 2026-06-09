"""Redis-backed idempotency key helpers for Zoiko services.

Pattern:
  1. Check: SETNX idempotency:<tenant_id>:<idempotency_key> → IN_PROGRESS (TTL 24h)
     - Returns False if key already exists (replay detected)
  2. Process request
  3. Finalise: SET idempotency:<tenant_id>:<idempotency_key> COMPLETE (no TTL)
     - Marks as permanently done

If a request arrives while status=IN_PROGRESS it should 409 (concurrent replay).
If status=COMPLETE it should return the cached response (idempotent replay).

The 5-step ingestion write pattern stores the Redis key AFTER the DB commit
(step 5) so a crash between DB commit and Redis write is safe — the next
attempt will re-check the DB via the outbox and can recover.
"""
from __future__ import annotations

from enum import Enum

class StrEnum(str, Enum):
    pass

import redis.asyncio as aioredis

_KEY_PREFIX = "idempotency"
_TTL_IN_PROGRESS = 86_400  # 24 hours in seconds


class IdempotencyStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"


class IdempotencyStore:
    def __init__(self, client: aioredis.Redis) -> None:
        self._r = client

    def _key(self, tenant_id: str, idempotency_key: str) -> str:
        return f"{_KEY_PREFIX}:{tenant_id}:{idempotency_key}"

    async def acquire(self, tenant_id: str, idempotency_key: str) -> bool:
        """Try to claim the key.  Returns True if acquired (first request),
        False if already IN_PROGRESS or COMPLETE (replay).
        """
        k = self._key(tenant_id, idempotency_key)
        acquired = await self._r.set(
            k,
            IdempotencyStatus.IN_PROGRESS,
            nx=True,
            ex=_TTL_IN_PROGRESS,
        )
        return bool(acquired)

    async def status(self, tenant_id: str, idempotency_key: str) -> IdempotencyStatus | None:
        k = self._key(tenant_id, idempotency_key)
        val = await self._r.get(k)
        if val is None:
            return None
        return IdempotencyStatus(val.decode() if isinstance(val, bytes) else val)

    async def complete(self, tenant_id: str, idempotency_key: str) -> None:
        """Mark key as permanently COMPLETE (no TTL — survives forever)."""
        k = self._key(tenant_id, idempotency_key)
        await self._r.set(k, IdempotencyStatus.COMPLETE)
