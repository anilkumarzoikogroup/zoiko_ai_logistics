# Zoiko AI Logistics

**AI-powered freight dispute resolution platform.** Detects overcharges, SLA breaches, carrier claim disputes, scorecard breaches, and accessorial charge excess — then recovers money through a cryptographically auditable pipeline where every decision is signed, Merkle-hashed, and locked into an Action Certification Record (ACR).

---

## What It Does

| Slice | Scenario | Outcome |
|-------|----------|---------|
| **SC-001** | BlueDart bills ₹12,500, contract allows ₹8,000 | ₹4,500 overcharge caught, two humans approve, ACR locked |
| **SC-002** | Carrier claim filed for damaged goods | AI scores claim, analyst proposes settlement, manager approves, credit issued |
| **SC-003** | Carrier commits 14:00 delivery, arrives 20:00 | 6-hour SLA breach = ₹3,000 penalty, two humans approve, SLA credit issued |
| **SC-004** | Carrier composite score falls below contracted threshold | AI detects breach (0.9640 confidence), analyst flags, manager approves, NOTIFY_FLAG actioned |
| **SC-005** | Carrier bills ₹3,200 accessorial charges, tariff caps ₹2,000 | ₹1,200 excess (0.9720 confidence), analyst proposes partial credit, manager approves |

---

## Quick Start (Local)

### Prerequisites

| Tool | Minimum | Notes |
|------|---------|-------|
| Python | 3.10+ | [python.org](https://python.org) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| PostgreSQL | 14+ | Must be running locally |
| Redis | 6+ | Optional — token CONSUMED lock (falls back to DB) |

### 1 — Configure environment

```bat
copy .env.example .env
```

Open `.env` and set at minimum:

```
DB_URL=postgresql://postgres:YOUR_PASSWORD@localhost/zoiko
ZOIKO_DEV_SECRET=any-32-char-random-string
ZOIKO_DEV_MODE=true
ZOIKO_ADMIN_EMAIL=admin@example.com
ZOIKO_ADMIN_PASSWORD=YourStrongPassword123
ZOIKO_ADMIN_NAME=Platform Admin
ZOIKO_COMPANY_NAME=Your Company
```

### 2 — One-time setup

Double-click **`setup.bat`** (or run in cmd):

```bat
setup.bat
```

This will:
- Create `.venv` Python virtual environment
- Install all Python packages from `requirements.txt`
- Run all 31 Alembic database migrations (creates every table)
- Seed the admin user
- Install frontend npm packages
- Write `zoiko-frontend/frontend/.env.local` with all proxy variables

### 3 — Launch everything

Double-click **`launch.bat`** (or run in cmd):

```bat
launch.bat
```

This starts **13 processes** in one shot:

| Process | Port | Slice |
|---------|------|-------|
| SC-001 Gateway | 8000 | Freight invoice overcharge |
| SC-001 Execution | 8001 | |
| SC-001 Governance | 8002 | |
| SC-002 Gateway | 8010 | Carrier claim |
| SC-002 Execution | 8011 | |
| SC-002 Governance | 8012 | |
| SC-003 Gateway | 8020 | Shipment exception / SLA breach |
| SC-003 Execution | 8021 | |
| SC-004 Gateway | 8030 | Supplier scorecard breach |
| SC-004 Execution | 8031 | |
| SC-005 Gateway | 8040 | Accessorial charge dispute |
| SC-005 Execution | 8041 | |
| Frontend (Vite) | 5173 | React UI |

Browser opens automatically at **http://localhost:5173/login**

---

## Architecture

### 5 Vertical Slices

Each slice is fully self-contained under `backend/slices/sc-00X.../spine/` and implements the full **12-domain platform spine**:

```
Domain  1 — Identity (JWT/OIDC, tenant resolution)
Domain  2 — Source Ingestion (hash-before-store source_records)
Domain  3 — Validation (structural + semantic + policy checks)
Domain  4 — Canonical Truth (authoritative canonical entity + lineage)
Domain  5 — Commercial Reference (contract rates, tariff schedules)
Domain  6 — Case Orchestration (FSM: NEW → EVIDENCE_PENDING → … → CLOSED)
Domain  7 — Evidence (growing append-only Merkle bundle)
Domain  8 — Reasoning (deterministic confidence rules → finding)
Domain  9 — Governance + Token (SoD enforce, 15-min governance token)
Domain 10 — Execution Gateway (8-gate check before money moves)
Domain 11 — Reconciliation (settlement match, variance resolution)
Domain 12 — ACR + Transparency Log (Merkle ACR, WORM-locked, offline verifiable)
```

### Service layout (per slice)

```
spine/
├── gateway/
│   └── services/
│       ├── api_gateway/         ← FastAPI routes + auth middleware
│       ├── ingestion_svc/       ← Domain 2
│       ├── validation_svc/      ← Domain 3
│       ├── canonical_truth/     ← Domain 4
│       ├── case_orchestration/  ← Domain 6
│       ├── evidence_svc/        ← Domain 7
│       ├── reasoning_svc/       ← Domain 8
│       ├── governance_svc/      ← Domain 9 (SoD + task lifecycle)
│       └── token_svc/           ← Domain 9 (governance token mint)
└── execution/
    └── services/
        ├── api_gateway/         ← FastAPI routes
        ├── execution_gateway/   ← Domain 10 (8-gate check)
        ├── reconciliation_svc/  ← Domain 11
        ├── audit_acr_svc/       ← Domain 12 (ACR)
        └── transparency_log_svc/← Domain 12 (Merkle log)
```

### Confidence scores (deterministic — never change)

| Slice | Confidence | Formula |
|-------|-----------|---------|
| SC-001 | **0.9600** | 1.00×0.50 + 0.92×0.50 |
| SC-003 | **0.9520** | 1.00×0.60 + 0.88×0.40 |
| SC-004 | **0.9640** | 1.00×0.70 + 0.88×0.30 |
| SC-005 | **0.9720** | 1.00×0.65 + 0.92×0.35 |

### Database

Single shared PostgreSQL database `zoiko`. 31 Alembic migration versions.

```
DB_URL=postgresql://postgres:1234@localhost/zoiko
```

Apply all migrations:
```bat
.venv\Scripts\python -m alembic -c alembic.ini upgrade head
```

---

## Frontend

React 18 + TypeScript + Vite + Tailwind CSS. Dark mode everywhere.

```
zoiko-frontend/frontend/
├── src/
│   ├── api/client.ts          ← All Axios instances (one per slice)
│   ├── api/zoiko.ts           ← Service layer (USE_MOCK gate)
│   ├── features/cases/        ← SC-001 freight invoice cases
│   ├── features/claims/       ← SC-002 carrier claims
│   ├── features/exceptions/   ← SC-003 shipment exceptions
│   ├── features/scorecard/    ← SC-004 supplier scorecard
│   ├── features/disputes/     ← SC-005 accessorial disputes
│   ├── features/governance/   ← Analyst review + Manager approval
│   ├── features/acr/          ← Crypto audit / ACR viewer
│   ├── features/recovery/     ← Phase 6 recovery pipeline
│   └── features/compliance/   ← C07 data governance
├── vite.config.ts             ← Proxy config (all 13 backend ports)
└── .env.local                 ← Written by setup.bat
```

Vite proxy map:

| Frontend prefix | Backend port | Slice |
|-----------------|-------------|-------|
| `/api` | 8000 | SC-001 gateway |
| `/api4` | 8001 | SC-001 execution |
| `/api3` | 8002 | SC-001 governance |
| `/claimapi` | 8010 | SC-002 gateway |
| `/claimapi4` | 8011 | SC-002 execution |
| `/claimapi3` | 8012 | SC-002 governance |
| `/excapi` | 8020 | SC-003 gateway |
| `/excapi4` | 8021 | SC-003 execution |
| `/scoreapi` | 8030 | SC-004 gateway |
| `/scoreapi4` | 8031 | SC-004 execution |
| `/accapi` | 8040 | SC-005 gateway |
| `/accapi4` | 8041 | SC-005 execution |

---

## API Reference

### SC-001 Gateway (port 8000) — Freight Invoice Overcharge

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/cases/submit` | Full pipeline: ingest → validate → canonical → case → evidence → finding |
| GET | `/v1/cases` | All cases for tenant |
| GET | `/v1/cases/{id}` | Case detail with carrier/amount/confidence |
| POST | `/v1/cases/{id}/propose` | Analyst proposes recovery |
| POST | `/v1/cases/{id}/decide` | Manager approves/rejects (SoD enforced) |
| POST | `/v1/execute` | 8-gate execution → issues credit memo |
| GET | `/v1/cases/{id}/acr` | Action Certification Record |
| GET | `/health` | Health check |

### SC-003 Gateway (port 8020) — Shipment Exception / SLA Breach

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/shipment-exceptions/submit` | Full pipeline |
| GET | `/v1/shipment-exceptions` | List with pagination |
| POST | `/v1/shipment-exceptions/{id}/propose` | Analyst proposes SLA credit |
| POST | `/v1/shipment-exceptions/{id}/decide` | Manager approves |

### SC-004 Gateway (port 8030) — Supplier Scorecard

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/scorecards/compute` | Compute + store scorecard for carrier+period |
| GET | `/v1/scorecards` | List all scorecards |
| GET | `/v1/scorecards/{id}` | Detail with sub-scores + breach case |
| POST | `/v1/scorecards/{id}/propose` | Analyst proposes NOTIFY_FLAG |
| POST | `/v1/scorecards/{id}/decide` | Manager approves |

### SC-005 Gateway (port 8040) — Accessorial Charge Dispute

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/accessorial-disputes/submit` | Full pipeline |
| GET | `/v1/accessorial-disputes` | List with pagination |
| POST | `/v1/accessorial-disputes/{id}/propose` | Analyst proposes partial credit |
| POST | `/v1/accessorial-disputes/{id}/decide` | Manager approves |

All requests require headers:
```
Authorization: Bearer <JWT>
X-Tenant-ID: <tenant-uuid>
Idempotency-Key: <unique-uuid>   (mutations only)
```

In dev mode (`ZOIKO_DEV_MODE=true`), a dev JWT is auto-accepted and tenant resolved from `X-Tenant-ID`.

---

## Security Rules

1. **Never commit `.env`** — contains real credentials. Already in `.gitignore`.
2. **Never `git add -A` or `git add .`** — always add specific files by name.
3. **Never log environment variables** anywhere in code.
4. **SoD enforced** — the analyst who proposes cannot be the manager who approves.
5. **8-gate execution** — all gates must pass before money moves.
6. **WORM locked** — ACR `is_locked=true` is irreversible.
7. **Append-only tables** — `lineage_records`, `case_events`, `evidence_items`, `audit_worm_index`, `shipment_events` — never UPDATE or DELETE.

---

## Deployment (Render)

Deployed as 4 Docker containers on Render (free tier):

| Service | What it runs |
|---------|-------------|
| `zoiko-api` | SC-001 gateway on `$PORT` |
| `zoiko-execution` | SC-001 execution on `$PORT` |
| `zoiko-governance` | SC-001 governance on `$PORT` |
| `zoiko-opa` | OPA policy engine |

Deploy triggers automatically when CI passes on `main` via `.github/workflows/deploy-render.yml`.

**Required GitHub Secrets** (in zoikoai/ZoikoAI repo settings):
- `RENDER_DEPLOY_HOOK_URL` — zoiko-api hook
- `RENDER_DEPLOY_HOOK_URL_EXECUTION` — zoiko-execution hook
- `RENDER_DEPLOY_HOOK_URL_GOVERNANCE` — zoiko-governance hook
- `RENDER_DEPLOY_HOOK_URL_OPA` — zoiko-opa hook

---

## Running Tests

```bat
REM SC-001 core + platform
cd backend\slices\sc-001-freight-invoice-overcharge\spine
..\..\..\..\.venv\Scripts\python -m pytest -q --tb=short

REM SC-002 carrier claim
cd backend\slices\sc-002-carrier-claim\spine\gateway
..\..\..\..\..\..\.venv\Scripts\python -m pytest -q --tb=short
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ERROR: .env not found` | Run `copy .env.example .env` and fill in values |
| `Cannot connect to database` | Start PostgreSQL, check `DB_URL` in `.env` |
| Frontend shows mock data | Check `VITE_USE_MOCK=false` in `zoiko-frontend/frontend/.env.local` |
| Port already in use | `launch.bat` auto-kills stale processes — if it fails, restart PC |
| SC-003 not loading | Check gateway on port 8020: `curl http://localhost:8020/health` |
| SC-004 not loading | Check gateway on port 8030: `curl http://localhost:8030/health` |
| SC-005 not loading | Check gateway on port 8040: `curl http://localhost:8040/health` |
| Backend not picking up changes | Kill Python process, restart uvicorn (or re-run `launch.bat`) |
