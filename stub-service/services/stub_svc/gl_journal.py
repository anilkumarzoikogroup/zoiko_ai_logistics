"""
GL (General Ledger) journal stub (fail-closed).

Posts a debit/credit journal entry to the accounting system.
Dev: logs in-memory, always succeeds.
Prod: POST to ERP/GL API; fail-closed if unavailable.

Journal entry format (double-entry):
  DR  Accounts Receivable  <amount USD>
  CR  Freight Overcharge Recovery  <amount USD>
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List


@dataclass
class JournalEntry:
    entry_id:      str
    envelope_id:   str
    tenant_id:     str
    debit_account: str
    credit_account: str
    amount_usd:    float
    description:   str
    posted_at:     datetime
    status:        str   # POSTED | FAILED | PENDING


@dataclass
class GLJournalResult:
    posted:     bool
    entry_id:   str
    reason:     str


# In-memory journal for dev/test
_journal: List[JournalEntry] = []


def post_entry(
    envelope_id: str,
    tenant_id:   str,
    amount_usd:  float,
    description: str = "Freight overcharge recovery credit",
) -> GLJournalResult:
    """
    Post a double-entry journal record.
    Fail-closed: any exception → return posted=False.
    """
    try:
        api_url = os.getenv("GL_API_URL", "")
        if api_url:
            return _call_real_api(envelope_id, tenant_id, amount_usd, description, api_url)

        entry = JournalEntry(
            entry_id       = str(uuid.uuid4()),
            envelope_id    = envelope_id,
            tenant_id      = tenant_id,
            debit_account  = "1200-Accounts-Receivable",
            credit_account = "4500-Freight-Overcharge-Recovery",
            amount_usd     = amount_usd,
            description    = description,
            posted_at      = datetime.now(timezone.utc),
            status         = "POSTED",
        )
        _journal.append(entry)
        return GLJournalResult(posted=True, entry_id=entry.entry_id, reason="Posted (dev stub)")

    except Exception as e:
        return GLJournalResult(posted=False, entry_id="", reason=f"GL post failed (fail-closed): {e}")


def get_entries(tenant_id: str) -> List[JournalEntry]:
    return [e for e in _journal if e.tenant_id == tenant_id]


def _call_real_api(
    envelope_id: str, tenant_id: str, amount_usd: float, description: str, api_url: str,
) -> GLJournalResult:
    import urllib.request, json
    payload = json.dumps({
        "envelope_id": envelope_id,
        "tenant_id": tenant_id,
        "amount_usd": amount_usd,
        "description": description,
        "debit_account":  "1200-Accounts-Receivable",
        "credit_account": "4500-Freight-Overcharge-Recovery",
    }).encode()
    req = urllib.request.Request(
        f"{api_url}/journal", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = json.loads(resp.read())
    return GLJournalResult(
        posted=body["posted"],
        entry_id=body.get("entry_id", ""),
        reason=body.get("reason", ""),
    )
