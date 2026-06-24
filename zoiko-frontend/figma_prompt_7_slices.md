# Figma Design Prompt — Zoiko L&S Chain, All 7 Slices

## Context for the design tool

Zoiko AI's Logistics & Supply Chain stack runs one platform spine for every use case:
**Source → Canonical → Case → Evidence → Proposal → Governance → Execution → Reconciliation → ACR.**

Two slices (SC-001 Freight Invoice Overcharge, SC-002 Carrier Claim) are already built and live.
Design the remaining five (SC-003–SC-007) as **visual extensions of the same system**, not new
products — same components, same page shapes, same color logic. A user switching between slices
should feel like they're in one app, not seven.

This is exploratory UI design only — no slice past SC-002 has a backend yet, so design with
placeholder/mock data, not real API shapes.

## Existing design system (match exactly — do not introduce a new palette)

- **Theme**: light. White cards (`#ffffff`) on a pale slate background (`slate-50`), `slate-200` borders.
- **Typography**: bold dark headers (`zoiko-navy` for h1/h2), `slate-800` body text, `slate-400`/`slate-500` for muted/meta text. Small uppercase labels at 10–11px tracked wide.
- **Color logic (semantic, not decorative)**:
  - **Blue** (`blue-600`) = primary action / AI-proposed / informational
  - **Emerald** (`emerald-600`) = approved / accepted / success
  - **Amber** (`amber-100/600/700`) = pending / partial / needs attention
  - **Red** (`red-200/600`) = rejected / destructive
  - **Indigo** (`indigo-50/600/700`) = negotiation / counter-party interaction (distinct from internal governance actions)
- **Components**: rounded-xl cards with subtle shadow, pill-shaped status badges (`rounded-full`, bold 10–11px text on a tinted background), bordered-left-4 KPI tiles, lucide-react icon set, standard form inputs with a floating `Label`.
- **Layout pattern per entity type**: every slice gets the same three screens — **List/Queue**, **Detail (pipeline view)**, **New Submission form**. Do not invent a fourth shape per slice.

## Shared page templates (build once, reuse across all 7 slices)

### 1. List / Queue view
- Header: entity name + count + "New [Entity]" button (top-right, blue).
- Filter bar: state/status dropdown, search, date range.
- Card-per-row or table — show: ID, key counterparty (carrier/supplier/vendor), amount or score, AI confidence, current FSM state as a colored pill, last updated.
- Empty state and loading skeleton.

### 2. Detail page — the pipeline view
This is the most important shared pattern. Every slice's detail page shows the **same 9-stage
horizontal pipeline** (Source → Canonical → Case → Evidence → Proposal → Governance → Execution →
Reconciliation → ACR) as a stepper at the top, with the current stage highlighted and completed
stages checked. Below the stepper:
- KPI tile row (4 tiles, left-border-4 color-coded) — content varies per slice (see specs below).
- **Two visually distinct zones, clearly separated**:
  - **Agent Authority Zone** (blue-tinted panel, dashed border, labeled "AI Proposed") — shows the finding/confidence/rule trace and a draft proposal. Read-only narrative, no destructive actions.
  - **Governed Execution Zone** (solid bordered panel) — propose / approve (SoD-enforced, shows "different user must approve") / execute / reconciliation outcome / ACR download. This is where state actually changes.
- Audit trail / event timeline at the bottom (append-only list, timestamps, actor).

### 3. New Submission form
- Single-column card, max-width ~32rem, matches the existing `NewClaim.tsx` form shape: grouped fields, a contextual info callout explaining what governed pipeline this kicks off, primary submit button with loading state.

## Per-slice screen specs

### SC-003 — Shipment Exception / SLA Penalty
- **Entity**: shipment event (time-series, not a single document).
- List view distinguishing feature: a small inline timeline sparkline per row showing the sequence of shipment events (pickup → in-transit → delayed → delivered) before the exception was flagged.
- Detail page KPI tiles: **Committed ETA**, **Actual Delivery**, **SLA Breach Duration**, **AI Confidence**.
- Proposal zone shows "SLA Credit" as the requested execution action (not a credit memo).
- Reconciliation panel: "Commitment Match" — compares promised delivery window vs. actual, shown as a two-bar comparison chart.

### SC-004 — Supplier Performance Scorecard
- **Entity**: supplier (aggregated over time, not a single transaction).
- This slice is **score-based, not amount-based** — replace every dollar-amount KPI tile pattern with a **score gauge** (0–100, color-graded red→amber→emerald).
- List view: supplier name, overall score, trend arrow (up/down vs. last period), category breakdown chips (fulfillment / quality / timing / reliability).
- Detail page: radar/spider chart comparing the 4–5 scoring dimensions, plus a historical trend line.
- No "Execute" action in the traditional sense — the governed action here is "Notify / Flag" (e.g., escalate to procurement), styled in amber, not the green/credit-memo pattern of SC-001/002.

### SC-005 — Accessorial Charge Dispute
- **Entity**: accessorial charge line, referenced against a tariff.
- Detail page must show a **side-by-side tariff comparison**: charged amount vs. tariff-permitted amount, with the specific tariff clause cited inline (tariff-by-reference — show the tariff ID/version as a clickable reference chip, not freeform text).
- Reconciliation default outcome is **partial acceptance** — design the reconciliation panel to default to a 3-way split bar (accepted / disputed / written-off) rather than the binary accept/reject pattern used in SC-001/002.

### SC-006 — Procurement Anomaly Detection
- **Entity**: purchase order, cross-validated against ASN / receiving / invoice.
- List view: PO number, supplier, anomaly type badge (spend-variance / PO-mismatch / non-compliant-charge), severity.
- Detail page's standout element: a **4-column cross-record comparison table** (PO vs ASN vs Receiving vs Invoice) with mismatched cells highlighted in amber/red — this is the core visual of the slice, more important than the pipeline stepper for this view.
- Proposal zone explains *which* cross-record check failed and why, citing the specific fields that disagree.

### SC-007 — Inventory Movement Exception
- **Entity**: inventory movement event, multi-source (warehouse system + PO + ASN + invoice).
- List view: SKU/location, movement type (receipt/transfer/adjustment/shrinkage), variance qty, source systems involved (small icon row showing which systems contributed data).
- Detail page: a movement ledger view (running balance table: expected qty → each movement → ending qty, with the exception row highlighted) instead of a single-amount KPI tile.
- Reconciliation panel labeled "Operational-System Reconciliation" — show it matching the AI's expected count against the warehouse system's actual count.

## Non-goals (do not design these yet)

- Carrier portal, supplier portal, or any external-party-facing screens — Zoiko's UI is internal-operator-only.
- Full bulk-import UI beyond what SC-001/002 already have.
- Dashboards aggregating across all 7 slices — out of scope until the Build Map's "Build Now" list includes it.
- Any screen implying ERP/GL posting or production carrier integration UI.

## Deliverable

For each of SC-003 through SC-007: one List view, one Detail/pipeline view, one New Submission
form — using the shared templates above with only the per-slice specifics swapped in. Sharable
component set (stepper, KPI tile, status pill, zone panel) should be built once as a Figma
component library, not redrawn per slice.
