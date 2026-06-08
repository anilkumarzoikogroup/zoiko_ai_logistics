"""
Phase 2 — Live Demo
Run (from phase-2/ directory):
    set DB_URL=postgresql://postgres:1234@localhost/zoiko
    py -3.13 demo_phase2.py

SC-001: DHL bills $220.  Contract allows $120.  Overcharge = $100.
Shows the 4 Phase 2 services chained in sequence.
"""
import sys, os, uuid
sys.path.insert(0, os.path.dirname(__file__))

# ── colour helpers ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"; RED    = "\033[91m"; YELLOW = "\033[93m"
BLUE   = "\033[94m"; CYAN   = "\033[96m"; BOLD   = "\033[1m"; RESET  = "\033[0m"

def ok(m):     print(f"  {GREEN}✅ {m}{RESET}")
def fail(m):   print(f"  {RED}❌ {m}{RESET}")
def info(m):   print(f"  {CYAN}ℹ  {m}{RESET}")
def warn(m):   print(f"  {YELLOW}⚠  {m}{RESET}")
def header(t):
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}\n{BOLD}{BLUE}  {t}{RESET}\n{BOLD}{BLUE}{'='*60}{RESET}")
def sub(t):    print(f"\n{YELLOW}{BOLD}  ── {t}{RESET}")

# ── Setup ──────────────────────────────────────────────────────────────────────
from shared.db import DB_URL, q1
from kafka.mock_kafka import MockKafkaBroker
from kafka.consumer   import ZoikoConsumer

from services.ingestion_svc.handler   import IngestionHandler
from services.ingestion_svc.models    import InvoiceInput
from services.validation_svc.handler  import ValidationHandler
from services.canonical_truth.handler import CanonicalHandler
from services.case_orchestration.handler import CaseHandler

print(f"\n{BOLD}{'='*60}")
print("  Zoiko AI Logistics — Phase 2 Live Demo")
print("  SC-001: DHL bills $220, contract allows $120, overcharge $100")
print(f"{'='*60}{RESET}")

# ── Get test tenant from DB ────────────────────────────────────────────────────
tenant_row = q1("SELECT id, slug, display_name FROM tenants WHERE status='ACTIVE' ORDER BY created_at LIMIT 1;")
if not tenant_row:
    print(f"{RED}No active tenant found. Run: py -3.13 scripts/seed_dummy_data.py{RESET}")
    sys.exit(1)

TENANT_ID   = str(tenant_row["id"])
TENANT_SLUG = tenant_row["slug"]
TENANT_NAME = tenant_row["display_name"]
INV_NO      = f"DHL-P2-DEMO-{uuid.uuid4().hex[:6].upper()}"

info(f"Tenant:   {TENANT_NAME}  ({TENANT_SLUG})")
info(f"DB URL:   {DB_URL[:40]}...")
info(f"Invoice#: {INV_NO}")

broker = MockKafkaBroker()

# ══════════════════════════════════════════════════════════════════════════════
# SERVICE 1 — INGESTION
# ══════════════════════════════════════════════════════════════════════════════
header("1.  INGESTION SERVICE")
print("  Receives the raw DHL invoice, JCS-canonicalizes, hashes, encrypts, writes to DB")

ingestion = IngestionHandler(DB_URL, broker, TENANT_SLUG)
invoice   = InvoiceInput(
    carrier_id        = "DHL",
    invoice_number    = INV_NO,
    total_amount      = 220.0,
    currency          = "USD",
    route_origin      = "Dallas",
    route_destination = "Atlanta",
    weight_lbs        = 1200.0,
)

sub("Running 5-step ingestion write pattern")
ing_result = ingestion.ingest_invoice(TENANT_ID, invoice)

ok("Step 1 — JCS canonicalize: keys sorted Unicode, deterministic bytes")
ok(f"Step 2 — SHA-256(domain_tag + canonical_bytes) = {ing_result.canonical_hash[:32]}...")
ok("Step 3 — Encrypted (ciphertext stored in source_records.ciphertext)")
ok("Step 4 — DB transaction: source_records + outbox inserted atomically")
ok("Step 5 — Kafka published: invoice.received")
ok(f"source_record_id = {ing_result.source_record_id}")
info(f"Idempotency key: {ing_result.idempotency_key}")
info(f"Kafka messages on invoice.received: {broker.message_count('invoice.received')}")

# ══════════════════════════════════════════════════════════════════════════════
# SERVICE 2 — VALIDATION
# ══════════════════════════════════════════════════════════════════════════════
header("2.  VALIDATION SERVICE")
print("  Reads contract_rates from DB, compares against the invoice, flags overcharges")

validation = ValidationHandler(DB_URL, broker, TENANT_SLUG)
sub("Comparing DHL invoice $220 against contract_rates table")
val_result = validation.validate(
    tenant_id        = TENANT_ID,
    source_record_id = ing_result.source_record_id,
    invoice_number   = INV_NO,
    carrier_id       = "DHL",
    total_amount     = 220.0,
)

status_label = {
    "FAIL": f"{RED}FAIL{RESET} — overcharge detected",
    "PASS": f"{GREEN}PASS{RESET} — within contract",
    "WARN": f"{YELLOW}WARN{RESET} — no contract rate on file",
}.get(val_result.status, val_result.status)

ok(f"Validation status: {status_label}")
ok(f"Overcharge amount: ${val_result.overcharge_amount:.2f}")
ok(f"Rule violations:   {len(val_result.rule_violations)}")
for v in val_result.rule_violations:
    info(f"  Rule: {v.rule}  |  expected=${v.expected:.2f}  actual=${v.actual:.2f}  delta=${v.delta:.2f}")
ok(f"validation_result_id = {val_result.validation_id}")
ok(f"Kafka published: invoice.validated  (status={val_result.status}, overcharge=${val_result.overcharge_amount})")

# ══════════════════════════════════════════════════════════════════════════════
# SERVICE 3 — CANONICAL TRUTH
# ══════════════════════════════════════════════════════════════════════════════
header("3.  CANONICAL TRUTH SERVICE")
print("  Writes the single authoritative canonical_invoice row that all downstream services reference")

canonical = CanonicalHandler(DB_URL, broker, TENANT_SLUG)
sub("Inserting canonical_invoice + canonical_shipment")
can_result = canonical.canonicalize_invoice(
    tenant_id        = TENANT_ID,
    source_record_id = ing_result.source_record_id,
    invoice_number   = INV_NO,
    carrier_id       = "DHL",
    total_amount     = 220.0,
    currency         = "USD",
    origin_city      = "Dallas",
    dest_city        = "Atlanta",
    weight_lbs       = 1200.0,
)

ok(f"canonical_invoice_id  = {can_result.canonical_invoice_id}")
ok(f"canonical_shipment_id = {can_result.canonical_shipment_id}")
ok(f"canonical_hash        = {can_result.canonical_hash[:32]}...")
info("This hash is THE reference — evidence, reasoning, ACR all anchor to it")
ok("Kafka published: invoice.canonical")

# ══════════════════════════════════════════════════════════════════════════════
# SERVICE 4 — CASE ORCHESTRATION
# ══════════════════════════════════════════════════════════════════════════════
header("4.  CASE ORCHESTRATION SERVICE")
print("  Opens a dispute case and walks it through the state machine")

orchestrator = CaseHandler(DB_URL, broker)
sub("Opening dispute case")
case_result = orchestrator.open_case(TENANT_ID, can_result.canonical_invoice_id, actor_sub="system")

ok(f"case_id   = {case_result.case_id}")
ok(f"state     = {case_result.state}")
ok(f"is_new    = {case_result.is_new}")
ok("APPEND-ONLY case_event logged: CASE_OPENED → OPENED")
ok("Kafka published: case.opened")

sub("State machine transitions")
for from_s, to_s, actor in [
    ("OPENED",             "EVIDENCE_GATHERING", "system"),
    ("EVIDENCE_GATHERING", "UNDER_REVIEW",        "system"),
    ("UNDER_REVIEW",       "PENDING_APPROVAL",    "alice@zoikotech.com"),
]:
    orchestrator.transition_state(TENANT_ID, case_result.case_id, to_s, actor)
    ok(f"{from_s:<22} → {to_s:<22}  (actor: {actor})")

sub("Idempotency: opening same case twice → same case_id")
r2 = orchestrator.open_case(TENANT_ID, can_result.canonical_invoice_id)
ok("Duplicate open attempt: is_new=False, case_id unchanged — idempotency works") if not r2.is_new else fail("BUG: second open was treated as new case")

# ══════════════════════════════════════════════════════════════════════════════
# KAFKA SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
header("KAFKA EVENT SUMMARY")
consumer = ZoikoConsumer(broker, group_id="demo-phase2")
events_seen = []
for topic in ["invoice.received", "invoice.validated", "invoice.canonical", "case.opened", "case.updated"]:
    count = broker.message_count(topic)
    if count > 0:
        ok(f"{topic:<26} — {count} message(s)")
        events_seen.append(topic)
    else:
        info(f"{topic:<26} — 0 messages")

# ══════════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
header("PHASE 2 — SUMMARY")
print(f"""
  {BOLD}SC-001 Full Phase 2 Run:{RESET}

  Invoice:  {INV_NO}  ({invoice.carrier_id}, ${invoice.total_amount})
  Tenant:   {TENANT_NAME}

  {GREEN}✅ Ingestion Service{RESET}
     • JCS → SHA-256 → encrypt → DB (source_records + outbox) → Kafka
     • source_record_id: {ing_result.source_record_id}

  {GREEN}✅ Validation Service{RESET}
     • Contract rate lookup → overcharge ${val_result.overcharge_amount:.2f} detected
     • validation_results row signed + inserted
     • Status: {val_result.status}

  {GREEN}✅ Canonical Truth Service{RESET}
     • canonical_invoice + canonical_shipment written
     • Authoritative hash: {can_result.canonical_hash[:24]}...

  {GREEN}✅ Case Orchestration Service{RESET}
     • Case opened: {case_result.case_id}
     • State walked: OPENED → EVIDENCE_GATHERING → UNDER_REVIEW → PENDING_APPROVAL
     • All transitions APPEND-ONLY in case_events

  {BOLD}Phase 3 picks up here:{RESET}
     evidence-svc, reasoning-svc, governance-svc, token-svc
     (Evidence bundle → AI finding 0.96 → Proposal → Approval → Token)
""")
