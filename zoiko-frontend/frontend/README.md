# Zoiko Frontend

React + TypeScript + Vite + Tailwind + shadcn/ui frontend for Zoiko AI Logistics.

## Quick start

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:5173`.

By default it runs in **mock mode** — all data comes from `src/mocks/fixtures.ts`, no backend needed. You can navigate every page and see SC-001 data.

## Connecting to your real backend

Create a `.env.local` in this folder:

```
VITE_USE_MOCK=false
VITE_API_BASE=http://localhost:8000
VITE_DEV_JWT=eyJ...your-jwt...
VITE_DEV_TENANT=amazon-india
```

Or set `zoiko_jwt` and `zoiko_tenant` in localStorage from the browser console.

The Vite dev server also proxies `/api` → `http://localhost:8000` (configurable in `vite.config.ts`), so requests like `GET /api/cases` go to your Phase 2/3 gateway.

## Project structure

```
frontend/
├── src/
│   ├── api/                  ← Axios client + service layer
│   │   ├── client.ts         ← Auth/tenant/idempotency interceptors
│   │   └── zoiko.ts          ← Service methods with mock fallback
│   ├── components/
│   │   ├── ui/               ← shadcn primitives (Button, Card, Table, etc.)
│   │   └── shared/           ← App-specific shared components
│   ├── layouts/AppLayout.tsx ← Sidebar + main shell
│   ├── mocks/fixtures.ts     ← SC-001 mock data
│   ├── pages/                ← 20 pages, one per dashboard view
│   ├── types/index.ts        ← TypeScript types matching DB schema
│   ├── utils/cn.ts           ← Formatters, idempotency-key generator
│   ├── App.tsx               ← Routes
│   └── main.tsx              ← React entry
├── index.html
├── package.json
├── tailwind.config.js
├── tsconfig.json
└── vite.config.ts
```

## Pages — what to look at

| Page | URL | What it shows |
|------|-----|---------------|
| Home | `/` | Dashboard with SC-001 spotlight |
| Cases | `/cases` | Filterable list of all cases |
| New case | `/cases/new` | Submit invoice form |
| Case detail | `/cases/:id` | Complete case view with all artifacts |
| Analyst review | `/analyst` | Queue sorted by confidence |
| Manager approval | `/manager` | SoD-enforced approval |
| Execute recovery | `/execute` | 8-gate execution preview |
| Crypto & audit | `/crypto` | Live JCS + SHA-256 demo |
| Database | `/database` | All 26 tables with row counts |
| KMS Keys | `/kms` | Three-tier key hierarchy |
| OIDC Identity | `/oidc` | JWT decode + verification |
| OPA Policies | `/opa` | Rego policy with sample evaluations |
| Kafka Events | `/kafka` | 17 topics + SC-001 event stream |
| Ingestion | `/ingestion` | 5-step write pattern |
| Validation | `/validation` | Contract comparison |
| Canonical | `/canonical` | Authoritative invoice row |
| Case flow | `/case-flow` | FSM diagram |
| Evidence | `/evidence` | Merkle bundle |
| Reasoning | `/reasoning` | 0.96 confidence trace |
| Governance | `/governance` | SoD-enforced decisions |
| Token | `/token` | Signed governance tokens |

## Key conventions

- **Auth headers added automatically** by `src/api/client.ts` — every request gets `Authorization`, `X-Tenant-ID`, and on mutations a fresh `Idempotency-Key`.
- **TanStack Query** for server state — caching, refetching, loading states handled automatically.
- **Tailwind + shadcn/ui** for styling — no design system to learn, just use `<Card>`, `<Button>`, `<Badge>`, etc.
- **TypeScript everywhere** — DB schema types in `src/types/index.ts` mirror your PostgreSQL tables.

## Build for production

```bash
npm run build
```

Output is in `dist/`. Serve with any static host.

## Where this fits in your monorepo

Drop this entire `frontend/` folder into your `zoiko-logistics/` root, alongside the existing `phase-0/`, `phase-1/`, `phase-2/`, `phase-3/` folders. It is fully self-contained — its own `package.json`, its own `node_modules`, its own build.
