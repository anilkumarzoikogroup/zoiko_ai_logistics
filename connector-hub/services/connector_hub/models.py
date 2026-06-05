"""Connector-hub domain models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ClaimRequest:
    """Incoming carrier credit-memo claim."""
    carrier_id:      str
    envelope_id:     str          # Phase-4 execution envelope ID
    tenant_id:       str
    claimed_amount:  float
    currency:        str          # INR | USD | EUR
    invoice_ref:     str
    actor_sub:       str
    idempotency_key: str


@dataclass
class ClaimResponse:
    """Connector settlement response."""
    claim_ref:        str
    envelope_id:      str
    carrier_id:       str
    accepted:         bool
    accepted_amount:  float       # always USD for settlement
    original_amount:  float
    original_currency: str
    fx_rate:          float       # original_currency → USD
    status:           str         # ACCEPTED | REJECTED | PENDING
    reason:           str
    settled_at:       datetime


@dataclass
class ConnectorStatus:
    carrier_id:   str
    status:       str             # ACTIVE | INACTIVE | SUSPENDED
    certified_at: Optional[datetime]
    certified_by: Optional[str]
    circuit_state: str            # CLOSED | OPEN | HALF_OPEN


@dataclass
class CertifyRequest:
    carrier_id:   str
    actor_sub:    str
    reason:       str = ""
