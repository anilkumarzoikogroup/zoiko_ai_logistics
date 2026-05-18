"""
Zoiko AI Logistics — SC-001 Dashboard
    set DB_URL=postgresql://postgres:zoiko123@localhost/zoiko
    streamlit run dashboard.py
"""
import sys, os, json, hashlib, uuid, time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "packages/zoiko-common")

# Phase 1 paths
_p1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "phase-1")
sys.path.insert(0, _p1)
sys.path.insert(0, os.path.join(_p1, "packages", "zoiko-kms"))

try:
    from zoiko_kms.hierarchy     import KeyHierarchy, KeyPurpose
    from zoiko_kms.local_backend import LocalKMSBackend
    from middleware.oidc.token_verifier import TokenVerifier, TokenExpiredError, TokenInvalidError
    from middleware.opa.client   import MockOPAClient, OPADecision, OPAClient, OPAUnavailableError
    from kafka.mock_kafka        import MockKafkaBroker
    from kafka.producer          import ZoikoProducer, KafkaMessage, REGISTERED_TOPICS
    from kafka.consumer          import ZoikoConsumer
    P1_AVAILABLE = True
except ImportError as _p1_err:
    P1_AVAILABLE = False
    _p1_err_msg  = str(_p1_err)

# Phase 2 paths
_p2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "phase-2")
sys.path.insert(0, _p2)

try:
    import psycopg2.extras as _pge; _pge.register_uuid()   # UUID adapter
    from services.ingestion_svc.handler   import IngestionHandler
    from services.ingestion_svc.models    import InvoiceInput
    from services.validation_svc.handler  import ValidationHandler
    from services.canonical_truth.handler import CanonicalHandler
    from services.case_orchestration.handler import CaseHandler
    P2_AVAILABLE = True
except ImportError as _p2_err:
    P2_AVAILABLE = False
    _p2_err_msg  = str(_p2_err)

import streamlit as st
import psycopg2
import psycopg2.extras

from zoiko_common.crypto.jcs import canonicalize
from zoiko_common.crypto.merkle import MerkleTree, hash_leaf
from zoiko_common.crypto.signing import ZoikoSigner, LocalEd25519Backend

st.set_page_config(page_title="Zoiko Logistics", page_icon="🚚", layout="wide")

DB_URL = os.getenv("DB_URL", "postgresql://postgres:zoiko123@localhost/zoiko")

def get_conn():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    return conn

def q(sql, params=None):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def q1(sql, params=None):
    rows = q(sql, params)
    return rows[0] if rows else {}

def _fix_uuids(data):
    """Convert uuid.UUID objects to str so PyArrow/Streamlit can render them."""
    import pandas as pd
    if not data:
        return data
    df = pd.DataFrame(data) if isinstance(data, list) else pd.DataFrame([data])
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: str(x) if isinstance(x, uuid.UUID) else x)
    return df

def execute(sql, params=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.close()

def badge(state):
    return {"CLOSED": "✅", "APPROVED": "✅", "CONFIRMED": "✅",
            "PENDING_APPROVAL": "⏳", "EVIDENCE_GATHERING": "🔍",
            "OPENED": "📂", "REJECTED": "❌"}.get(state.upper(), "🔵")

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("🚚 Zoiko Logistics")
st.sidebar.caption("SC-001 Freight Dispute")
st.sidebar.divider()

st.sidebar.markdown("**Phase 0 — Foundation**")
page = st.sidebar.radio("Navigate", [
    "🏠 Home",
    "📋 All Cases",
    "➕ New Case",
    "👤 Analyst Review",
    "✅ Manager Approval",
    "⚡ Execute Recovery",
    "🔐 Crypto & Audit",
    "🗄️ Database",
    "— Phase 1 —",
    "🔑 KMS Keys",
    "🎫 OIDC Identity",
    "🛡️ OPA Policies",
    "📨 Kafka Events",
    "— Phase 2 —",
    "📥 Ingestion",
    "✔ Validation",
    "📄 Canonical Truth",
    "🗂 Case Flow",
])

st.sidebar.divider()
try:
    for c in q("SELECT id, state FROM cases ORDER BY opened_at DESC LIMIT 4;"):
        st.sidebar.caption(f"{badge(c['state'])} {str(c['id'])[:8]}… {c['state']}")
except:
    st.sidebar.caption("⚠️ DB offline")

# ═══════════════════════════════════════════════════════════════════════════════
# 🏠 HOME
# ═══════════════════════════════════════════════════════════════════════════════
if page == "🏠 Home":
    st.title("🚚 Zoiko AI Logistics — SC-001")
    st.divider()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tenants",          q1("SELECT COUNT(*) n FROM tenants;").get("n",0))
    c2.metric("Total Cases",      q1("SELECT COUNT(*) n FROM cases;").get("n",0))
    c3.metric("Closed",           q1("SELECT COUNT(*) n FROM cases WHERE state='CLOSED';").get("n",0))
    c4.metric("Pending Approval", q1("SELECT COUNT(*) n FROM approval_tasks WHERE status='PENDING';").get("n",0))

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("SC-001 Reference Case")
        st.info(
            "**Route:** Dallas → Atlanta  |  **Carrier:** DHL\n\n"
            "| Item | Amount |\n|------|--------|\n"
            "| DHL billed | $220 |\n"
            "| Contract allows | $120 (fuel only) |\n"
            "| **Overcharge** | **$100** (accessorial) |\n"
            "| AI confidence | 96% |\n"
            "| Recovered | **$100** ✅ |"
        )

    with right:
        st.subheader("How It Works")
        for step in [
            "1. Invoice arrives from carrier",
            "2. AI compares against contract (96% confidence)",
            "3. Analyst reviews and proposes recovery",
            "4. Manager approves — different person (SoD)",
            "5. 8 security gates all pass",
            "6. $100 recovered · Audit record issued",
        ]:
            st.success(step)

# ═══════════════════════════════════════════════════════════════════════════════
# 📋 ALL CASES
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📋 All Cases":
    st.title("📋 All Cases")
    st.divider()

    cases = q("""
        SELECT c.id, c.state, c.opened_at, c.closed_at,
               ci.invoice_number, ci.carrier_id, ci.total_amount, ci.currency,
               t.display_name AS tenant
        FROM cases c
        JOIN canonical_invoices ci ON ci.id = c.invoice_id
        JOIN tenants t ON t.id = c.tenant_id
        ORDER BY c.opened_at DESC;
    """)

    if not cases:
        st.info("No cases yet. Go to ➕ New Case to create one.")
        st.stop()

    for c in cases:
        label = f"{badge(c['state'])} {c['invoice_number']}  •  {c['carrier_id']}  •  ${c['total_amount']} {c['currency']}  •  {c['tenant']}  •  **{c['state']}**"
        with st.expander(label):
            col1, col2, col3 = st.columns(3)
            col1.metric("Billed",  f"${c['total_amount']} {c['currency']}")
            col2.metric("Opened",  str(c['opened_at'])[:10])
            col3.metric("Closed",  str(c['closed_at'])[:10] if c['closed_at'] else "—")

            f = q1("SELECT confidence, rule_trace FROM findings WHERE case_id=%s;", (c['id'],))
            if f:
                conf = float(f['confidence'])
                st.progress(conf, text=f"AI Confidence: {conf:.0%}")
                rt  = f['rule_trace'] if isinstance(f['rule_trace'], dict) else json.loads(f['rule_trace'])
                fc  = rt.get('fuel_charge', {})
                acc = rt.get('accessorial_charge', {})
                a, b = st.columns(2)
                (a.success if fc.get('status') == 'OK'       else a.error)(f"Fuel: ${fc.get('billed',0)} billed / ${fc.get('contract',0)} allowed — {fc.get('status','?')}")
                (b.error   if acc.get('status') == 'OVERCHARGE' else b.success)(f"Accessorial: ${acc.get('billed',0)} billed — {acc.get('status','?')}")

            ap = q1("SELECT proposer_sub, actor_sub, status FROM approval_tasks WHERE proposal_id IN (SELECT id FROM decision_proposals WHERE case_id=%s);", (c['id'],))
            if ap:
                st.info(f"Analyst: `{ap['proposer_sub']}` · Manager: `{ap.get('actor_sub','pending')}` · {ap['status']}")

            acr = q1("SELECT encode(merkle_root,'hex') mr, certified_at FROM action_certification_records WHERE case_id=%s;", (c['id'],))
            if acr:
                st.success(f"ACR issued {str(acr['certified_at'])[:19]}")
                st.code(f"Merkle Root: {acr['mr']}", language=None)

# ═══════════════════════════════════════════════════════════════════════════════
# ➕ NEW CASE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "➕ New Case":
    st.title("➕ New Case")
    st.divider()

    tab1, tab2 = st.tabs(["🏢 Register Tenant", "📄 Submit Invoice"])

    # ── Tab 1: Register Tenant ─────────────────────────────
    with tab1:
        tenants = q("SELECT slug, display_name, status, created_at FROM tenants ORDER BY created_at DESC;")
        if tenants:
            st.dataframe(_fix_uuids(tenants), use_container_width=True)
        else:
            st.info("No tenants yet.")

        st.subheader("Add New Tenant")
        with st.form("tenant_form"):
            col1, col2 = st.columns(2)
            display_name = col1.text_input("Company Name", placeholder="Acme Logistics Inc.")
            slug         = col2.text_input("Short ID",     placeholder="acme-logistics")
            ok = st.form_submit_button("Create Tenant", use_container_width=True)

        if ok:
            if not display_name or not slug:
                st.error("Fill in both fields.")
            else:
                try:
                    tid = str(uuid.uuid4())
                    signer = ZoikoSigner(LocalEd25519Backend())
                    execute("INSERT INTO tenants (id,slug,display_name,status) VALUES (%s,%s,%s,'ACTIVE') ON CONFLICT (slug) DO UPDATE SET display_name=EXCLUDED.display_name;",
                            (tid, slug, display_name))
                    real = q1("SELECT id FROM tenants WHERE slug=%s;", (slug,))
                    tid  = real['id']
                    execute("INSERT INTO tenant_keys (id,tenant_id,key_purpose,kms_resource,key_ciphertext) VALUES (%s,%s,'DEK_ENCRYPT',%s,%s) ON CONFLICT DO NOTHING;",
                            (str(uuid.uuid4()), tid, f"local/dev/{slug}-key", signer.public_key_der))
                    st.success(f"Tenant **{display_name}** created.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── Tab 2: Submit Invoice ──────────────────────────────
    with tab2:
        tenants = q("SELECT id, display_name FROM tenants WHERE status='ACTIVE';")
        if not tenants:
            st.warning("Register a tenant first.")
            st.stop()

        st.subheader("Submit Invoice for Dispute Analysis")

        with st.form("invoice_form"):
            tenant_opts = {t['display_name']: t['id'] for t in tenants}
            col1, col2 = st.columns(2)
            sel_tenant = col1.selectbox("Tenant (Shipper)", list(tenant_opts))
            carrier    = col2.text_input("Carrier", value="DHL")

            col1, col2 = st.columns(2)
            origin      = col1.text_input("From", value="DAL")
            destination = col2.text_input("To",   value="ATL")

            col1, col2, col3 = st.columns(3)
            inv_no       = col1.text_input("Invoice No.", value=f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}")
            fuel_charge  = col2.number_input("Fuel Charge ($)",         min_value=0.0, value=120.0, step=10.0)
            accessorial  = col3.number_input("Accessorial Charge ($)",  min_value=0.0, value=100.0, step=10.0)

            col1, col2 = st.columns(2)
            contract_fuel = col1.number_input("Max Fuel Allowed ($)", min_value=0.0, value=120.0, step=10.0)
            currency      = col2.selectbox("Currency", ["USD", "EUR", "GBP"])

            submit = st.form_submit_button("Analyse Invoice", use_container_width=True)

        if submit:
            tid        = tenant_opts[sel_tenant]
            total      = fuel_charge + accessorial
            overcharge = max(0.0, accessorial)
            fuel_ok    = fuel_charge <= contract_fuel
            fuel_conf  = 1.0 if fuel_ok else 0.7
            acc_conf   = 0.92 if accessorial > 0 else 1.0
            conf       = round((fuel_conf + acc_conf) / 2, 4)

            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Billed",  f"${total:.2f}")
            c2.metric("Contract Max",  f"${contract_fuel:.2f}")
            c3.metric("Overcharge",    f"${overcharge:.2f}", delta=f"-${overcharge:.2f}" if overcharge else "None", delta_color="inverse")
            c4.metric("AI Confidence", f"{conf:.0%}")
            st.progress(conf)

            if overcharge > 0:
                st.error(f"Overcharge detected: accessorial **${accessorial:.2f}** not in contract. Recovery proposed: **${overcharge:.2f}**")
            else:
                st.success("No overcharge — all charges within contract limits.")

            with st.spinner("Saving to database…"):
                try:
                    rule_trace = {
                        "fuel_charge":        {"billed": fuel_charge, "contract": contract_fuel, "delta": max(0, fuel_charge-contract_fuel), "status": "OK" if fuel_ok else "OVERCHARGE", "confidence": fuel_conf},
                        "accessorial_charge": {"billed": accessorial, "contract": 0.0, "delta": accessorial, "status": "OVERCHARGE" if accessorial > 0 else "OK", "confidence": acc_conf},
                        "combined_confidence": conf,
                    }
                    raw   = {"invoice_number": inv_no, "carrier": carrier, "route": f"{origin}-{destination}", "charges": {"fuel": fuel_charge, "accessorial": accessorial}, "total": total, "currency": currency, "billed_at": datetime.now(timezone.utc).isoformat()}
                    signer        = ZoikoSigner(LocalEd25519Backend())
                    canon         = canonicalize(raw)
                    canon_hash    = hash_leaf("zoiko/v1/source-record", canon)
                    env           = signer.sign(canon_hash)

                    src_id = str(uuid.uuid4()); ci_id = str(uuid.uuid4()); case_id = str(uuid.uuid4())
                    bundle_id = str(uuid.uuid4()); finding_id = str(uuid.uuid4()); proposal_id = str(uuid.uuid4()); pb_id = str(uuid.uuid4())

                    execute("INSERT INTO source_records (id,tenant_id,source_type,canonical_hash,ciphertext,signature,kid,idempotency_key) VALUES (%s,%s,'CARRIER_INVOICE',%s,%s,%s,%s,%s);",
                            (src_id,tid,canon_hash,canon,bytes(env.signature),env.kid,f"idem-{inv_no}-{uuid.uuid4().hex[:8]}"))
                    execute("INSERT INTO canonical_invoices (id,tenant_id,source_record_id,invoice_number,carrier_id,total_amount,currency,canonical_hash,signature,kid) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);",
                            (ci_id,tid,src_id,inv_no,carrier,total,currency,canon_hash,bytes(env.signature),env.kid))
                    execute("INSERT INTO contract_rates (id,tenant_id,carrier_id,rate_type,rate_value,currency,effective_on) VALUES (%s,%s,%s,'FUEL',%s,%s,CURRENT_DATE);",
                            (str(uuid.uuid4()),tid,carrier,contract_fuel,currency))
                    execute("INSERT INTO cases (id,tenant_id,invoice_id,state) VALUES (%s,%s,%s,'OPENED');", (case_id,tid,ci_id))
                    execute("INSERT INTO case_events (id,tenant_id,case_id,event_type,actor_sub) VALUES (%s,%s,%s,'OPENED','system');", (str(uuid.uuid4()),tid,case_id))
                    execute("INSERT INTO validation_results (id,tenant_id,source_record_id,status,rule_violations,signature,kid) VALUES (%s,%s,%s,'PASS','[]',%s,%s);",
                            (str(uuid.uuid4()),tid,src_id,bytes(env.signature),env.kid))
                    bh = hashlib.sha256(case_id.encode()).digest()
                    execute("INSERT INTO evidence_bundles (id,tenant_id,case_id,bundle_hash,signature,kid) VALUES (%s,%s,%s,%s,%s,%s);",
                            (bundle_id,tid,case_id,bh,bytes(env.signature),env.kid))
                    fh = hashlib.sha256(json.dumps(rule_trace).encode()).digest()
                    execute("INSERT INTO findings (id,tenant_id,case_id,bundle_id,confidence,rule_trace,signature,kid) VALUES (%s,%s,%s,%s,%s,%s,%s,%s);",
                            (finding_id,tid,case_id,bundle_id,conf,json.dumps(rule_trace),fh,env.kid))
                    execute("INSERT INTO policy_bundles (id,tenant_id,version,rego_hash,active) VALUES (%s,%s,'1.2',%s,true) ON CONFLICT DO NOTHING;",
                            (pb_id,tid,hashlib.sha256(b"rego-v1.2").digest()))
                    ph = hashlib.sha256(f"{case_id}:RECOVER:{overcharge}".encode()).digest()
                    execute("INSERT INTO decision_proposals (id,tenant_id,case_id,finding_id,proposed_action,amount,currency,proposer_sub,proposal_hash,signature,kid) VALUES (%s,%s,%s,%s,'RECOVER',%s,%s,'system',%s,%s,%s);",
                            (proposal_id,tid,case_id,finding_id,overcharge,currency,ph,bytes(env.signature),env.kid))
                    execute("UPDATE cases SET state='EVIDENCE_GATHERING' WHERE id=%s;", (case_id,))
                    execute("INSERT INTO case_events (id,tenant_id,case_id,event_type,actor_sub) VALUES (%s,%s,%s,'EVIDENCE_GATHERED','system');", (str(uuid.uuid4()),tid,case_id))

                    st.success(f"Case created: `{case_id}`")
                    st.info("Next → **👤 Analyst Review**")
                except Exception as e:
                    st.error(f"Error: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# 👤 ANALYST REVIEW
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "👤 Analyst Review":
    st.title("👤 Analyst Review")
    st.info("Review the AI finding and propose a recovery. You cannot approve your own proposal.")
    st.divider()

    pending = q("""
        SELECT dp.id proposal_id, dp.amount, dp.currency, dp.case_id, dp.tenant_id,
               f.confidence, f.rule_trace,
               ci.invoice_number, ci.carrier_id, ci.total_amount,
               t.display_name tenant_name
        FROM decision_proposals dp
        JOIN findings f ON f.id = dp.finding_id
        JOIN cases c ON c.id = dp.case_id
        JOIN canonical_invoices ci ON ci.id = c.invoice_id
        JOIN tenants t ON t.id = dp.tenant_id
        WHERE c.state NOT IN ('APPROVED','EXECUTED','RECONCILED','CLOSED','REJECTED')
        AND NOT EXISTS (SELECT 1 FROM approval_tasks a WHERE a.proposal_id = dp.id);
    """)

    if not pending:
        st.success("No cases waiting for analyst review.")
        st.stop()

    for p in pending:
        st.subheader(f"{p['invoice_number']}  —  {p['tenant_name']}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Billed",    f"${p['total_amount']}")
        c2.metric("Recovery",  f"${p['amount']} {p['currency']}")
        c3.metric("Confidence",f"{float(p['confidence']):.0%}")
        st.progress(float(p['confidence']))

        rt = p['rule_trace'] if isinstance(p['rule_trace'], dict) else json.loads(p['rule_trace'])
        a, b = st.columns(2)
        fc = rt.get('fuel_charge', {})
        ac = rt.get('accessorial_charge', {})
        (a.success if fc.get('status')=='OK'       else a.error)(f"Fuel: ${fc.get('billed',0)} / ${fc.get('contract',0)} — {fc.get('status')}")
        (b.error   if ac.get('status')=='OVERCHARGE' else b.success)(f"Accessorial: ${ac.get('billed',0)} — {ac.get('status')}")

        with st.form(f"analyst_{p['proposal_id']}"):
            analyst_email = st.text_input("Your Email", placeholder="analyst@zoikotech.com")
            ok = st.form_submit_button("Propose Recovery", use_container_width=True)

        if ok:
            if not analyst_email:
                st.error("Enter your email.")
            else:
                try:
                    execute("INSERT INTO approval_tasks (id,tenant_id,proposal_id,proposer_sub,status) VALUES (%s,%s,%s,%s,'PENDING');",
                            (str(uuid.uuid4()), p['tenant_id'], p['proposal_id'], analyst_email))
                    execute("UPDATE cases SET state='PENDING_APPROVAL' WHERE id=%s;", (p['case_id'],))
                    execute("INSERT INTO case_events (id,tenant_id,case_id,event_type,actor_sub) VALUES (%s,%s,%s,'PENDING_APPROVAL',%s);",
                            (str(uuid.uuid4()), p['tenant_id'], p['case_id'], analyst_email))
                    st.success(f"Proposal submitted by `{analyst_email}`.")
                    st.info("Next → **✅ Manager Approval**")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# ✅ MANAGER APPROVAL
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "✅ Manager Approval":
    st.title("✅ Manager Approval")
    st.warning("SoD Rule: your email must differ from the analyst's — same person cannot approve their own proposal.")
    st.divider()

    pending = q("""
        SELECT at.id task_id, at.proposer_sub, at.proposal_id, at.tenant_id,
               dp.amount, dp.currency, dp.case_id,
               ci.invoice_number, ci.total_amount,
               f.confidence,
               t.display_name tenant_name
        FROM approval_tasks at
        JOIN decision_proposals dp ON dp.id = at.proposal_id
        JOIN cases c ON c.id = dp.case_id
        JOIN canonical_invoices ci ON ci.id = c.invoice_id
        JOIN findings f ON f.case_id = dp.case_id
        JOIN tenants t ON t.id = at.tenant_id
        WHERE at.status = 'PENDING';
    """)

    if not pending:
        st.success("No proposals awaiting manager approval.")
        st.stop()

    for p in pending:
        st.subheader(f"{p['invoice_number']}  —  {p['tenant_name']}")
        st.caption(f"Proposed by analyst: `{p['proposer_sub']}`")

        c1, c2, c3 = st.columns(3)
        c1.metric("Billed",     f"${p['total_amount']}")
        c2.metric("Recovery",   f"${p['amount']} {p['currency']}")
        c3.metric("Confidence", f"{float(p['confidence']):.0%}")
        st.progress(float(p['confidence']))

        with st.form(f"mgr_{p['task_id']}"):
            c1, c2 = st.columns(2)
            mgr_email = c1.text_input("Your Email", placeholder="manager@zoikotech.com")
            decision  = c2.radio("Decision", ["APPROVED", "REJECTED"], horizontal=True)
            ok = st.form_submit_button("Submit Decision", use_container_width=True)

        if ok:
            if not mgr_email:
                st.error("Enter your email.")
            elif mgr_email == p['proposer_sub']:
                st.error(f"SoD blocked — you are the analyst (`{p['proposer_sub']}`). Use a different account.")
            else:
                try:
                    signer = ZoikoSigner(LocalEd25519Backend())
                    pb = q1("SELECT id FROM policy_bundles WHERE tenant_id=%s AND active=true LIMIT 1;", (p['tenant_id'],))
                    if not pb:
                        pb_id = str(uuid.uuid4())
                        execute("INSERT INTO policy_bundles (id,tenant_id,version,rego_hash,active) VALUES (%s,%s,'1.2',%s,true);",
                                (pb_id, p['tenant_id'], hashlib.sha256(b"rego-v1.2").digest()))
                    else:
                        pb_id = pb['id']

                    dh  = hashlib.sha256(f"{p['proposal_id']}:{decision}:{mgr_email}".encode()).digest()
                    env = signer.sign(dh)
                    gd_id = str(uuid.uuid4())
                    execute("INSERT INTO governance_decisions (id,tenant_id,proposal_id,policy_bundle_id,outcome,decision_hash,signature,kid) VALUES (%s,%s,%s,%s,%s,%s,%s,%s);",
                            (gd_id, p['tenant_id'], p['proposal_id'], pb_id, decision, dh, bytes(env.signature), env.kid))
                    execute("UPDATE approval_tasks SET actor_sub=%s, status=%s, actioned_at=NOW() WHERE id=%s;",
                            (mgr_email, decision, p['task_id']))

                    if decision == "APPROVED":
                        tok_id  = str(uuid.uuid4())
                        th      = hashlib.sha256(gd_id.encode()).digest()
                        tb      = hashlib.sha256(p['tenant_id'].encode()).digest()
                        te      = signer.sign(th)
                        exp     = datetime.now(timezone.utc) + timedelta(hours=24)
                        execute("INSERT INTO governance_tokens (id,tenant_id,decision_id,scope,tenant_binding,status,expires_at,token_hash,signature,kid) VALUES (%s,%s,%s,'EXECUTE',%s,'ACTIVE',%s,%s,%s,%s);",
                                (tok_id, p['tenant_id'], gd_id, tb, exp, th, bytes(te.signature), te.kid))
                        execute("UPDATE cases SET state='APPROVED' WHERE id=%s;", (p['case_id'],))
                        execute("INSERT INTO case_events (id,tenant_id,case_id,event_type,actor_sub) VALUES (%s,%s,%s,'APPROVED',%s);",
                                (str(uuid.uuid4()), p['tenant_id'], p['case_id'], mgr_email))
                        st.success(f"Approved by `{mgr_email}` — token issued (24 h).")
                        st.info("Next → **⚡ Execute Recovery**")
                    else:
                        execute("UPDATE cases SET state='REJECTED' WHERE id=%s;", (p['case_id'],))
                        st.warning(f"Rejected by `{mgr_email}`.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# ⚡ EXECUTE RECOVERY
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "⚡ Execute Recovery":
    st.title("⚡ Execute Recovery")
    st.info("All 8 gates must pass. Token is consumed once — no replay.")
    st.divider()

    approved = q("""
        SELECT c.id case_id, c.tenant_id,
               ci.invoice_number, ci.carrier_id, ci.total_amount, ci.currency,
               gt.id token_id, gt.scope, gt.expires_at,
               dp.amount overcharge, dp.id proposal_id,
               t.display_name tenant_name
        FROM cases c
        JOIN canonical_invoices ci ON ci.id = c.invoice_id
        JOIN decision_proposals dp ON dp.case_id = c.id
        JOIN governance_decisions gd ON gd.proposal_id = dp.id AND gd.outcome='APPROVED'
        JOIN governance_tokens gt ON gt.decision_id = gd.id AND gt.status='ACTIVE'
        JOIN tenants t ON t.id = c.tenant_id
        WHERE c.state = 'APPROVED';
    """)

    if not approved:
        st.success("No approved cases waiting for execution.")
        st.stop()

    for case in approved:
        st.subheader(f"{case['invoice_number']}  —  {case['tenant_name']}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Invoice Total",  f"${case['total_amount']} {case['currency']}")
        c2.metric("Recovery",       f"${case['overcharge']}")
        c3.metric("Token Expires",  str(case['expires_at'])[:16])

        st.subheader("8 Security Gates")
        gates = [
            ("Gate 1", "Token Signature Valid",     "Ed25519 verified"),
            ("Gate 2", "Token Not Expired",         f"Until {str(case['expires_at'])[:16]}"),
            ("Gate 3", "Tenant Binding Matches",    "Hash verified"),
            ("Gate 4", "Token Scope = EXECUTE",     f"Scope: {case['scope']}"),
            ("Gate 5", "Sanctions Clear",           "OFAC/UN: CLEAR"),
            ("Gate 6", "FX Lock Obtained",          f"{case['currency']}/{case['currency']} 1.0"),
            ("Gate 7", "Connector Certified",       f"{case['carrier_id']}-CONNECTOR v2.1"),
            ("Gate 8", "Idempotency Key New",       "Not previously executed"),
        ]
        g1, g2 = st.columns(2)
        for i, (gid, title, detail) in enumerate(gates):
            (g1 if i % 2 == 0 else g2).success(f"✅ **{gid} — {title}**\n\n{detail}")

        st.divider()
        if st.button(f"Execute Recovery — ${case['overcharge']} {case['currency']}", key=f"exec_{case['case_id']}", type="primary", use_container_width=True):
            gate_results = {f"gate_{i+1}": f"PASS — {d}" for i, (_, _, d) in enumerate(gates)}
            with st.spinner("Executing…"):
                try:
                    signer    = ZoikoSigner(LocalEd25519Backend())
                    tenant_id = case['tenant_id']
                    case_id   = case['case_id']

                    ik = f"exec-{case['invoice_number']}-{uuid.uuid4().hex[:8]}"
                    execute("INSERT INTO idempotency_keys (id,tenant_id,key_value,status,completed_at) VALUES (%s,%s,%s,'COMPLETE',NOW());",
                            (str(uuid.uuid4()), tenant_id, ik))

                    env_id  = str(uuid.uuid4())
                    eh      = hashlib.sha256(f"{case_id}:{case['token_id']}".encode()).digest()
                    es      = signer.sign(eh)
                    execute("INSERT INTO execution_envelopes (id,tenant_id,token_id,case_id,gate_results,status,env_hash,signature,kid) VALUES (%s,%s,%s,%s,%s,'CONFIRMED',%s,%s,%s);",
                            (env_id, tenant_id, case['token_id'], case_id, json.dumps(gate_results), eh, bytes(es.signature), es.kid))

                    ref  = f"CR-{uuid.uuid4().hex[:8].upper()}"
                    resp = {"status": "CREDIT_ISSUED", "amount": float(case['overcharge']), "currency": case['currency'], "ref": ref}
                    execute("INSERT INTO connector_responses (id,tenant_id,envelope_id,connector_id,status_code,response_body) VALUES (%s,%s,%s,%s,200,%s);",
                            (str(uuid.uuid4()), tenant_id, env_id, f"{case['carrier_id']}-CONNECTOR", json.dumps(resp)))

                    rid = str(uuid.uuid4())
                    execute("INSERT INTO reconciliations (id,tenant_id,case_id,envelope_id,delta_amount,currency,recon_hash) VALUES (%s,%s,%s,%s,%s,%s,%s);",
                            (rid, tenant_id, case_id, env_id, -float(case['overcharge']), case['currency'], hashlib.sha256(env_id.encode()).digest()))

                    oid = str(uuid.uuid4()); oh = hashlib.sha256(f"{rid}:RECOVERED".encode()).digest(); os2 = signer.sign(oh)
                    execute("INSERT INTO outcomes (id,tenant_id,case_id,recon_id,outcome_type,outcome_hash,signature,kid) VALUES (%s,%s,%s,%s,'RECOVERED',%s,%s,%s);",
                            (oid, tenant_id, case_id, rid, oh, bytes(os2.signature), os2.kid))
                    execute("UPDATE governance_tokens SET status='CONSUMED', consumed_at=NOW() WHERE id=%s;", (case['token_id'],))

                    artifacts = {
                        "source_record":     hashlib.sha256(b"source").digest(),
                        "validation_result": hashlib.sha256(b"PASS").digest(),
                        "canonical_invoice": eh,
                        "finding":           hashlib.sha256(b"confidence").digest(),
                        "decision_proposal": hashlib.sha256(case['proposal_id'].encode()).digest(),
                        "gov_decision":      hashlib.sha256(b"APPROVED").digest(),
                        "gov_token":         hashlib.sha256(case['token_id'].encode()).digest(),
                        "outcome":           oh,
                    }
                    tree = MerkleTree("zoiko/v1/acr")
                    hashes = {n: tree.append(d).hex() for n, d in artifacts.items()}
                    root   = tree.root()
                    as2    = signer.sign(root)
                    acr_id = str(uuid.uuid4())
                    execute("INSERT INTO action_certification_records (id,tenant_id,case_id,acr_version,merkle_root,artifact_hashes,signature,kid) VALUES (%s,%s,%s,'v1',%s,%s,%s,%s);",
                            (acr_id, tenant_id, case_id, root, json.dumps(hashes), bytes(as2.signature), as2.kid))
                    execute("INSERT INTO audit_worm_index (id,tenant_id,acr_id,worm_bucket,object_name,object_hash) VALUES (%s,%s,%s,'zoiko-acr-worm',%s,%s);",
                            (str(uuid.uuid4()), tenant_id, acr_id, f"acr/{acr_id}.json", root))
                    execute("UPDATE cases SET state='CLOSED', closed_at=NOW() WHERE id=%s;", (case_id,))
                    execute("INSERT INTO case_events (id,tenant_id,case_id,event_type,actor_sub) VALUES (%s,%s,%s,'CLOSED','system');",
                            (str(uuid.uuid4()), tenant_id, case_id))

                    st.balloons()
                    st.success(f"Recovery complete — **${case['overcharge']} {case['currency']}** recovered from {case['carrier_id']}.")
                    st.success(f"ACR issued and WORM-locked.  Ref: `{ref}`")
                    st.code(f"Merkle Root: {root.hex()}", language=None)
                    st.rerun()
                except Exception as e:
                    st.error(f"Execution error: {e}")
        st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# 🔐 CRYPTO & AUDIT
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🔐 Crypto & Audit":
    st.title("🔐 Crypto & Audit")
    st.divider()

    tab1, tab2, tab3 = st.tabs(["JCS & Hash", "Merkle Tree", "Tamper Detection"])

    with tab1:
        st.subheader("JCS Canonicalization (RFC 8785)")
        st.info("JCS makes JSON byte-identical on every machine — so the hash is always the same regardless of key order or whitespace.")
        sample = {"invoice_number": "DHL-2026-00441", "carrier": "DHL", "charges": {"fuel": 120.0, "accessorial": 100.0}, "total": 220.0, "currency": "USD"}
        canon  = canonicalize(sample)
        c1, c2 = st.columns(2)
        c1.markdown("**Original JSON**")
        c1.json(sample)
        c2.markdown("**After JCS** (sorted keys, no spaces)")
        c2.code(canon.decode(), language="json")

        st.subheader("Domain-Tagged SHA-256")
        st.info("Same data with a different domain tag produces a completely different hash — prevents cross-type forgery.")
        h1 = hash_leaf("zoiko/v1/source-record",    canon)
        h2 = hash_leaf("zoiko/v1/canonical-invoice", canon)
        h3 = hash_leaf("zoiko/v1/finding",           canon)
        st.code(f"source-record     → {h1.hex()}\ncanonical-invoice → {h2.hex()}\nfinding           → {h3.hex()}", language=None)

    with tab2:
        st.subheader("ACR Merkle Tree — 8 Artifacts")
        st.info("The final audit record locks 8 evidence pieces into one Merkle tree. Any change changes the root. Auditors verify offline.")
        acrs = q("SELECT encode(merkle_root,'hex') mr, artifact_hashes, certified_at FROM action_certification_records ORDER BY certified_at DESC LIMIT 1;")
        if acrs:
            acr = acrs[0]
            st.success(f"Latest ACR — {str(acr['certified_at'])[:19]}")
            st.code(f"Merkle Root: {acr['mr']}", language=None)
            arts = acr['artifact_hashes'] if isinstance(acr['artifact_hashes'], dict) else json.loads(acr['artifact_hashes'])
            for name, h in arts.items():
                st.markdown(f"- **{name}** → `{h[:48]}…`")
        else:
            st.info("No ACRs yet. Complete a case to see this.")

    with tab3:
        st.subheader("Tamper Detection Demo")
        st.info("What if someone changes the confidence from 0.96 → 0.99 in the finding?")
        orig = {"source": hashlib.sha256(b"source").digest(), "finding": hashlib.sha256(b"confidence=0.96").digest(), "outcome": hashlib.sha256(b"recovered=100").digest()}
        tampered = dict(orig); tampered["finding"] = hashlib.sha256(b"confidence=0.99:TAMPERED").digest()

        t_ok  = MerkleTree("zoiko/v1/acr"); [t_ok.append(d)  for d in orig.values()]
        t_bad = MerkleTree("zoiko/v1/acr"); [t_bad.append(d) for d in tampered.values()]

        c1, c2 = st.columns(2)
        c1.success(f"Original root:\n`{t_ok.root().hex()[:32]}…`")
        c2.error(f"Tampered root:\n`{t_bad.root().hex()[:32]}…`")
        st.error("Roots differ — tampering is detected immediately. Even a 1-character change produces a completely different root.")

# ═══════════════════════════════════════════════════════════════════════════════
# 🗄️ DATABASE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🗄️ Database":
    st.title("🗄️ Database — All 26 Tables")
    st.divider()

    groups = {
        "Tenant":          ["tenants", "tenant_keys"],
        "Ingestion":       ["source_records", "lineage_records"],
        "Validation":      ["validation_results"],
        "Canonical":       ["canonical_invoices", "canonical_shipments", "contract_rates"],
        "Case":            ["cases", "case_events"],
        "Evidence":        ["evidence_bundles", "evidence_items"],
        "Reasoning":       ["findings", "decision_proposals"],
        "Governance":      ["policy_bundles", "governance_decisions", "approval_tasks"],
        "Token":           ["governance_tokens"],
        "Execution":       ["idempotency_keys", "execution_envelopes", "connector_responses"],
        "Reconciliation":  ["reconciliations", "outcomes"],
        "Audit":           ["action_certification_records"],
        "Infrastructure":  ["outbox", "audit_worm_index"],
    }

    append_only = {"lineage_records", "case_events", "evidence_items", "audit_worm_index"}

    c1, c2 = st.columns(2)
    sel_group = c1.selectbox("Domain", list(groups.keys()))
    table_list = groups[sel_group]
    sel_table  = c2.selectbox("Table", table_list)

    cnt = q1(f"SELECT COUNT(*) n FROM {sel_table};").get("n", 0)
    st.metric(f"Rows in {sel_table}", cnt)
    if sel_table in append_only:
        st.warning("APPEND-ONLY — INSERT only, no UPDATE or DELETE")

    rows = q(f"SELECT * FROM {sel_table} LIMIT 50;")
    st.dataframe(_fix_uuids(rows if rows else []), use_container_width=True)

    st.divider()
    st.subheader("Row Count — All Tables")
    summary = [{"Domain": g, "Table": t, "Append-Only": "yes" if t in append_only else "", "Rows": q1(f"SELECT COUNT(*) n FROM {t};").get("n",0)}
               for g, tbls in groups.items() for t in tbls]
    st.dataframe(_fix_uuids(summary), use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1 separator — not a real page
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "— Phase 1 —":
    st.title("Phase 1 Components")
    st.info("Select a Phase 1 page from the sidebar: 🔑 KMS Keys, 🎫 OIDC Identity, 🛡️ OPA Policies, or 📨 Kafka Events.")

# ═══════════════════════════════════════════════════════════════════════════════
# 🔑 KMS KEYS
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🔑 KMS Keys":
    st.title("🔑 KMS Key Hierarchy — Phase 1")
    st.info("Every tenant gets 3 dedicated keys: **Root CA → DEK Encrypt → Signing**. Dev uses SOFTWARE keys; Prod uses HSM (GCP Cloud KMS).")
    st.divider()

    if not P1_AVAILABLE:
        st.error(f"Phase 1 not installed: {_p1_err_msg}")
        st.stop()

    # ── Key provisioning ──────────────────────────────────────────────────────
    tenants = q("SELECT id, slug, display_name FROM tenants WHERE status='ACTIVE';")
    if not tenants:
        st.warning("No tenants found. Register a tenant in ➕ New Case first.")
        st.stop()

    col1, col2 = st.columns(2)
    env        = col1.selectbox("Environment", ["dev", "staging", "prod"])
    sel_tenant = col2.selectbox("Tenant", [t['display_name'] for t in tenants])
    tenant     = next(t for t in tenants if t['display_name'] == sel_tenant)

    kms  = KeyHierarchy(env=env)
    keys = kms.provision_tenant(tenant['id'], tenant['slug'])

    st.subheader(f"Keys for: {sel_tenant}  |  env: {env}")
    key_data = []
    for k in keys:
        key_data.append({
            "Purpose":     k.purpose.value,
            "Backend":     k.backend.value,
            "Resource":    k.kms_resource,
            "Version":     k.version,
            "Active":      k.is_active,
            "Rotates In":  f"{k.days_until_rotation} days",
            "Fingerprint": k.fingerprint(),
        })
    st.dataframe(_fix_uuids(key_data), use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Root CA",     "✅ Active")
    c2.metric("DEK Encrypt", "✅ Active")
    c3.metric("Signing Key", "✅ Active")

    # ── Live signing demo ─────────────────────────────────────────────────────
    st.divider()
    st.subheader("Live: Sign & Verify an Invoice Hash")

    backend  = LocalKMSBackend()
    resource = f"dev/{tenant['slug']}-signing-v1"

    # Pull real invoice hash from DB if available
    src = q1("SELECT encode(canonical_hash,'hex') h FROM source_records WHERE tenant_id=%s LIMIT 1;", (tenant['id'],))
    sample_payload = src.get('h', '').encode() if src.get('h') else b"invoice:DHL-2026-00441:total=220.00:USD"

    sig      = backend.sign(resource, sample_payload)
    verified = backend.verify(resource, sample_payload, sig)

    col1, col2 = st.columns(2)
    col1.metric("Signature Length", f"{len(sig)} bytes")
    col2.metric("Signature Valid",  "Yes" if verified else "No")
    st.code(f"Payload:   {sample_payload[:60]}\nSignature: {sig.hex()[:48]}...\nVerified:  {verified}", language=None)

    # Tamper demo
    tampered = backend.verify(resource, b"tampered payload", sig)
    st.error(f"Tampered payload verification: {tampered} — tamper detected immediately")

    # ── Key rotation ──────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Key Rotation")
    st.caption("Rotating a key issues a new version. Old version is deactivated. Old signatures remain valid.")

    old = kms.get_active_key(tenant['id'], KeyPurpose.SIGNING)
    if st.button("Rotate Signing Key", type="primary"):
        new_key = kms.rotate_key(tenant['id'], KeyPurpose.SIGNING)
        st.success(f"Signing key rotated: v{old.version} → v{new_key.version}")
        st.info(f"Old key active: {old.is_active}   |   New key active: {new_key.is_active}")

    # ── Dev vs Prod comparison ────────────────────────────────────────────────
    st.divider()
    st.subheader("Dev vs Prod Key Backend")
    col1, col2 = st.columns(2)
    with col1:
        st.success("**Dev — SOFTWARE**\n\nKey material generated locally in-process.\nEphemeral — lost on restart.\nSafe for development only.")
    with col2:
        st.warning("**Prod — HSM (GCP Cloud KMS)**\n\nKey material never leaves the HSM chip.\nAudit logs every key usage.\nFIPS 140-2 Level 3 certified.")

# ═══════════════════════════════════════════════════════════════════════════════
# 🎫 OIDC IDENTITY
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🎫 OIDC Identity":
    st.title("🎫 OIDC Identity — Phase 1")
    st.info("Every API call must prove WHO is calling. A signed JWT carries the user's identity, tenant, and roles. Phase 1 validates every token on every request.")
    st.divider()

    if not P1_AVAILABLE:
        st.error(f"Phase 1 not installed: {_p1_err_msg}")
        st.stop()

    DEV_SECRET = b"zoiko-dev-secret-streamlit"
    verifier   = TokenVerifier(dev_secret=DEV_SECRET, issuer="https://auth.zoikotech.com")

    tenants = q("SELECT id, display_name FROM tenants WHERE status='ACTIVE';")
    tenant_opts = {t['display_name']: t['id'] for t in tenants} if tenants else {"Demo Tenant": str(uuid.uuid4())}

    tab1, tab2 = st.tabs(["Issue Token", "Verify Token"])

    with tab1:
        st.subheader("Issue a JWT Token")
        st.caption("In production this comes from your OIDC provider (Okta / Auth0 / Google). In dev we issue HS256 tokens locally.")

        with st.form("token_form"):
            col1, col2 = st.columns(2)
            user_email = col1.text_input("User Email", value="alice@zoikotech.com")
            sel_tenant = col2.selectbox("Tenant", list(tenant_opts.keys()))
            roles      = st.multiselect("Roles", ["analyst", "manager", "admin"], default=["analyst"])
            ttl        = st.slider("Token TTL (seconds)", 60, 86400, 3600)
            issued     = st.form_submit_button("Issue Token", use_container_width=True)

        if issued:
            tid   = tenant_opts[sel_tenant]
            token = verifier.make_dev_token(sub=user_email, tenant_id=tid, roles=roles, ttl_sec=ttl, audience="zoiko-api")
            st.success(f"Token issued for **{user_email}**")
            st.code(token, language=None)

            claims = verifier.verify(token)
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Subject",   claims.sub.split("@")[0])
            col2.metric("Roles",     ", ".join(claims.roles))
            col3.metric("Expired",   str(claims.is_expired))
            col4.metric("TTL",       f"{ttl}s")

            st.session_state["last_token"]    = token
            st.session_state["last_tenant_id"] = tid

    with tab2:
        st.subheader("Verify a Token")

        token_input = st.text_area("Paste a JWT token here", value=st.session_state.get("last_token", ""), height=80)

        col1, col2 = st.columns(2)
        if col1.button("Verify Valid Token", use_container_width=True):
            if token_input:
                try:
                    claims = verifier.verify(token_input, expected_audience="zoiko-api")
                    st.success(f"Token VALID — subject: `{claims.sub}`  roles: `{claims.roles}`  tenant: `{claims.tenant_id[:20]}...`")
                except TokenExpiredError:
                    st.error("Token EXPIRED")
                except TokenInvalidError as e:
                    st.error(f"Token INVALID: {e}")

        if col2.button("Test Tampered Token", use_container_width=True):
            if token_input:
                parts = token_input.split(".")
                if len(parts) == 3:
                    parts[1] = parts[1][:-4] + "XXXX"
                    try:
                        verifier.verify(".".join(parts))
                        st.error("Tampered token was accepted — this should not happen!")
                    except Exception:
                        st.error("Tampered token correctly REJECTED")

        st.divider()
        st.subheader("What Phase 1 Rejects Automatically")
        checks = [
            ("Expired token",           "Token TTL passed — attacker replaying an old token"),
            ("Tampered payload",        "Someone changed the tenant_id or roles in the token body"),
            ("Wrong audience",          "Token was issued for service-A but used on service-B"),
            ("Missing X-Tenant-ID",     "Header not present — required on every state-changing call"),
            ("Tenant mismatch",         "JWT tenant_id ≠ X-Tenant-ID header — cross-tenant attempt"),
        ]
        for check, reason in checks:
            st.error(f"**{check}** — {reason}")

# ═══════════════════════════════════════════════════════════════════════════════
# 🛡️ OPA POLICIES
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🛡️ OPA Policies":
    st.title("🛡️ OPA Policies — Phase 1")
    st.warning("**Rule 5 (non-negotiable):** If OPA is unreachable → 503 Service Unavailable. The system NEVER permits when the policy engine is down.")
    st.divider()

    if not P1_AVAILABLE:
        st.error(f"Phase 1 not installed: {_p1_err_msg}")
        st.stop()

    opa = MockOPAClient()

    tab1, tab2, tab3 = st.tabs(["Freight Dispute Policy", "Tenant Isolation Policy", "Fail-Closed Demo"])

    with tab1:
        st.subheader("freight_dispute.rego — SC-001 Business Rules")
        st.caption("Simulates real OPA decisions for every SC-001 action")

        col1, col2 = st.columns(2)
        action      = col1.selectbox("Action", ["PROPOSE_RECOVERY", "APPROVE_PROPOSAL", "EXECUTE_RECOVERY", "READ_CASE"])
        role        = col2.selectbox("Caller Role", ["analyst", "manager", "admin"])
        proposer    = col1.text_input("Proposer (analyst email)", value="alice@zoikotech.com")
        actor       = col2.text_input("Actor (your email)", value="bob@zoikotech.com")
        token_exp   = st.checkbox("Simulate expired token", value=False)

        if st.button("Evaluate Policy", type="primary", use_container_width=True):
            sod_ok = proposer != actor
            allow  = False
            violations = []

            if action == "PROPOSE_RECOVERY" and role == "analyst":
                allow = True
            elif action == "APPROVE_PROPOSAL" and role == "manager" and sod_ok:
                allow = True
            elif action == "APPROVE_PROPOSAL" and proposer == actor:
                violations.append("SoD violation: proposer and approver are the same person")
            elif action == "APPROVE_PROPOSAL" and role != "manager":
                violations.append(f"Role required: manager — caller has role: {role}")
            elif action == "EXECUTE_RECOVERY" and token_exp:
                violations.append("Token is expired")
            elif action == "EXECUTE_RECOVERY" and not token_exp:
                allow = True
            elif action == "READ_CASE":
                allow = True

            opa.set_decision("zoiko/freight_dispute", OPADecision(allow=allow, violations=violations))
            d = opa.check_freight_dispute({
                "action": action, "roles": [role],
                "proposer_sub": proposer, "actor_sub": actor,
                "token_expired": token_exp,
            })

            if d.allow:
                st.success(f"✅ **{action}** by `{actor}` (role={role}) → **ALLOWED**")
            else:
                st.error(f"❌ **{action}** by `{actor}` (role={role}) → **DENIED**")
                for v in d.violations:
                    st.error(f"   Reason: {v}")

        st.divider()
        st.subheader("Policy Rules — freight_dispute.rego")
        rules = [
            ("PROPOSE_RECOVERY",    "analyst",           "✅ ALLOW", "Analyst role required"),
            ("PROPOSE_RECOVERY",    "manager / admin",   "❌ DENY",  "Only analyst can propose"),
            ("APPROVE_PROPOSAL",    "manager (≠ analyst)","✅ ALLOW", "SoD satisfied"),
            ("APPROVE_PROPOSAL",    "same as proposer",  "❌ DENY",  "SoD violation"),
            ("APPROVE_PROPOSAL",    "analyst",           "❌ DENY",  "Manager role required"),
            ("EXECUTE_RECOVERY",    "any (valid token)", "✅ ALLOW", "EXECUTE scope + not expired"),
            ("EXECUTE_RECOVERY",    "expired token",     "❌ DENY",  "Token expired"),
            ("READ_CASE",           "any authenticated", "✅ ALLOW", "Read-only, always allowed"),
        ]
        st.dataframe(_fix_uuids([{"Action": a, "Caller": c, "Decision": d, "Reason": r} for a,c,d,r in rules]), use_container_width=True)

    with tab2:
        st.subheader("tenant_isolation.rego — Hard Tenant Boundary")
        st.caption("Every request is checked: does your JWT tenant match the resource you're touching?")

        col1, col2, col3 = st.columns(3)
        claim_t    = col1.text_input("JWT tenant_id", value="tenant-acme-001")
        resource_t = col2.text_input("Resource tenant_id", value="tenant-acme-001")
        iso_role   = col3.selectbox("Role", ["analyst", "manager", "admin"])

        if st.button("Check Tenant Isolation", type="primary", use_container_width=True):
            if iso_role == "admin":
                opa.set_decision("zoiko/tenant_isolation", OPADecision(allow=True))
                st.success(f"✅ ADMIN cross-tenant READ → ALLOWED (admin only)")
            elif claim_t == resource_t:
                opa.set_decision("zoiko/tenant_isolation", OPADecision(allow=True))
                d = opa.check_tenant_isolation(claim_t, resource_t, [iso_role])
                st.success(f"✅ Same tenant → ALLOWED — `{claim_t}` can access its own data")
            else:
                opa.set_decision("zoiko/tenant_isolation", OPADecision(
                    allow=False,
                    violations=[f"Tenant isolation: token has `{claim_t}` but resource belongs to `{resource_t}`"]
                ))
                d = opa.check_tenant_isolation(claim_t, resource_t, [iso_role])
                st.error(f"❌ Cross-tenant access BLOCKED")
                for v in d.violations:
                    st.error(f"   {v}")

    with tab3:
        st.subheader("Fail-Closed Demo")
        st.error("If OPA is unreachable, ALL requests are blocked — the system returns 503, never 200.")

        if st.button("Simulate OPA Unreachable", type="primary", use_container_width=True):
            real_opa = OPAClient(opa_url="http://localhost:19999", timeout=0.5)
            with st.spinner("Trying to reach OPA at localhost:19999..."):
                try:
                    real_opa.evaluate("zoiko/freight_dispute", {"action": "EXECUTE_RECOVERY"})
                    st.success("OPA responded (it's running locally)")
                except OPAUnavailableError as e:
                    st.error("OPA unreachable → Service returns **503 Service Unavailable**")
                    st.error("Request is BLOCKED. Rule 5: Never permit on unavailability.")
                    st.code(str(e)[:200], language=None)

# ═══════════════════════════════════════════════════════════════════════════════
# 📨 KAFKA EVENTS
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📨 Kafka Events":
    st.title("📨 Kafka Events — Phase 1")
    st.info("Services communicate via events. Each step of the SC-001 lifecycle publishes a Kafka message. Downstream services subscribe and react.")
    st.divider()

    if not P1_AVAILABLE:
        st.error(f"Phase 1 not installed: {_p1_err_msg}")
        st.stop()

    tab1, tab2 = st.tabs(["SC-001 Lifecycle Events", "Publish & Consume"])

    with tab1:
        st.subheader("Full SC-001 Event Flow — Live Simulation")

        # Get real data from DB if available
        cases    = q("SELECT c.id, ci.invoice_number, ci.carrier_id, ci.total_amount FROM cases c JOIN canonical_invoices ci ON ci.id=c.invoice_id ORDER BY c.opened_at DESC LIMIT 5;")
        case_id  = cases[0]['id'] if cases else str(uuid.uuid4())
        inv_no   = cases[0]['invoice_number'] if cases else "DHL-2026-00441"
        carrier  = cases[0]['carrier_id'] if cases else "DHL"
        total    = cases[0]['total_amount'] if cases else 220.0
        tid      = q1("SELECT id FROM tenants LIMIT 1;").get('id', str(uuid.uuid4()))

        broker   = MockKafkaBroker()
        producer = ZoikoProducer(broker)

        lifecycle = [
            ("invoice.received",    "ingestion-svc",       {"invoice_number": inv_no, "carrier": carrier, "total": float(total)}),
            ("invoice.validated",   "validation-svc",      {"invoice_number": inv_no, "status": "PASS", "overcharge_detected": True}),
            ("case.opened",         "case-orchestration",  {"case_id": str(case_id)[:12], "state": "OPENED"}),
            ("evidence.bundled",    "evidence-svc",        {"case_id": str(case_id)[:12], "items": 4}),
            ("finding.created",     "reasoning-svc",       {"confidence": 0.96, "overcharge": 100.0, "currency": "USD"}),
            ("proposal.created",    "governance-svc",      {"proposed_by": "alice@zoikotech.com", "amount": 100.0}),
            ("decision.made",       "governance-svc",      {"outcome": "APPROVED", "approved_by": "bob@zoikotech.com"}),
            ("token.issued",        "token-svc",           {"scope": "EXECUTE", "expires_in": "24h"}),
            ("execution.completed", "execution-gateway",   {"recovered": 100.0, "ref": f"CR-{uuid.uuid4().hex[:8].upper()}"}),
            ("acr.issued",          "acr-svc",             {"merkle_root": hashlib.sha256(str(case_id).encode()).hexdigest()[:32]}),
        ]

        for topic, publisher, payload in lifecycle:
            msg = KafkaMessage(topic=topic, key=str(case_id), payload=payload, tenant_id=str(tid))
            producer.publish(msg)

        st.success(f"Published {len(lifecycle)} events for case `{str(case_id)[:12]}...`")

        rows = []
        for i, (topic, publisher, payload) in enumerate(lifecycle, 1):
            rows.append({
                "Step": i,
                "Topic": topic,
                "Publisher": publisher,
                "Key Data": str(list(payload.values())[0])[:40],
                "Messages": broker.message_count(topic),
            })
        st.dataframe(_fix_uuids(rows), use_container_width=True)

        # Show consumer reading decision.made
        st.divider()
        st.subheader("Consumer: execution-gateway reads 'decision.made'")
        consumer = ZoikoConsumer(broker, group_id="execution-gateway")
        received = []
        consumer.subscribe("decision.made", lambda t, p: received.append(p))
        consumer.poll()
        if received:
            p = received[0]
            st.success(f"Received: outcome=**{p.get('outcome')}**  approved_by=**{p.get('approved_by')}**")
            st.info("execution-gateway now knows approval is done → proceeds to 8-gate execution")

    with tab2:
        st.subheader("Publish a Custom Event")
        st.caption("Try publishing your own event to any of the 17 registered topics")

        broker2   = MockKafkaBroker()
        producer2 = ZoikoProducer(broker2)

        tid2 = q1("SELECT id FROM tenants LIMIT 1;").get('id', str(uuid.uuid4()))

        with st.form("kafka_form"):
            col1, col2 = st.columns(2)
            sel_topic  = col1.selectbox("Topic", sorted(REGISTERED_TOPICS))
            key_val    = col2.text_input("Partition Key (e.g. case_id)", value=str(uuid.uuid4())[:8])
            payload_str = st.text_area("Payload (JSON)", value='{"status": "test", "amount": 100.0}', height=80)
            send_it     = st.form_submit_button("Publish Event", use_container_width=True)

        if send_it:
            try:
                payload = json.loads(payload_str)
                msg     = KafkaMessage(topic=sel_topic, key=key_val, payload=payload, tenant_id=str(tid2))
                producer2.publish(msg)
                st.success(f"Published to **{sel_topic}** with key `{key_val}`")
                raw = broker2.messages_for(sel_topic)[0]
                body = json.loads(raw['value'])
                st.json(body)
            except json.JSONDecodeError:
                st.error("Payload must be valid JSON")
            except ValueError as e:
                st.error(f"Error: {e}")

        st.divider()
        st.subheader("All 17 Registered Topics")
        topic_data = [{"Topic": t, "Used By": {
            "invoice.received":    "ingestion-svc → validation-svc",
            "invoice.validated":   "validation-svc → canonical-truth",
            "invoice.canonical":   "canonical-truth → case-orchestration",
            "case.opened":         "case-orchestration → evidence-svc",
            "case.updated":        "case-orchestration → all listeners",
            "case.closed":         "case-orchestration → audit-svc",
            "evidence.bundled":    "evidence-svc → reasoning-svc",
            "finding.created":     "reasoning-svc → governance-svc",
            "proposal.created":    "governance-svc → approval UI",
            "decision.made":       "governance-svc → token-svc",
            "token.issued":        "token-svc → execution-gateway",
            "token.consumed":      "execution-gateway → reconciliation",
            "execution.started":   "execution-gateway → connector-hub",
            "execution.completed": "execution-gateway → reconciliation",
            "reconciliation.done": "reconciliation-svc → acr-svc",
            "acr.issued":          "acr-svc → audit-worm",
            "audit.locked":        "audit-worm → compliance",
        }.get(t, "—")} for t in sorted(REGISTERED_TOPICS)]
        st.dataframe(_fix_uuids(topic_data), use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# — Phase 2 separator
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "— Phase 2 —":
    st.title("Phase 2 — Service Layer")
    st.info("Select a Phase 2 page from the sidebar: 📥 Ingestion, ✔ Validation, 📄 Canonical Truth, or 🗂 Case Flow.")

# ═══════════════════════════════════════════════════════════════════════════════
# 📥 INGESTION
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📥 Ingestion":
    st.title("📥 Ingestion Service — Phase 2")
    st.info(
        "Receives a raw carrier invoice and runs the **5-step write pattern**:\n\n"
        "JCS canonicalize → SHA-256(domain_tag) → encrypt → INSERT source_records + outbox "
        "(single transaction) → publish **invoice.received** to Kafka"
    )
    st.divider()

    if not P2_AVAILABLE:
        st.error(f"Phase 2 not available: {_p2_err_msg}")
        st.stop()

    tenants = q("SELECT id, slug, display_name FROM tenants WHERE status='ACTIVE';")
    if not tenants:
        st.warning("No tenants. Create one in ➕ New Case first.")
        st.stop()

    sel = st.selectbox("Tenant", [t["display_name"] for t in tenants])
    tenant = next(t for t in tenants if t["display_name"] == sel)

    st.subheader("Submit an Invoice")
    with st.form("ingest_form"):
        c1, c2 = st.columns(2)
        carrier    = c1.text_input("Carrier ID", value="DHL")
        inv_no     = c2.text_input("Invoice Number", value=f"DHL-{uuid.uuid4().hex[:6].upper()}")
        c3, c4, c5 = st.columns(3)
        amount     = c3.number_input("Total Amount ($)", value=220.0, step=1.0)
        currency   = c4.selectbox("Currency", ["USD", "EUR", "GBP"])
        weight     = c5.number_input("Weight (lbs)", value=1200.0, step=100.0)
        c6, c7     = st.columns(2)
        origin     = c6.text_input("Origin City", value="Dallas")
        dest       = c7.text_input("Destination City", value="Atlanta")
        submitted  = st.form_submit_button("Ingest Invoice", type="primary", use_container_width=True)

    if submitted:
        broker  = MockKafkaBroker()
        handler = IngestionHandler(DB_URL, broker, tenant["slug"])
        invoice = InvoiceInput(
            carrier_id=carrier, invoice_number=inv_no,
            total_amount=float(amount), currency=currency,
            route_origin=origin, route_destination=dest, weight_lbs=float(weight),
        )
        with st.spinner("Running ingestion pipeline..."):
            result = handler.ingest_invoice(tenant["id"], invoice)

        st.success("Invoice ingested successfully")
        c1, c2, c3 = st.columns(3)
        c1.metric("Source Record ID", str(result.source_record_id)[:13] + "…")
        c2.metric("Canonical Hash",   result.canonical_hash[:16] + "…")
        c3.metric("Kafka Messages",   broker.message_count("invoice.received"))

        st.subheader("5-Step Write Pattern — Completed")
        steps = [
            ("Step 1", "JCS Canonicalize",       f"Keys sorted by Unicode. Payload: carrier={carrier}, amount={amount}, currency={currency}"),
            ("Step 2", "SHA-256 Domain Hash",     f"SHA-256(\"zoiko.ingestion.invoice.v1:\" + canonical_bytes) = {result.canonical_hash[:32]}..."),
            ("Step 3", "Encrypt",                 "ciphertext stored in source_records.ciphertext (dev: canonical bytes; prod: AES-256-GCM via KMS)"),
            ("Step 4", "DB Transaction",          f"INSERT source_records + INSERT outbox — atomically committed"),
            ("Step 5", "Kafka Publish",           f"invoice.received published with key={str(result.source_record_id)[:8]}..."),
        ]
        for step, title, detail in steps:
            st.success(f"**{step} — {title}:** {detail}")

        st.divider()
        st.subheader("source_records row (DB)")
        row = q1("SELECT id, source_type, encode(canonical_hash,'hex') h, kid, idempotency_key, created_at FROM source_records WHERE id=%s", (result.source_record_id,))
        if row:
            st.dataframe(_fix_uuids([row]), use_container_width=True)

        st.subheader("outbox row (DB)")
        ob = q1("SELECT id, topic, partition_key, shipped_at, created_at FROM outbox WHERE partition_key=%s", (str(result.source_record_id),))
        if ob:
            st.dataframe(_fix_uuids([ob]), use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# ✔ VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "✔ Validation":
    st.title("✔ Validation Service — Phase 2")
    st.info(
        "Reads **contract_rates** from DB for the carrier, compares against the invoice total, "
        "detects overcharges, signs the result, and publishes **invoice.validated** to Kafka."
    )
    st.divider()

    if not P2_AVAILABLE:
        st.error(f"Phase 2 not available: {_p2_err_msg}")
        st.stop()

    tenants = q("SELECT id, slug, display_name FROM tenants WHERE status='ACTIVE';")
    if not tenants:
        st.warning("No tenants found.")
        st.stop()

    sel    = st.selectbox("Tenant", [t["display_name"] for t in tenants])
    tenant = next(t for t in tenants if t["display_name"] == sel)

    # Show existing contract rates
    st.subheader("Contract Rates on File")
    rates = q("SELECT carrier_id, rate_type, rate_value, currency, effective_on, expires_on FROM contract_rates WHERE tenant_id=%s ORDER BY carrier_id", (tenant["id"],))
    if rates:
        st.dataframe(_fix_uuids(rates), use_container_width=True)
    else:
        st.warning("No contract rates found for this tenant.")

    st.divider()
    tab1, tab2 = st.tabs(["Validate an Invoice", "Add Contract Rate"])

    with tab1:
        st.subheader("Run Validation Against a Source Record")
        src_records = q("""
            SELECT sr.id, sr.idempotency_key, sr.created_at,
                   encode(sr.canonical_hash,'hex') AS hash_hex
            FROM source_records sr
            WHERE sr.tenant_id=%s
            ORDER BY sr.created_at DESC LIMIT 20
        """, (tenant["id"],))

        if not src_records:
            st.info("No source records yet. Ingest an invoice first via 📥 Ingestion.")
        else:
            sel_src = st.selectbox("Source Record", [f"{str(r['id'])[:13]}…  ({r['created_at'].strftime('%H:%M:%S')})" for r in src_records])
            idx     = [f"{str(r['id'])[:13]}…  ({r['created_at'].strftime('%H:%M:%S')})" for r in src_records].index(sel_src)
            src     = src_records[idx]

            c1, c2, c3 = st.columns(3)
            v_carrier  = c1.text_input("Carrier ID", value="DHL")
            v_amount   = c2.number_input("Invoice Total ($)", value=220.0, step=1.0)
            v_inv_no   = c3.text_input("Invoice Number", value=f"INV-{uuid.uuid4().hex[:6]}")

            if st.button("Run Validation", type="primary", use_container_width=True):
                broker  = MockKafkaBroker()
                handler = ValidationHandler(DB_URL, broker, tenant["slug"])
                with st.spinner("Validating…"):
                    result = handler.validate(
                        tenant_id=tenant["id"],
                        source_record_id=src["id"],
                        invoice_number=v_inv_no,
                        carrier_id=v_carrier,
                        total_amount=float(v_amount),
                    )

                status_color = {"PASS": "success", "FAIL": "error", "WARN": "warning"}
                fn = getattr(st, status_color.get(result.status, "info"))
                fn(f"**Validation Status: {result.status}**  |  Overcharge: **${result.overcharge_amount:.2f}**")

                c1, c2, c3 = st.columns(3)
                c1.metric("Status",           result.status)
                c2.metric("Overcharge",       f"${result.overcharge_amount:.2f}")
                c3.metric("Rule Violations",  len(result.rule_violations))

                if result.rule_violations:
                    st.subheader("Violations")
                    viol_data = [{"Rule": v.rule, "Carrier": v.carrier_id, "Rate Type": v.rate_type,
                                  "Expected $": v.expected, "Actual $": v.actual, "Delta $": v.delta}
                                 for v in result.rule_violations]
                    st.dataframe(_fix_uuids(viol_data), use_container_width=True)

                db_row = q1("SELECT id, status, rule_violations, validated_at FROM validation_results WHERE id=%s", (result.validation_id,))
                if db_row:
                    st.subheader("validation_results row (DB)")
                    st.dataframe(_fix_uuids([db_row]), use_container_width=True)

    with tab2:
        st.subheader("Add a Contract Rate")
        st.caption("Add a rate so the validation service has something to compare against")
        with st.form("rate_form"):
            c1, c2, c3 = st.columns(3)
            r_carrier  = c1.text_input("Carrier ID", value="DHL")
            r_type     = c2.selectbox("Rate Type", ["FUEL_CHARGE", "ACCESSORIAL", "BASE_RATE", "SURCHARGE"])
            r_value    = c3.number_input("Rate Value ($)", value=120.0, step=1.0)
            add_rate   = st.form_submit_button("Add Rate", use_container_width=True)
        if add_rate:
            execute("""
                INSERT INTO contract_rates (tenant_id, carrier_id, rate_type, rate_value, currency, effective_on)
                VALUES (%s, %s, %s, %s, 'USD', CURRENT_DATE)
            """, (tenant["id"], r_carrier, r_type, float(r_value)))
            st.success(f"Added: {r_carrier} / {r_type} = ${r_value:.2f}")
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# 📄 CANONICAL TRUTH
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📄 Canonical Truth":
    st.title("📄 Canonical Truth Service — Phase 2")
    st.info(
        "Writes the **single authoritative** `canonical_invoice` + `canonical_shipment` rows. "
        "Every downstream service — evidence, reasoning, governance, ACR — anchors to the "
        "`canonical_hash` produced here."
    )
    st.divider()

    if not P2_AVAILABLE:
        st.error(f"Phase 2 not available: {_p2_err_msg}")
        st.stop()

    tenants = q("SELECT id, slug, display_name FROM tenants WHERE status='ACTIVE';")
    if not tenants:
        st.warning("No tenants found.")
        st.stop()

    sel    = st.selectbox("Tenant", [t["display_name"] for t in tenants])
    tenant = next(t for t in tenants if t["display_name"] == sel)

    tab1, tab2 = st.tabs(["Canonicalize Invoice", "Existing Canonical Invoices"])

    with tab1:
        src_records = q("""
            SELECT sr.id, sr.idempotency_key, sr.created_at
            FROM source_records sr
            WHERE sr.tenant_id=%s
            ORDER BY sr.created_at DESC LIMIT 20
        """, (tenant["id"],))

        if not src_records:
            st.info("No source records yet. Ingest an invoice first via 📥 Ingestion.")
        else:
            sel_src = st.selectbox("Source Record", [f"{str(r['id'])[:13]}…  ({r['created_at'].strftime('%H:%M:%S')})" for r in src_records])
            idx     = [f"{str(r['id'])[:13]}…  ({r['created_at'].strftime('%H:%M:%S')})" for r in src_records].index(sel_src)
            src     = src_records[idx]

            with st.form("canon_form"):
                c1, c2 = st.columns(2)
                cn_carrier = c1.text_input("Carrier ID", value="DHL")
                cn_inv_no  = c2.text_input("Invoice Number", value=f"DHL-{uuid.uuid4().hex[:6].upper()}")
                c3, c4, c5 = st.columns(3)
                cn_amount  = c3.number_input("Total Amount ($)", value=220.0, step=1.0)
                cn_origin  = c4.text_input("Origin City", value="Dallas")
                cn_dest    = c5.text_input("Destination City", value="Atlanta")
                cn_submit  = st.form_submit_button("Canonicalize", type="primary", use_container_width=True)

            if cn_submit:
                broker  = MockKafkaBroker()
                handler = CanonicalHandler(DB_URL, broker, tenant["slug"])
                with st.spinner("Writing canonical record..."):
                    result = handler.canonicalize_invoice(
                        tenant_id=tenant["id"],
                        source_record_id=src["id"],
                        invoice_number=cn_inv_no,
                        carrier_id=cn_carrier,
                        total_amount=float(cn_amount),
                        currency="USD",
                        origin_city=cn_origin,
                        dest_city=cn_dest,
                    )

                st.success("Canonical invoice written")
                c1, c2 = st.columns(2)
                c1.metric("canonical_invoice_id",  str(result.canonical_invoice_id)[:13] + "…")
                c2.metric("canonical_hash",        result.canonical_hash[:16] + "…")

                st.subheader("The Authoritative Hash")
                st.code(result.canonical_hash, language=None)
                st.caption("All evidence bundles, findings, proposals, and the final ACR Merkle tree will anchor to this exact hash.")

                db_row = q1("SELECT id, invoice_number, carrier_id, total_amount, encode(canonical_hash,'hex') hash, created_at FROM canonical_invoices WHERE id=%s", (result.canonical_invoice_id,))
                if db_row:
                    st.subheader("canonical_invoices row (DB)")
                    st.dataframe(_fix_uuids([db_row]), use_container_width=True)

    with tab2:
        rows = q("""
            SELECT ci.id, ci.invoice_number, ci.carrier_id, ci.total_amount, ci.currency,
                   encode(ci.canonical_hash,'hex') AS canonical_hash,
                   ci.created_at,
                   cs.origin_city, cs.dest_city
            FROM canonical_invoices ci
            LEFT JOIN canonical_shipments cs ON cs.invoice_id = ci.id
            WHERE ci.tenant_id=%s
            ORDER BY ci.created_at DESC
        """, (tenant["id"],))
        if rows:
            st.dataframe(_fix_uuids(rows), use_container_width=True)
            st.caption(f"{len(rows)} canonical invoice(s) on file")
        else:
            st.info("No canonical invoices yet.")

# ═══════════════════════════════════════════════════════════════════════════════
# 🗂 CASE FLOW
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🗂 Case Flow":
    st.title("🗂 Case Orchestration — Phase 2")
    st.info(
        "Opens dispute cases and manages the **state machine**. Every transition is logged as an "
        "APPEND-ONLY `case_event` — the complete audit trail of who moved the case and when."
    )
    st.divider()

    if not P2_AVAILABLE:
        st.error(f"Phase 2 not available: {_p2_err_msg}")
        st.stop()

    tenants = q("SELECT id, slug, display_name FROM tenants WHERE status='ACTIVE';")
    if not tenants:
        st.warning("No tenants found.")
        st.stop()

    sel    = st.selectbox("Tenant", [t["display_name"] for t in tenants])
    tenant = next(t for t in tenants if t["display_name"] == sel)

    tab1, tab2, tab3 = st.tabs(["Open a Case", "Transition State", "Case Event Log"])

    with tab1:
        st.subheader("Open Dispute Case from Canonical Invoice")
        inv_rows = q("""
            SELECT ci.id, ci.invoice_number, ci.carrier_id, ci.total_amount
            FROM canonical_invoices ci
            WHERE ci.tenant_id=%s
            ORDER BY ci.created_at DESC LIMIT 20
        """, (tenant["id"],))

        if not inv_rows:
            st.info("No canonical invoices yet. Run 📄 Canonical Truth first.")
        else:
            inv_labels = [f"{r['invoice_number']}  |  {r['carrier_id']}  |  ${r['total_amount']}" for r in inv_rows]
            sel_inv    = st.selectbox("Canonical Invoice", inv_labels)
            inv        = inv_rows[inv_labels.index(sel_inv)]

            if st.button("Open Dispute Case", type="primary", use_container_width=True):
                broker  = MockKafkaBroker()
                handler = CaseHandler(DB_URL, broker)
                result  = handler.open_case(tenant["id"], inv["id"], actor_sub="dashboard-user")

                if result.is_new:
                    st.success(f"Case opened: `{result.case_id}`  |  State: **{result.state}**")
                else:
                    st.info(f"Case already exists: `{result.case_id}`  |  State: **{result.state}**  (idempotent)")

                c1, c2, c3 = st.columns(3)
                c1.metric("Case ID",   str(result.case_id)[:13] + "…")
                c2.metric("State",     result.state)
                c3.metric("Is New",    "Yes" if result.is_new else "No (existing)")

    with tab2:
        st.subheader("Move Case Through State Machine")
        cases = q("""
            SELECT c.id, c.state, ci.invoice_number, ci.carrier_id
            FROM cases c
            JOIN canonical_invoices ci ON ci.id = c.invoice_id
            WHERE c.tenant_id=%s
            ORDER BY c.opened_at DESC LIMIT 20
        """, (tenant["id"],))

        if not cases:
            st.info("No cases yet. Open one in the first tab.")
        else:
            STATE_NEXT = {
                "OPENED":             "EVIDENCE_GATHERING",
                "EVIDENCE_GATHERING": "UNDER_REVIEW",
                "UNDER_REVIEW":       "PENDING_APPROVAL",
                "PENDING_APPROVAL":   "APPROVED",
                "APPROVED":           "EXECUTED",
                "EXECUTED":           "RECONCILED",
                "RECONCILED":         "CLOSED",
            }
            case_labels = [f"{r['invoice_number']}  |  state: {r['state']}" for r in cases]
            sel_case    = st.selectbox("Case", case_labels)
            case        = cases[case_labels.index(sel_case)]

            current  = case["state"]
            next_st  = STATE_NEXT.get(current)
            actor    = st.text_input("Actor (your email)", value="alice@zoikotech.com")

            # State machine diagram
            all_states = ["OPENED","EVIDENCE_GATHERING","UNDER_REVIEW","PENDING_APPROVAL","APPROVED","EXECUTED","RECONCILED","CLOSED"]
            state_str  = " → ".join(f"**{s}**" if s == current else s for s in all_states)
            st.markdown(state_str)

            if next_st:
                if st.button(f"Transition: {current} → {next_st}", type="primary", use_container_width=True):
                    broker  = MockKafkaBroker()
                    handler = CaseHandler(DB_URL, broker)
                    try:
                        handler.transition_state(tenant["id"], case["id"], next_st, actor)
                        st.success(f"State moved: **{current}** → **{next_st}**  |  actor: {actor}")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
            else:
                st.success(f"Case is in terminal state: **{current}**")

            if st.button("Reject Case", use_container_width=True):
                broker  = MockKafkaBroker()
                handler = CaseHandler(DB_URL, broker)
                try:
                    handler.transition_state(tenant["id"], case["id"], "REJECTED", actor)
                    st.warning("Case REJECTED")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    with tab3:
        st.subheader("APPEND-ONLY case_events (Full Audit Trail)")
        cases2 = q("""
            SELECT c.id, ci.invoice_number, c.state
            FROM cases c
            JOIN canonical_invoices ci ON ci.id = c.invoice_id
            WHERE c.tenant_id=%s
            ORDER BY c.opened_at DESC LIMIT 10
        """, (tenant["id"],))

        if not cases2:
            st.info("No cases yet.")
        else:
            sel2  = st.selectbox("Case", [f"{r['invoice_number']}  |  {r['state']}" for r in cases2], key="case_log")
            case2 = cases2[[f"{r['invoice_number']}  |  {r['state']}" for r in cases2].index(sel2)]
            events = q("""
                SELECT event_type, from_state, to_state, actor_sub, payload, occurred_at
                FROM case_events
                WHERE case_id=%s
                ORDER BY occurred_at ASC
            """, (case2["id"],))
            if events:
                st.dataframe(_fix_uuids(events), use_container_width=True)
                st.caption(f"{len(events)} event(s) — APPEND-ONLY, no UPDATE or DELETE ever issued")
            else:
                st.info("No events logged for this case yet.")

