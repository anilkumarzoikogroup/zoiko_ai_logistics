import paths  # noqa: F401
import uuid
import hashlib
import json
from datetime import datetime, timezone

from shared.db import q
from zoiko_common.crypto.jcs import canonicalize as jcs
from shared.signer import sign
from services.reasoning_svc.rules import compute_confidence


class ReasoningHandler:
    def __init__(self, db_url, broker, tenant_slug="default"):
        self.db_url = db_url
        self.broker = broker
        self.tenant_slug = tenant_slug

    def reason(self, tenant_id, case_id, bundle_id, charge_lines) -> dict:
        confidence, rule_trace = compute_confidence(charge_lines)

        dispute_total = sum(
            max(0, float(l["billed_amount"]) - float(l["contracted_cap"]))
            for l in charge_lines
        )

        now = datetime.now(timezone.utc)

        finding_dict = {
            "bundle_id": str(bundle_id),
            "case_id": str(case_id),
            "confidence": confidence,
            "rule_trace": rule_trace,
            "dispute_total": dispute_total,
            "tenant_id": tenant_id,
        }

        finding_bytes = jcs(finding_dict)
        finding_hash = hashlib.sha256(b"zoiko.finding.v1:" + finding_bytes).digest()
        f_sig, f_kid = sign(self.tenant_slug, finding_hash)

        finding_id = uuid.uuid4()

        q(
            """
            INSERT INTO findings
                (id, tenant_id, case_id, bundle_id, confidence, rule_trace,
                 finding_hash, signature, kid, created_at)
            VALUES
                (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                str(finding_id),
                tenant_id,
                str(case_id),
                str(bundle_id),
                confidence,
                json.dumps(rule_trace),
                finding_hash.hex(),
                f_sig.hex(),
                f_kid,
                now,
            ),
            self.db_url,
        )

        return {
            "finding_id": str(finding_id),
            "confidence": confidence,
            "rule_trace": rule_trace,
            "dispute_total": dispute_total,
            "disputed_lines": [
                l for l in charge_lines
                if float(l.get("billed_amount", 0)) > float(l.get("contracted_cap", 0))
            ],
        }
