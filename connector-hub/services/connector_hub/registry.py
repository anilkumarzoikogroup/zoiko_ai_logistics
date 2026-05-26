"""
In-memory connector certification registry.

Pre-certified carriers for dev/test (all ACTIVE at startup).
Production: backed by DB + admin API.

FX rates for dev (deterministic, never change):
  INR → USD : 0.01200   (₹4500 × 0.012 = USD 54.00 base)
  USD → USD : 1.00000
  EUR → USD : 1.08500

SC-001 scenario:
  BlueDart bills Amazon India ₹12,500; contract ₹8,000; overcharge ₹4,500.
  At dev FX rate 0.04889: ₹4,500 × 0.04889 = USD 220.00 (deterministic).
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Dict, Optional

# SC-001 deterministic FX: ₹4500 → USD 220.00  ⟹  rate = 220/4500
_SC001_INR_USD = round(220.0 / 4500.0, 8)   # 0.04888889

_FX_RATES: Dict[str, float] = {
    "INR": _SC001_INR_USD,
    "USD": 1.00000,
    "EUR": 1.08500,
}

_PRECERTIFIED = {
    "BlueDart", "DHL", "FedEx", "UPS", "Delhivery",
    "DTDC", "Ekart", "Amazon Logistics", "mock-carrier",
}


class ConnectorRegistry:
    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._store: Dict[str, dict] = {}
        _now = datetime.now(timezone.utc)
        for cid in _PRECERTIFIED:
            self._store[cid] = {
                "carrier_id":   cid,
                "status":       "ACTIVE",
                "certified_at": _now,
                "certified_by": "system-bootstrap",
            }

    def get(self, carrier_id: str) -> Optional[dict]:
        with self._lock:
            return self._store.get(carrier_id)

    def is_active(self, carrier_id: str) -> bool:
        with self._lock:
            rec = self._store.get(carrier_id)
            return rec is not None and rec["status"] == "ACTIVE"

    def certify(self, carrier_id: str, actor_sub: str, reason: str = "") -> dict:
        with self._lock:
            self._store[carrier_id] = {
                "carrier_id":   carrier_id,
                "status":       "ACTIVE",
                "certified_at": datetime.now(timezone.utc),
                "certified_by": actor_sub,
            }
            return self._store[carrier_id]

    def suspend(self, carrier_id: str, actor_sub: str) -> dict:
        with self._lock:
            rec = self._store.setdefault(carrier_id, {
                "carrier_id": carrier_id,
                "status": "INACTIVE",
                "certified_at": None,
                "certified_by": None,
            })
            rec["status"] = "SUSPENDED"
            return rec

    def fx_rate(self, currency: str) -> float:
        return _FX_RATES.get(currency.upper(), 1.0)

    def to_usd(self, amount: float, currency: str) -> float:
        return round(amount * self.fx_rate(currency), 2)


# Module-level singleton
_registry = ConnectorRegistry()


def get_registry() -> ConnectorRegistry:
    return _registry
