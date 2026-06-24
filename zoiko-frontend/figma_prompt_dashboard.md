# Figma Design Spec — Zoiko Dashboard (Command Center)

Written as a senior frontend developer's handoff brief, not a vibe description. Every
number below is pulled directly from the live component (`src/features/dashboard/Home.tsx`)
so the Figma file matches production pixel-for-pixel — this is "redraw what exists, then
extend it," not "imagine a dashboard."

---

## 1. Screen purpose & current data binding

This is the post-login landing page. Today it renders **one slice only** — invoice
overcharge recovery (SC-001). It pulls three live queries:
- `listCases()` — refetches every 5s
- `listTokens()` — refetches every 10s
- `getStats()` — refetches every 10s

Everything on screen is **derived client-side** from the `cases` array (no separate
aggregation endpoint) — carrier breakdown, monthly trend, funnel counts, and KPI totals
are all computed in-component from raw case rows. Keep this noted in the Figma file as an
annotation: design decisions about "what's a tile vs. a derived metric" should assume this
same pattern continues (each new slice contributes derived metrics into the same shapes,
not new bespoke widgets).

---

## 2. Page-level layout

- Outer container: vertical flex stack, **20px gap** between every major section (`gap: 20`).
- No max-width constraint at the page level — fills the content area inside the app shell/sidebar.
- Background: page background is the app shell's pale slate (not set inline here — inherits `slate-50`).
- Section order, top to bottom:
  1. Welcome banner (greeting + primary CTA)
  2. Action Required panel (conditional — hidden entirely if empty)
  3. 4-column KPI row
  4. 3-column analytics row (Carrier Scorecard / Monthly Recovery / Recovery Pipeline funnel)
  5. Recent Cases table (full width)
  6. Trust footer band (full width, dark)

---

## 3. Section 1 — Welcome banner

- Flex row, `justify-content: space-between`, `align-items: center`, wraps on narrow viewports (`flex-wrap: wrap`), `gap: 12px`.
- **Left**: greeting block.
  - H1: "Welcome back, {firstName}" — 20px / weight 800 / color `#1e293b` (slate-800), margin 0. First name only (split on space, take index 0).
  - Subline directly below, 2px margin-top: 13px / `#64748b` (slate-500) / role-conditional copy:
    - `analyst` → "Review flagged invoices and propose recoveries"
    - `manager` → "Approve pending recovery proposals"
    - `admin` → "Freight overcharge recovery overview"
- **Right**: primary CTA button.
  - "Submit Invoice" with a `FileText` icon (15×15px), icon-then-label, 7px gap.
  - Padding `9px 18px`, background `#2563eb` (blue-600), white text, no border, `border-radius: 8px`, font 13px/weight 700.
  - Shadow: `0 2px 8px rgba(37,99,235,0.3)` — this soft colored shadow is the button's signature, keep it on every primary CTA across the app, not just here.
  - Navigates to `/cases/new`.

**Multi-slice note**: this CTA is currently hardcoded to "Submit Invoice." When generalized, this needs to become a split-button or dropdown ("Submit New ▾" → Invoice / Claim / + future slices) rather than a single hardcoded action — flag this as a required component change, not just a visual one.

---

## 4. Section 2 — Action Required panel

Conditionally rendered — **entirely absent from the DOM** when there's nothing to act on (not just visually hidden). Design both states in Figma: populated and the "page without this section" layout (KPI row simply becomes the first element).

- Card: white, `1px solid #e2e8f0` border, `border-radius: 12px`, padding `16px 18px`, shadow `0 1px 4px rgba(0,0,0,0.04)` — this exact card recipe (border + radius + padding + shadow) is the **base card component** reused everywhere on this screen. Define it once as a Figma component (`Card/Base`) and instance it for every white box on the page.
- Header row inside: `AlertTriangle` icon (15×15, `#f59e0b` amber-500) + "Action Required" label (13px/weight 700/`#1e293b`), 7px gap, 14px margin-bottom.
- Body: vertical stack of **Action Rows**, 8px gap between rows.

### Action Row anatomy (component: `ActionCard`)
- Flex row, `space-between`, padding `12px 16px`, `border-radius: 10px`.
- Background and border are the **same accent color at different opacity**: background = `{color}0d` (≈5% alpha), border = `1px solid {color}30` (≈19% alpha). On hover, background deepens to `{color}18` (≈9% alpha). This alpha-layering technique (one hex + opacity suffix, not separate hover colors) is used throughout — replicate it as a Figma color style with opacity variants, not as separate flat colors.
- Left side: icon chip (34×34px, `border-radius: 8px`, background `{color}20`, icon 16×16 in `color`) + two-line text block (title 13px/weight 700/`#1e293b`, meta line 11px/`#64748b` showing `"{count} case(s) · {currency amount}"`).
- Right side: a pill-shaped action-label badge (12px/weight 700/`color`, background `{color}18`, padding `4px 10px`, `border-radius: 6px`) + `ChevronRight` (14×14, `color`).
- Whole row is a click target (cursor pointer), routes to a queue page.

Four possible rows, each role-gated and only shown if `count > 0`:
| Row | Icon | Accent hex | Routes to |
|---|---|---|---|
| Cases need your proposal | `FileText` | `#7c3aed` (violet) | `/analyst` |
| Cases awaiting your approval | `CheckCircle2` | `#d97706` (amber-600) | `/manager` |
| Approved cases ready to execute | `Zap` | `#2563eb` (blue) | `/execute` |
| Active governance tokens expiring | `Clock` | `#dc2626` (red-600) | `/execute` |

**Multi-slice note**: these four rows are currently invoice-case-only. Generalizing means each row's count/amount must aggregate across *all* governed entity types (invoices + claims + future slices), and a 5th+ row type may be needed per new slice's distinct action (e.g. SC-004's "supplier needs escalation" doesn't fit the amount-based copy pattern — needs a count-only variant of this component).

---

## 5. Section 3 — KPI row (4 cards)

- CSS grid, `grid-template-columns: repeat(4, 1fr)`, `gap: 14px`.

### KPI Card anatomy (component: `KpiCard`)
- Base card recipe (see §4) plus: `position: relative; overflow: hidden`.
- **Top accent bar**: absolutely positioned, `top/left/right: 0`, `height: 3px`, background = the card's accent color, rounded top corners only (`12px 12px 0 0`). This 3px top stripe is the KPI card's signature — every KPI card gets one, color-coded to its meaning.
- Header row inside (10px margin-bottom): label (11px/weight 700/`#94a3b8` slate-400/uppercase/`letter-spacing: 0.05em`) on the left, icon chip on the right (32×32px, `border-radius: 8px`, background `{accent}18`, icon 15×15 in accent color).
- Value: 22px / weight 800 / `#1e293b`, margin `0 0 4px`.
- Sub-line (optional): 11px/weight 600, color `#16a34a` (green) if trending up else `#64748b`, with a `TrendingUp`/`TrendingDown` icon (11×11) prefixed when `subUp` is defined.
- **Hover** (only when the card is clickable — has an `onClick`): shadow deepens to `0 4px 16px rgba(0,0,0,0.10)` and the card lifts `translateY(-1px)`, both on a `0.15s` transition. Cards without a click handler (e.g. "Overcharges Detected") never show this hover state — design both interactive and static KPI card variants.

### The 4 cards, exact content:
| # | Label | Value source | Sub-line | Icon | Accent | Clickable? |
|---|---|---|---|---|---|---|
| 1 | Invoices Submitted | `stats.total_cases` or case count | "{open count} in progress" | `FileText` | `#3b82f6` blue | → `/cases` |
| 2 | Overcharges Detected | sum of `diff` across all cases | "{N} carriers", trend-down styling | `TrendingDown` | `#ef4444` red | no |
| 3 | Amount Recovered | sum of `diff` for DISPATCHED/OUTCOME_RECORDED/CLOSED | "{N} cases closed", trend-up | `IndianRupee` | `#10b981` emerald | no |
| 4 | Recovery Rate | recovered/overcharge as % | "Above target" if ≥70% else "In progress" | `Award` | `#8b5cf6` violet | → `/analytics` |

**Multi-slice note**: card 1's label ("Invoices Submitted") and card 4's framing ("Recovery Rate") are invoice-specific nouns. Generalizing requires either (a) renaming to entity-agnostic copy ("Cases Submitted") with a breakdown-by-slice on hover/expand, or (b) this row becoming horizontally scrollable / slice-filterable rather than a fixed 4-tile grid — flag as a real design decision, not a copy change.

---

## 6. Section 4 — Analytics row (3 columns)

- CSS grid, `grid-template-columns: 1fr 1.2fr 0.9fr` (note: deliberately *unequal* — the middle chart column is widest, the right funnel column is narrowest), `gap: 14px`.

### 6a. Carrier Scorecard (left column)
- Base card. Header: `Truck` icon (14×14, `#64748b`) + "Carrier Scorecard" (13px/weight 700) on the left; "All →" link (11px/weight 600/`#2563eb`) on the right, routes to `/cases`.
- Body: top 5 carriers by overcharge amount, each row:
  - Line 1: colored dot (8×8px circle, carrier's assigned color) + carrier name (12px/weight 600/`#334155`) on the left; overcharge amount (11px/weight 700/`#ef4444`) + percentage (10px/`#94a3b8`) on the right.
  - Line 2: a horizontal progress bar — track `#f1f5f9`, 5px tall, fully rounded, fill is the carrier's color at `width: {pct}%`, animated `transition: width 0.8s ease`.
  - Carrier colors cycle through a fixed 6-color palette: `#3b82f6, #8b5cf6, #f59e0b, #10b981, #ef4444, #06b6d4` (assigned by sort order, not by identity — i.e. colors are NOT stable per carrier across renders if the sort order changes — note this as a known limitation in the spec, worth fixing before this becomes multi-slice with more "counterparty" types like suppliers).
- Empty state: centered, `Truck` icon at 28×28 in `#cbd5e1`, "No carrier data yet" in 12px `#94a3b8`, vertically centered in a 140px-tall box.

### 6b. Monthly Recovery (middle column, widest)
- Base card. Header: `BarChart3` icon + "Monthly Recovery" label, same pattern as 6a.
- Recharts grouped `BarChart`, 160px height, last 6 months only.
  - Grid: dashed horizontal lines only (`strokeDasharray: 3 3`, color `#f1f5f9`, no vertical lines).
  - Axes: no axis lines, no tick lines, 10px tick labels in `#94a3b8`. Y-axis formats as `$Xk` (divides by 1000).
  - Two bars per month, both rounded on top only (`radius: [4,4,0,0]`): "billed" in `#fee2e2` (red-100, i.e. the *overcharge* total — note the misleading internal name `billed`, it's actually the overcharge/diff sum, not the invoice total — flag this naming inconsistency to engineering, don't replicate the confusing name in new components), "recovered" in `#10b981` (emerald-500).
  - Tooltip: 11px font, `border-radius: 8px`, `1px solid #e2e8f0` border.
  - Custom legend below the chart (not Recharts' built-in legend): two swatches, 10×10px rounded squares with a 1.5px border in a slightly darker shade of the same color, 10px label text, 16px gap between legend items, 8px margin-top from chart.
- Empty state: plain centered text "Submit invoices to see trend," 150px tall box, `#94a3b8`, 12px.

### 6c. Recovery Pipeline funnel (right column, narrowest)
- Base card. Header: `TrendingUp` icon + "Recovery Pipeline" label.
- 4-stage funnel, each stage rendered identically to the carrier scorecard's bar pattern (label/value row + progress bar) but:
  - Bar height is 6px (not 5px).
  - Bar width = `(stage_value / first_stage_value) × 100%` — i.e. always relative to the top of the funnel, not relative to 100 in absolute terms.
  - Each stage's bar opacity steps down by 0.1 per stage (`opacity: 1 - i*0.1`) — stage 1 fully opaque, stage 4 at 0.7 opacity, even though they're different colors. This is a deliberate "fading down the funnel" visual cue — preserve it.
  - Stages: Submitted (blue `#3b82f6`) → AI Analyzed (violet `#8b5cf6`) → Awaiting Approval (amber `#f59e0b`) → Recovered (emerald `#10b981`).
- Below the funnel, separated by a `1px solid #f1f5f9` top border with 14px padding-top: a small callout — "PENDING APPROVAL" label (10px/weight 700/uppercase/`#94a3b8`/`letter-spacing 0.05em`), then the pending-approval dollar amount (16px/weight 800/`#d97706` amber-600), then case count (10px/`#94a3b8`).

**Multi-slice note**: this entire row's three widgets are conceptually "breakdown by counterparty / trend over time / stage funnel" — that pattern generalizes cleanly (supplier scorecard instead of carrier scorecard for SC-004, etc.), but each new slice needs its own instance of this row, not a forced merge into one. Design this as **per-slice-tab content beneath a slice selector**, not as one giant unified chart trying to plot incompatible units (dollars vs. scores vs. days-late) on the same axis.

---

## 7. Section 5 — Recent Cases table

- Base card but with `overflow: hidden` and **no padding on the card itself** (padding lives on the header and rows individually) — this is a different card variant from the others (`Card/Table`, not `Card/Base`).
- Header bar: `padding: 14px 18px`, `border-bottom: 1px solid #f1f5f9`, "Recent Cases" label (13px/weight 700) left, "View all →" link right (`ArrowRight` 12×12 icon).
- Table: `border-collapse: collapse`, full width.
  - Header row: background `#f8fafc` (slate-50), cells `padding: 9px 16px`, 10px/weight 700/`#94a3b8`/uppercase/letter-spacing 0.05em, bottom border `1px solid #f1f5f9`.
  - Columns: Case ID · Carrier · Invoice Amount · Overcharge · AI Confidence · Status · Date.
  - Body rows: `padding: 11px 16px` per cell, `cursor: pointer` (navigates to case detail), hover background `#f8fafc`, bottom border `1px solid #f8fafc` (lighter than the header's border) except on the last row.
  - **Case ID** cell: monospace font, 11px, `#2563eb` blue, truncated to first 8 characters + ellipsis.
  - **Overcharge** cell: 12px/weight 700, color `#dc2626` if > 0 else `#94a3b8` em-dash.
  - **AI Confidence** cell: inline mini progress bar (40×5px, rounded, track `#f1f5f9`) + percentage label (11px/weight 700/`#475569`). Bar fill color is confidence-banded: `#10b981` if ≥90%, `#f59e0b` if ≥70%, `#ef4444` below — **this 3-tier confidence color convention (emerald/amber/red at 90%/70% thresholds) should be a reusable Figma color token**, it'll recur on every slice's detail page.
  - **Status** cell: the `StateBadge` pill — 10px/weight 700, `padding: 2px 8px`, fully rounded, `whitespace: nowrap`. Background/text pairs are customer-friendly relabels of the raw FSM state (e.g. raw `APPROVAL_PENDING` displays as "Awaiting Approval" in amber `#fef3c7`/`#d97706`). Full mapping table is in the component — replicate exactly, don't invent new labels.
  - **Date** cell: 11px/`#94a3b8`, formatted `en-IN` locale, `Asia/Kolkata` timezone, "day month" only (no year, no time).
- Loading state: 5 skeleton rows, pulsing gray bars (`animate-pulse`, background `#f1f5f9`, `border-radius: 999px`) at varying widths mimicking real column content.
- Empty state: centered, 48px padding, `FileText` icon 32×32 `#cbd5e1`, "No cases yet" (14px `#64748b`), helper line below (12px `#94a3b8`), then a "Submit Invoice" button identical in style to the welcome banner's CTA but smaller (`8px 18px` padding, 12px font).

**Multi-slice note**: column headers ("Carrier," "Invoice Amount") are invoice-specific. A multi-slice version needs either per-slice column sets or a normalized column set (Entity / Counterparty / Amount-or-Score / Confidence / Status / Date) that every slice maps into — design the normalized version, since a separate table per slice defeats the point of a unified Recent Activity feed.

---

## 8. Section 6 — Trust footer band

- Full-width dark band: `background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%)`, `border-radius: 12px`, `padding: 16px 24px`.
- Flex row, `flex-wrap: wrap`, `justify-content: space-between`, `align-items: center`, `gap: 16px`.
- 4 fixed trust badges, each: icon chip (32×32px, `border-radius: 8px`, `background: rgba(255,255,255,0.07)`, icon 15×15 in `#60a5fa` light-blue) + two-line text (title 11px/weight 700/white, subtitle 10px/`#64748b`).
  1. `ShieldCheck` — "Cryptographically Signed" / "Ed25519 + SHA-256 on every record"
  2. `CheckCircle2` — "Two-Person Approval" / "Analyst proposes · Manager approves"
  3. `Award` — "Immutable Audit Trail" / "WORM-locked, tamper-proof"
  4. `Users` — "Role-Based Access" / "Analyst · Manager · Admin"

This band is **static marketing/trust copy**, not data-driven — same on every slice, every role. Keep it exactly as-is when generalizing; it's the one section that should NOT change per slice.

---

## 9. States to design explicitly (don't skip these in Figma)

1. **Fully loaded, populated** (the default — everything above).
2. **Loading** — KPI cards still render with real-looking zero values (no loading state defined for KPIs in code today — flag this as a gap, design a skeleton variant), Recent Cases shows the 5-row pulsing skeleton.
3. **Empty / new tenant** — Action Required panel absent, all 4 KPIs show "—" / "No data yet", carrier scorecard and trend both show their empty-state illustrations, Recent Cases shows its full empty state with CTA.
4. **Role variants** — analyst sees only the "needs proposal" action row; manager sees approval/execute/token rows; admin sees all four. Design these as three distinct Action Required panel states, not one screen with notes.

---

## 10. Multi-slice command center — the actual extension ask

Today this page hardcodes invoice vocabulary everywhere. To become the dashboard for all 7
slices without a rebuild per slice, design:

1. **A slice selector** at the top of the page (tabs or a segmented control, directly under
   or replacing the welcome banner's subline) — "All · Invoices · Claims · Shipments ·
   Suppliers · Accessorials · Procurement · Inventory" — switching it re-filters every
   section below using the same layout, swapping only labels/units/icons per the mapping
   tables in each section above.
2. **KPI row stays 4 tiles**, but tile 1's noun and tile 4's framing become slice-aware
   (driven by a per-slice config object: `{ entityNounPlural, primaryMetricLabel,
   primaryMetricIsScore: boolean }`), not hardcoded strings.
3. **Analytics row's left widget** (Carrier Scorecard) generalizes to "Counterparty
   Scorecard" — same bar-list pattern, but the counterparty type changes (carrier / supplier
   / vendor) per slice.
4. **Recent Cases table** adopts the normalized column set from §7's note, with an added
   "Slice" badge column when the "All" selector is active, so mixed-entity rows are still
   scannable.
5. The **Action Required panel** and **Trust footer** patterns are already slice-agnostic in
   structure — just need their data sources widened (see notes in §4 and §6).

Build this as **one Figma page per slice selector state** (8 total: "All" + 7 slices), all
instancing the same component library, so a reviewer can flip between them and see exactly
what's shared vs. what's swapped.
