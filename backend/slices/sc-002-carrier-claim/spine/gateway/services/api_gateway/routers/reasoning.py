"""Decision & Reasoning endpoints: reasoning trace, decision proposals, rule traces."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from services.api_gateway.auth import get_claims
from shared.db import q, q1

router = APIRouter(tags=["reasoning"])


def _assert_case(case_id: str, tenant_id: str):
    row = q1("SELECT id FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")


@router.get("/cases/{case_id}/reasoning")
def get_case_reasoning(case_id: str, claims=Depends(get_claims)):
    _assert_case(case_id, claims.tenant_id)

    # Findings
    findings = q("""
        SELECT id, case_id, finding_type, severity, confidence, summary, payload, created_at
        FROM findings WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY created_at
    """, (case_id, claims.tenant_id))

    # Rule traces
    traces = q("""
        SELECT id, validator_name, rule_id, result, executed_at
        FROM rule_traces WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY executed_at
    """, (case_id, claims.tenant_id))

    # Confidence assessments on this case's findings
    confidence = q("""
        SELECT subject_id, score, calibration_version, model_id, assessed_at
        FROM confidence_assessments
        WHERE tenant_id=%s::uuid AND subject_type='finding'
          AND subject_id IN (SELECT id FROM findings WHERE case_id=%s::uuid)
    """, (claims.tenant_id, case_id))

    return {
        "case_id": case_id,
        "findings": [{"id": str(f["id"]), "finding_type": f["finding_type"],
                      "severity": f["severity"],
                      "confidence": float(f["confidence"]) if f.get("confidence") else None,
                      "summary": f["summary"],
                      "created_at": f["created_at"].isoformat()} for f in findings],
        "rule_traces": [{"id": str(t["id"]), "validator": t["validator_name"],
                         "rule_id": t["rule_id"], "result": t["result"],
                         "executed_at": t["executed_at"].isoformat()} for t in traces],
        "confidence_assessments": [{"subject_id": str(c["subject_id"]),
                                    "score": float(c["score"]),
                                    "model_id": c["model_id"],
                                    "assessed_at": c["assessed_at"].isoformat()} for c in confidence],
    }


@router.get("/cases/{case_id}/decision-proposals")
def get_decision_proposals(case_id: str, claims=Depends(get_claims)):
    _assert_case(case_id, claims.tenant_id)
    rows = q("""
        SELECT id, case_id, action_type, evidence_bundle_id, confidence_score,
               recommended_amount, status, created_at
        FROM decision_proposals WHERE case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY created_at DESC
    """, (case_id, claims.tenant_id))
    return {"case_id": case_id, "proposals": [
        {"id": str(r["id"]), "action_type": r["action_type"],
         "evidence_bundle_id": str(r["evidence_bundle_id"]) if r.get("evidence_bundle_id") else None,
         "confidence_score": float(r["confidence_score"]) if r.get("confidence_score") else None,
         "recommended_amount": float(r["recommended_amount"]) if r.get("recommended_amount") else None,
         "status": r["status"], "created_at": r["created_at"].isoformat()} for r in rows
    ]}


@router.get("/cases/{case_id}/explanation")
def get_case_explanation(case_id: str, claims=Depends(get_claims)):
    _assert_case(case_id, claims.tenant_id)
    rows = q("""
        SELECT id, subject_type, subject_id, explanation, format, generated_by, created_at
        FROM explanation_artifacts WHERE case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY created_at DESC
    """, (case_id, claims.tenant_id))
    return {"case_id": case_id, "explanations": [
        {"id": str(r["id"]), "subject_type": r["subject_type"],
         "explanation": r["explanation"], "format": r["format"],
         "generated_by": r["generated_by"],
         "created_at": r["created_at"].isoformat()} for r in rows
    ]}
