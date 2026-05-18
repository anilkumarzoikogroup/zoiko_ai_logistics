# Phase 1 — KMS · OIDC · Kafka · OPA

**Timeline:** Week 5–6  |  **Status:** ✅ BUILT

Phase 0 is complete (see `../phase-0/`). Phase 1 builds the four security and messaging
pillars that every Phase 2+ microservice depends on.

---

## What Got Built

| Component | Files | Purpose |
|-----------|-------|---------|
| **KMS Key Hierarchy** | `packages/zoiko-kms/` | 3-tier key hierarchy: Root CA → DEK → Signing |
| **OIDC Middleware**   | `middleware/oidc/`    | JWT validation + tenant binding for FastAPI |
| **Kafka Abstractions**| `kafka/`              | Producer, consumer, mock broker (17 topics) |
| **OPA Policy Scaffold**| `middleware/opa/` + `opa/policies/` | Fail-closed policy enforcement |

---

## Folder Structure

```
phase-1/
├── packages/
│   └── zoiko-kms/              # KMS key hierarchy package
│       ├── zoiko_kms/
│       │   ├── hierarchy.py    # KeyHierarchy, KeyRecord, KeyPurpose
│       │   ├── local_backend.py# Ed25519 signing + AES-like encrypt (dev)
│       │   └── gcp_stub.py     # GCP Cloud KMS typed stub (Phase 4)
│       ├── tests/
│       │   └── test_hierarchy.py
│       └── pyproject.toml
├── middleware/
│   ├── oidc/
│   │   ├── claims.py           # ZoikoClaims, TenantContext dataclasses
│   │   ├── middleware.py       # FastAPI OIDCMiddleware (Bearer + X-Tenant-ID)
│   │   ├── token_verifier.py   # HS256 (dev) + RS256/ES256 stub (prod)
│   │   └── tenant_context.py  # FastAPI Depends: require_tenant, require_role
│   └── opa/
│       ├── client.py           # OPAClient (fail-closed), MockOPAClient
│       └── middleware.py       # FastAPI OPAMiddleware (tenant isolation)
├── kafka/
│   ├── producer.py             # ZoikoProducer — KafkaMessage + 17 topics
│   ├── consumer.py             # ZoikoConsumer — group offset tracking
│   └── mock_kafka.py           # MockKafkaBroker — in-memory, no cluster needed
├── opa/
│   └── policies/
│       ├── freight_dispute.rego  # Allow/deny rules for SC-001 actions
│       └── tenant_isolation.rego # Hard tenant boundary check (runs first)
├── tests/
│   ├── test_oidc_middleware.py
│   ├── test_kafka_mock.py
│   └── test_opa_client.py
├── pyproject.toml
└── README.md
```

---

## Quick Start

```bash
# Install dependencies
cd phase-1
py -3.13 -m pip install -e "packages/zoiko-kms[dev]"
py -3.13 -m pip install cryptography fastapi starlette python-jose pytest pytest-cov

# Run all Phase 1 tests
py -3.13 -m pytest tests/ packages/zoiko-kms/tests/ -v

# Run with coverage
py -3.13 -m pytest tests/ packages/zoiko-kms/tests/ --cov=middleware --cov=kafka --cov=zoiko_kms
```

---

## Component Details

### 1. KMS Key Hierarchy
Three-tier hierarchy per tenant:
```
Root CA Key  →  Tenant DEK (Data Encryption Key)  →  Tenant Signing Key
```
- **Dev**: `LocalKMSBackend` — real Ed25519 keys, ephemeral in-process
- **Staging/Prod**: `GcpKMSStub` — typed interface, wired to Cloud KMS in Phase 4
- Key rotation: `hierarchy.rotate_key(tenant_id, purpose)` → new version, old marked inactive
- **Rule**: SOFTWARE keys are not allowed in prod (raises RuntimeError)

### 2. OIDC Middleware
Every FastAPI request must carry:
```
Authorization: Bearer <JWT>
X-Tenant-ID:   <tenant_uuid>
```
- **Dev**: HS256 tokens via `TokenVerifier.make_dev_token()`
- **Prod**: RS256/ES256 verified against JWKS endpoint
- Tenant binding: `JWT.tenant_id` must match `X-Tenant-ID` header — 403 if mismatch
- FastAPI dependency: `Depends(require_tenant)`, `Depends(require_role("manager"))`

### 3. Kafka Abstractions
All 17 registered topics:
```
invoice.received    invoice.validated    invoice.canonical
case.opened         case.updated         case.closed
evidence.bundled    finding.created      proposal.created
decision.made       token.issued         token.consumed
execution.started   execution.completed
reconciliation.done acr.issued           audit.locked
```
- Every message carries `tenant_id` + `idempotency_key` in headers
- `MockKafkaBroker` for local dev — no Kafka cluster needed
- Real `kafka-python` client wired in Phase 2 GKE deploy

### 4. OPA Policy Scaffold
**Rule 5 (non-negotiable):** OPA unreachable → 503. Never permit.

Policies:
| Policy | Package | What it enforces |
|--------|---------|-----------------|
| `freight_dispute.rego` | `zoiko.freight_dispute` | Analyst proposes, manager approves, SoD, token scope |
| `tenant_isolation.rego` | `zoiko.tenant_isolation` | Tenant in JWT must match tenant on resource |

---

## Key Rules Covered in Phase 1

| Rule | Coverage |
|------|---------|
| ✅ Rule 3: RLS on all tenant tables | OIDC middleware enforces tenant binding |
| ✅ Rule 5: OPA fail-closed          | `OPAUnavailableError` → 503         |
| ✅ Rule 6: Separation of Duties     | `freight_dispute.rego` — SoD check  |
| ✅ Rule 9: Idempotency + Tenant headers | `KafkaMessage` headers enforced |

---

## Next: Phase 2 (Week 7–10)

| Service | What it does |
|---------|-------------|
| api-gateway | Routes requests, enforces OIDC + OPA on every call |
| ingestion-svc | JCS → hash → sign → DB tx → outbox (exact write pattern) |
| validation-svc | Contract rule engine, populates validation_results |
| canonical-truth | Deduplication, canonical_invoices + canonical_shipments |
| case-orchestration | State machine: OPENED → EVIDENCE_GATHERING → PENDING_APPROVAL |
