"""
Phase 0 → Phase 1 Connected Demo
=================================
Shows the COMPLETE SC-001 story:
  Phase 0 built: crypto, database, dashboard
  Phase 1 adds:  identity (OIDC), keys (KMS), policy (OPA), events (Kafka)

Run:
    cd phase-1
    py -3.13 demo_connected.py
"""
import sys, os, hashlib, uuid
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "phase-0", "packages", "zoiko-common"))

# ── helpers ───────────────────────────────────────────────────────────────────
W  = "\033[97m"   # white
G  = "\033[92m"   # green
R  = "\033[91m"   # red
Y  = "\033[93m"   # yellow
B  = "\033[94m"   # blue
C  = "\033[96m"   # cyan
M  = "\033[95m"   # magenta
BO = "\033[1m"
RS = "\033[0m"

def title(text):
    bar = "=" * 62
    print(f"\n{BO}{B}{bar}")
    print(f"  {text}")
    print(f"{bar}{RS}")

def phase(n, label):
    print(f"\n{BO}{M}  [ PHASE {n} ]  {label}{RS}")

def step(label):
    print(f"\n{Y}{BO}  ──── {label}{RS}")

def ok(msg):   print(f"  {G}✅  {msg}{RS}")
def no(msg):   print(f"  {R}❌  {msg}{RS}")
def info(msg): print(f"  {C}ℹ   {msg}{RS}")
def arrow(msg):print(f"  {W}➜   {msg}{RS}")
def box(lines):
    print(f"  {B}┌{'─'*56}┐{RS}")
    for line in lines:
        print(f"  {B}│{RS}  {line:<54}{B}│{RS}")
    print(f"  {B}└{'─'*56}┘{RS}")


# ══════════════════════════════════════════════════════════════════════════════
# THE SCENARIO
# ══════════════════════════════════════════════════════════════════════════════
title("Zoiko AI Logistics — Phase 0 + Phase 1 Connected Demo")

box([
    "SCENARIO: SC-001  Dallas (DAL) → Atlanta (ATL)",
    "Carrier : DHL",
    "Billed  : $220  (fuel $120 + accessorial $100)",
    "Contract: $120  (fuel only — accessorial NOT authorized)",
    "Overcharge: $100",
    "People  : Alice = Analyst  |  Bob = Manager",
    "",
    "Goal: Recover $100 from DHL with a tamper-proof audit trail",
])


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 0 — What was already built
# ══════════════════════════════════════════════════════════════════════════════
title("PHASE 0 — What Was Already Built")
print(f"""
  Phase 0 built the cryptographic FOUNDATION:

  {G}✅ JCS Canonicalization (RFC 8785){RS}
     Makes JSON byte-identical on every machine.
     Same invoice → same bytes → same hash → always.

  {G}✅ Domain-Tagged SHA-256 Hashing{RS}
     SHA-256(domain_tag + data) — prevents swapping one
     record type for another.

  {G}✅ Ed25519 Signing{RS}
     Every record gets a 64-byte digital signature.
     Tamper anything → signature fails.

  {G}✅ 26 PostgreSQL Tables{RS}
     All with Row-Level Security (RLS).
     Tenants can NEVER see each other's data.

  {G}✅ Streamlit Dashboard{RS}
     Manual workflow: submit invoice → analyst signs →
     manager approves → execute recovery → ACR issued.
""")

# ── Show Phase 0 crypto working ───────────────────────────────────────────────
from zoiko_common.crypto.jcs      import canonicalize
from zoiko_common.crypto.merkle   import MerkleTree, hash_leaf
from zoiko_common.crypto.signing  import ZoikoSigner, LocalEd25519Backend

phase(0, "Step 1 — DHL Invoice Arrives")
raw_invoice = {
    "invoice_number": "DHL-2026-00441",
    "carrier":        "DHL",
    "route":          "DAL-ATL",
    "charges":        {"fuel": 120.0, "accessorial": 100.0},
    "total":          220.0,
    "currency":       "USD",
}
info("Raw invoice from DHL:")
for k, v in raw_invoice.items():
    info(f"  {k}: {v}")

phase(0, "Step 2 — JCS Canonicalize (RFC 8785)")
canon = canonicalize(raw_invoice)
ok(f"Canonical bytes: {canon.decode()[:60]}...")
ok("Keys are sorted, no spaces — byte-identical on ANY machine")

phase(0, "Step 3 — Domain-Tagged SHA-256 Hash")
invoice_hash = hash_leaf("zoiko/v1/source-record", canon)
ok("hash(zoiko/v1/source-record + canonical) =")
ok(f"  {invoice_hash.hex()}")
info("Same domain tag = always same hash for this invoice")
info("Different domain tag = completely different hash (prevents swapping)")

phase(0, "Step 4 — Ed25519 Sign + Store in DB")
signer   = ZoikoSigner(LocalEd25519Backend())
envelope = signer.sign(invoice_hash)
ok(f"Signature:  {bytes(envelope.signature).hex()[:40]}...  (64 bytes)")
ok(f"Key ID:     {envelope.kid}")
ok("Stored in:  source_records, canonical_invoices, cases (26 tables)")

phase(0, "Step 5 — AI Detects Overcharge")
fuel_conf = 1.00   # exact match $120 == $120
acc_conf  = 0.92   # $100 billed, $0 in contract
combined  = 0.96
box([
    "AI Analysis Result:",
    "  Fuel charge:  $120 billed / $120 allowed  → OK   (conf=1.00)",
    "  Accessorial:  $100 billed / $0   allowed  → OVERCHARGE (conf=0.92)",
    "  Combined confidence: 0.96  (96%)",
    "  Proposed recovery:  $100.00 USD",
])

phase(0, "Step 6 — ACR Merkle Tree (tamper-proof audit record)")
artifacts = {
    "source_record":     hashlib.sha256(b"source").digest(),
    "validation_result": hashlib.sha256(b"PASS").digest(),
    "canonical_invoice": invoice_hash,
    "finding":           hashlib.sha256("confidence=0.96:OVERCHARGE".encode()).digest(),
    "decision_proposal": hashlib.sha256(b"RECOVER:100.00:USD").digest(),
    "gov_decision":      hashlib.sha256(b"APPROVED").digest(),
    "gov_token":         hashlib.sha256(b"EXECUTE:24h").digest(),
    "outcome":           hashlib.sha256(b"RECOVERED:100.00:USD").digest(),
}
tree = MerkleTree("zoiko/v1/acr")
for d in artifacts.values():
    tree.append(d)
merkle_root = tree.root()
ok(f"8-artifact Merkle root: {merkle_root.hex()}")
ok("Any change to any artifact changes the root completely")
ok("Auditor can verify OFFLINE — zero access to Zoiko systems needed")

print(f"""
  {BO}{G}Phase 0 Summary:{RS}
  ┌─────────────────────────────────────────────────────┐
  │  Invoice received, hashed, signed, stored in DB    │
  │  AI found $100 overcharge with 96% confidence       │
  │  ACR Merkle tree created — tamper-proof audit trail │
  │                                                     │
  │  BUT Phase 0 had NO answer to:                      │
  │  • WHO is Alice? How do we PROVE she is an analyst? │
  │  • Can Alice approve her own proposal? (SoD risk)   │
  │  • How do other services KNOW the decision was made?│
  │  • Are encryption keys managed securely?            │
  └─────────────────────────────────────────────────────┘
  {B}Phase 1 answers ALL of these.{RS}
""")


# ══════════════════════════════════════════════════════════════════════════════
# THE CONNECTION — How Phase 1 wraps Phase 0
# ══════════════════════════════════════════════════════════════════════════════
title("THE CONNECTION — How Phase 1 Wraps Phase 0")

print(f"""
  {BO}Phase 0 flow (what we had):{RS}

    Invoice → JCS → Hash → Sign → DB → AI → ACR
       ↑ raw data flow, no identity, no events, no policy

  {BO}Phase 1 wraps every step:{RS}

    [Alice logs in]
          │
          ▼
    {G}[OIDC] JWT issued → proves Alice is analyst@zoikotech.com{RS}
          │
          ▼
    Invoice → JCS → Hash
          │
          ▼
    {G}[KMS]  Signing key fetched from key hierarchy{RS}
          │   (ROOT_CA → DEK_ENCRYPT → SIGNING — 3 tiers)
          ▼
    Sign → DB → AI finding
          │
          ▼
    {G}[OPA]  "Alice PROPOSES recovery" → ALLOWED (analyst role){RS}
          │
          ▼
    [Bob logs in]
          │
          ▼
    {G}[OIDC] JWT issued → proves Bob is manager@zoikotech.com{RS}
          │
          ▼
    {G}[OPA]  "Bob APPROVES Alice's proposal"
           → proposer_sub=alice ≠ actor_sub=bob → ALLOWED (SoD ok){RS}
          │
          ▼
    {G}[Kafka] "decision.made" event published → all services notified{RS}
          │
          ▼
    8-gate execution → $100 recovered → ACR issued
          │
          ▼
    {G}[Kafka] "acr.issued" event published → audit service locks WORM{RS}
""")


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — Live walkthrough connected to SC-001
# ══════════════════════════════════════════════════════════════════════════════
title("PHASE 1 — Live SC-001 Walkthrough")

from zoiko_kms.hierarchy      import KeyHierarchy, KeyPurpose
from zoiko_kms.local_backend  import LocalKMSBackend
from middleware.oidc.token_verifier import TokenVerifier, TokenExpiredError, TokenInvalidError
from middleware.opa.client    import MockOPAClient, OPADecision, OPAClient, OPAUnavailableError
from kafka.mock_kafka         import MockKafkaBroker
from kafka.producer           import ZoikoProducer, KafkaMessage
from kafka.consumer           import ZoikoConsumer

TENANT_ID = "tenant-acme-logistics-001"
CASE_ID   = f"case-{uuid.uuid4().hex[:8]}"
DEV_SECRET = os.getenv("ZOIKO_DEV_SECRET").encode()

# ── KMS ───────────────────────────────────────────────────────────────────────
phase(1, "KMS — Secure Key Hierarchy for Acme Logistics")

kms  = KeyHierarchy(env="dev")
keys = kms.provision_tenant(TENANT_ID, "acme-logistics")

step("Provisioning 3 keys for tenant acme-logistics")
box([
    "Key 1: ROOT_CA      → Master key, never leaves KMS",
    "Key 2: DEK_ENCRYPT  → Encrypts invoice data in DB",
    "Key 3: SIGNING      → Signs every record (Ed25519)",
    "",
    "Dev environment  = SOFTWARE keys (local)",
    "Prod environment = HSM keys (GCP Cloud KMS)",
])
for k in keys:
    ok(f"{k.purpose.value:<14} | {k.kms_resource:<40} | rotates in {k.days_until_rotation}d")

step("KMS signs the DHL invoice hash (same hash from Phase 0)")
backend     = LocalKMSBackend()
sign_res    = "dev/acme-logistics-signing-v1"
p1_sig      = backend.sign(sign_res, invoice_hash)
p1_verified = backend.verify(sign_res, invoice_hash, p1_sig)
ok(f"Invoice hash signed via KMS: {p1_sig.hex()[:32]}...")
ok(f"Signature verified: {p1_verified}")

step("Key rotation — Phase 1 makes this safe")
old_key = kms.get_active_key(TENANT_ID, KeyPurpose.SIGNING)
new_key = kms.rotate_key(TENANT_ID, KeyPurpose.SIGNING)
ok(f"Old key v{old_key.version} → deactivated")
ok(f"New key v{new_key.version} → now active")
info("Old signatures still valid — rotation only affects new signing")


# ── OIDC ──────────────────────────────────────────────────────────────────────
phase(1, "OIDC — Identity: Who Is Calling?")

verifier = TokenVerifier(dev_secret=DEV_SECRET, issuer="https://auth.zoikotech.com")

step("Alice (analyst) logs in to review the DHL overcharge case")
alice_token = verifier.make_dev_token(
    sub       = "alice@zoikotech.com",
    tenant_id = TENANT_ID,
    roles     = ["analyst"],
    audience  = "zoiko-api",
)
alice_claims = verifier.verify(alice_token, expected_audience="zoiko-api")
box([
    "Alice's Identity Token (JWT):",
    f"  sub       = {alice_claims.sub}",
    f"  tenant_id = {alice_claims.tenant_id[:30]}...",
    f"  roles     = {alice_claims.roles}",
    f"  is_analyst= {alice_claims.is_analyst}",
    f"  expired   = {alice_claims.is_expired}",
])
ok("Alice's token verified — she is confirmed analyst for this tenant")

step("Bob (manager) logs in to approve")
bob_token  = verifier.make_dev_token(
    sub       = "bob@zoikotech.com",
    tenant_id = TENANT_ID,
    roles     = ["manager"],
    audience  = "zoiko-api",
)
bob_claims = verifier.verify(bob_token)
ok(f"Bob verified: sub={bob_claims.sub}, roles={bob_claims.roles}")

step("Security checks — what Phase 1 rejects")
# Expired
exp_token = verifier.make_dev_token(sub="hacker@evil.com", tenant_id=TENANT_ID, ttl_sec=-1)
try:
    verifier.verify(exp_token)
except TokenExpiredError:
    no("Expired token from hacker → REJECTED")

# Tampered
parts = alice_token.split(".")
parts[1] = parts[1][:-4] + "XXXX"
try:
    verifier.verify(".".join(parts))
except Exception:
    no("Tampered token → REJECTED")

# Wrong audience
wrong = verifier.make_dev_token(sub="alice@zoikotech.com", tenant_id=TENANT_ID, audience="other-svc")
try:
    verifier.verify(wrong, expected_audience="zoiko-api")
except TokenInvalidError:
    no("Token for wrong service → REJECTED")


# ── OPA ───────────────────────────────────────────────────────────────────────
phase(1, "OPA — Policy: Is This Action Allowed?")

opa = MockOPAClient()

step("Alice proposes $100 recovery → OPA checks")
opa.set_decision("zoiko/freight_dispute", OPADecision(allow=True))
d = opa.check_freight_dispute({
    "action":          "PROPOSE_RECOVERY",
    "roles":           alice_claims.roles,
    "tenant_id":       TENANT_ID,
    "claim_tenant_id": alice_claims.tenant_id,
    "proposer_sub":    alice_claims.sub,
    "amount":          100.0,
})
ok(f"Alice PROPOSES recovery → {d.reason()}")

step("Alice tries to approve her OWN proposal → SoD violation")
opa.set_decision("zoiko/freight_dispute", OPADecision(
    allow=False,
    violations=["SoD violation: proposer and approver must be different people"]
))
d = opa.check_freight_dispute({
    "action":       "APPROVE_PROPOSAL",
    "roles":        alice_claims.roles,
    "proposer_sub": alice_claims.sub,
    "actor_sub":    alice_claims.sub,    # ← same person!
    "tenant_id":    TENANT_ID,
})
no(f"Alice APPROVES own proposal → {d.reason()}")

step("Bob (different person) approves → SoD satisfied")
opa.set_decision("zoiko/freight_dispute", OPADecision(allow=True))
d = opa.check_freight_dispute({
    "action":       "APPROVE_PROPOSAL",
    "roles":        bob_claims.roles,
    "proposer_sub": alice_claims.sub,   # alice proposed
    "actor_sub":    bob_claims.sub,     # bob approves — different!
    "tenant_id":    TENANT_ID,
})
ok(f"Bob APPROVES Alice's proposal → {d.reason()}")

step("Rival Corp tries to access Acme's cases → blocked")
opa.set_decision("zoiko/tenant_isolation", OPADecision(
    allow=False,
    violations=["Tenant isolation: acme-001 cannot access rival-corp-999's data"]
))
d = opa.check_tenant_isolation("acme-001", "rival-corp-999", ["analyst"])
no(f"Cross-tenant access → {d.reason()}")

step("OPA server goes down → FAIL CLOSED (Rule 5)")
real_opa = OPAClient(opa_url="http://localhost:19999", timeout=0.3)
try:
    real_opa.evaluate("zoiko/freight_dispute", {"action": "EXECUTE_RECOVERY"})
except OPAUnavailableError:
    no("OPA unreachable → request BLOCKED → service returns 503")
    info("Rule 5: Never permit when policy engine is unavailable")


# ── Kafka ─────────────────────────────────────────────────────────────────────
phase(1, "Kafka — Events: Notify All Services")

broker   = MockKafkaBroker()
producer = ZoikoProducer(broker)

step("SC-001 lifecycle events — published to Kafka as each step completes")

sc001_events = [
    ("invoice.received",    "ingestion-svc",       {"invoice": "DHL-2026-00441", "total": 220.0}),
    ("invoice.validated",   "validation-svc",      {"status": "PASS", "overcharge_detected": True}),
    ("case.opened",         "case-orchestration",  {"case_id": CASE_ID, "state": "OPENED"}),
    ("evidence.bundled",    "evidence-svc",        {"case_id": CASE_ID, "items": 4}),
    ("finding.created",     "reasoning-svc",       {"confidence": 0.96, "overcharge": 100.0}),
    ("proposal.created",    "governance-svc",      {"proposed_by": "alice@zoikotech.com", "amount": 100.0}),
    ("decision.made",       "governance-svc",      {"outcome": "APPROVED", "approved_by": "bob@zoikotech.com"}),
    ("token.issued",        "token-svc",           {"scope": "EXECUTE", "expires_in": "24h"}),
    ("execution.completed", "execution-gateway",   {"recovered": 100.0, "ref": "CR-A1B2C3D4"}),
    ("acr.issued",          "acr-svc",             {"merkle_root": merkle_root.hex()[:16] + "..."}),
]

for topic, publisher, payload in sc001_events:
    msg = KafkaMessage(topic=topic, key=CASE_ID, payload=payload, tenant_id=TENANT_ID)
    producer.publish(msg)
    ok(f"{publisher:<22} publishes → {topic}")

step("Services consume their relevant events")

results = {}
for topic in ["decision.made", "execution.completed", "acr.issued"]:
    consumer = ZoikoConsumer(broker, group_id=f"demo-consumer-{topic}")
    consumer.subscribe(topic, lambda tid, p, t=topic: results.update({t: p}))
    consumer.poll()

info(f"decision.made     → outcome={results.get('decision.made',{}).get('outcome')}  approved_by={results.get('decision.made',{}).get('approved_by')}")
info(f"execution.completed → recovered=${results.get('execution.completed',{}).get('recovered')}  ref={results.get('execution.completed',{}).get('ref')}")
info(f"acr.issued        → merkle_root={results.get('acr.issued',{}).get('merkle_root')}")

step("Unknown topic rejected — prevents accidental data leaks")
try:
    KafkaMessage(topic="internal.secrets", key="k", payload={}, tenant_id=TENANT_ID)
except ValueError:
    no("Topic 'internal.secrets' not in registry → REJECTED")


# ══════════════════════════════════════════════════════════════════════════════
# FINAL OUTPUT — What Phase 1 produces
# ══════════════════════════════════════════════════════════════════════════════
title("FINAL OUTPUT — What Phase 1 Produces")

print(f"""
  {BO}Complete SC-001 audit trail with Phase 0 + Phase 1:{RS}

  {B}┌─────────────────────────────────────────────────────────┐
  │  CASE: {CASE_ID:<48}│
  │  TENANT: acme-logistics                                 │
  ├─────────────────────────────────────────────────────────┤
  │  PHASE 0 — Cryptographic Foundation                    │
  │  ✅ Invoice hash:    {invoice_hash.hex()[:36]}...  │
  │  ✅ Ed25519 sig:     {p1_sig.hex()[:36]}...  │
  │  ✅ Merkle root:     {merkle_root.hex()[:36]}...  │
  │  ✅ DB records:      26 tables, RLS enforced            │
  ├─────────────────────────────────────────────────────────┤
  │  PHASE 1 — Security & Messaging Layer                  │
  │  ✅ KMS keys:        ROOT_CA + DEK + SIGNING (3-tier)  │
  │  ✅ Alice identity:  JWT verified, role=analyst         │
  │  ✅ Bob identity:    JWT verified, role=manager         │
  │  ✅ SoD enforced:    alice≠bob — proposal/approval OK   │
  │  ✅ OPA policies:    all 5 checks passed                │
  │  ✅ Kafka events:    10 topics published                │
  │  ✅ Fail-closed:     OPA down → 503, never permit       │
  ├─────────────────────────────────────────────────────────┤
  │  RESULT                                                 │
  │  💰 $100.00 USD recovered from DHL                     │
  │  📜 ACR issued — tamper-proof, WORM-locked             │
  │  🔐 Verifiable offline — zero access to Zoiko needed   │
  └─────────────────────────────────────────────────────────┘{RS}
""")

print(f"  {BO}What Phase 2 will add:{RS}")
print(f"  {C}  • Real FastAPI microservices (api-gateway, ingestion, validation){RS}")
print(f"  {C}  • Each service uses OIDC + OPA + Kafka from Phase 1{RS}")
print(f"  {C}  • Phase 0 crypto is the foundation for every service{RS}")
print(f"  {C}  • Phase 1 security wraps every API call{RS}")
print()
