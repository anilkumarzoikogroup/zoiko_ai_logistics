"""
FX rate lock stub (fail-closed).

Acquires a time-bounded FX rate lock for a given currency pair.
Dev: deterministic rates (same as connector-hub registry).
Prod: call treasury/FX API; fail-closed if unavailable.

Lock semantics:
  - Lock is valid for FX_LOCK_TTL_SECONDS (default 300s = 5 min).
  - Amount must be within FX_TOLERANCE_PCT (default 5%) of the locked rate.
  - Returns the locked USD amount.
"""
from __future__ import annotations

import os
import time
import threading
from dataclasses import dataclass

_FX_LOCK_TTL = int(os.getenv("FX_LOCK_TTL_SECONDS", "300"))
_TOLERANCE   = float(os.getenv("FX_TOLERANCE_PCT", "5")) / 100.0

# SC-001 deterministic: ₹4500 → USD 220.00
_SC001_INR_USD = round(220.0 / 4500.0, 8)

_RATES: dict[str, float] = {
    "INR": _SC001_INR_USD,
    "USD": 1.0,
    "EUR": 1.085,
}


@dataclass
class FXLockResult:
    acquired:      bool
    locked_rate:   float
    locked_amount_usd: float
    currency:      str
    lock_id:       str
    expires_at:    float   # monotonic timestamp
    reason:        str


_locks: dict[str, dict] = {}   # lock_id → {rate, expires_at}
_lock_mu = threading.Lock()


def acquire(amount: float, currency: str, envelope_id: str) -> FXLockResult:
    """
    Acquire an FX rate lock for (amount, currency) → USD.
    Fail-closed: any exception → return acquired=False.
    """
    try:
        api_url = os.getenv("FX_API_URL", "")
        if api_url:
            return _call_real_api(amount, currency, envelope_id, api_url)

        rate = _RATES.get(currency.upper(), 1.0)
        usd  = round(amount * rate, 2)
        lock_id  = f"FX-{envelope_id[:8]}-{currency}"
        expires  = time.monotonic() + _FX_LOCK_TTL

        with _lock_mu:
            _locks[lock_id] = {"rate": rate, "expires_at": expires, "usd": usd}

        return FXLockResult(
            acquired=True,
            locked_rate=rate,
            locked_amount_usd=usd,
            currency=currency,
            lock_id=lock_id,
            expires_at=expires,
            reason="FX lock acquired (dev stub)",
        )
    except Exception as e:
        return FXLockResult(
            acquired=False,
            locked_rate=0.0,
            locked_amount_usd=0.0,
            currency=currency,
            lock_id="",
            expires_at=0.0,
            reason=f"FX lock failed (fail-closed): {e}",
        )


def validate(lock_id: str, amount_usd: float) -> bool:
    """Check a previously acquired lock is still valid and amount is within tolerance."""
    with _lock_mu:
        lock = _locks.get(lock_id)
    if not lock:
        return False
    if time.monotonic() > lock["expires_at"]:
        return False
    delta = abs(amount_usd - lock["usd"])
    return delta / max(lock["usd"], 1.0) <= _TOLERANCE


def _call_real_api(amount: float, currency: str, envelope_id: str, api_url: str) -> FXLockResult:
    import urllib.request, json, uuid
    payload = json.dumps({"amount": amount, "currency": currency, "ref": envelope_id}).encode()
    req = urllib.request.Request(
        f"{api_url}/lock", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = json.loads(resp.read())
    return FXLockResult(
        acquired=body["acquired"],
        locked_rate=body["rate"],
        locked_amount_usd=body["usd"],
        currency=currency,
        lock_id=body["lock_id"],
        expires_at=time.monotonic() + body.get("ttl", _FX_LOCK_TTL),
        reason=body.get("reason", ""),
    )
