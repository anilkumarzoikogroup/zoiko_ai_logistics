"""
Email sender — supports SendGrid, SMTP, or logging-only fallback.

Configure via .env:
  EMAIL_PROVIDER=sendgrid   → uses SENDGRID_API_KEY
  EMAIL_PROVIDER=smtp       → uses SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
  EMAIL_PROVIDER=none       → logs token to console (dev default)
"""
from __future__ import annotations
import os
import logging

log = logging.getLogger("zoiko.email")

EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "none").lower().strip()
EMAIL_FROM     = os.getenv("EMAIL_FROM", "noreply@zoikotech.com")
APP_URL        = os.getenv("APP_URL", "http://localhost:5173")


def send_password_reset(to_email: str, raw_token: str, expires_at: str) -> None:
    link = f"{APP_URL}/login?flow=recovery&token={raw_token}"
    subject = "Reset your Zoiko password"
    body = f"""Hello,

You requested a password reset for your Zoiko account.

Click the link below to reset your password (expires {expires_at}):
{link}

If you did not request this, ignore this email.

— Zoiko AI Logistics
"""
    _send(to_email, subject, body, link)
    log.info("Password reset email sent to %s (provider=%s)", to_email, EMAIL_PROVIDER)


def send_invitation(to_email: str, invited_by: str, role: str, raw_token: str, expires_at: str) -> None:
    link = f"{APP_URL}/login?flow=invite&token={raw_token}"
    subject = f"You're invited to join Zoiko as {role.title()}"
    body = f"""Hello,

{invited_by} has invited you to join Zoiko AI Logistics as {role.title()}.

Click the link below to accept your invitation and set your password (expires {expires_at}):
{link}

— Zoiko AI Logistics
"""
    _send(to_email, subject, body, link)
    log.info("Invitation email sent to %s as %s (provider=%s)", to_email, role, EMAIL_PROVIDER)


def send_governance_notification(to_email: str, to_name: str, event: str,
                                 case_id: str, actor: str, amount: float,
                                 currency: str, app_url: str = "") -> None:
    """Notify manager (on proposal) or analyst (on decision) about governance events."""
    sym = "Rs." if currency == "INR" else ("$" if currency == "USD" else currency + " ")
    if event == "proposal":
        subject = f"Action Required: Recovery Proposal — Case {case_id[:8].upper()}"
        action_text = f"{actor} proposed a recovery of {sym}{amount:,.0f} {currency}."
        cta = "Review and approve or reject the proposal."
        cta_url = f"{app_url}/manager"
        cta_label = "Go to Manager Approval"
    else:
        subject = f"Recovery Decision — Case {case_id[:8].upper()}"
        action_text = f"Your proposal of {sym}{amount:,.0f} {currency} has been {'approved' if event == 'approved' else 'rejected'} by {actor}."
        cta = "View the case timeline for full details."
        cta_url = f"{app_url}/cases"
        cta_label = "View Cases"

    plain = f"Hello {to_name},\n\n{action_text}\n{cta}\n\n{cta_url}\n\n— Zoiko AI Logistics"
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px">
      <div style="background:#1e3a8a;padding:16px 24px;border-radius:8px 8px 0 0">
        <span style="color:white;font-weight:800;font-size:18px">ZOIKO</span><span style="color:#60a5fa;font-weight:800;font-size:18px">AI</span>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;padding:24px">
        <h3 style="color:#1e293b;margin:0 0 12px">Hello {to_name},</h3>
        <p style="color:#475569">{action_text}</p>
        <p style="color:#64748b;font-size:13px">{cta}</p>
        <a href="{cta_url}" style="display:inline-block;margin-top:16px;background:#2563eb;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:700;font-size:13px">{cta_label}</a>
        <p style="margin-top:20px;color:#94a3b8;font-size:11px">Case: {case_id}</p>
      </div>
    </div>"""
    _send_html(to_email, subject, plain, html)
    log.info("Governance notification sent to %s for case %s (event=%s)", to_email, case_id, event)


def send_new_signup_alert(full_name: str, work_email: str, company_name: str, use_case: str = "") -> None:
    """Alert admin when a new workspace access request is submitted."""
    admin_email = os.getenv("ADMIN_EMAIL", "admin@zoikotech.com")
    subject = f"New Signup Request — {company_name}"
    plain = f"New workspace request:\n\nName: {full_name}\nEmail: {work_email}\nCompany: {company_name}\nUse case: {use_case}\n\nLogin to Admin panel to approve."
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px">
      <div style="background:#1e3a8a;padding:16px 24px;border-radius:8px 8px 0 0">
        <span style="color:white;font-weight:800;font-size:18px">ZOIKO</span><span style="color:#60a5fa;font-weight:800;font-size:18px">AI</span>
        <span style="color:#94a3b8;font-size:11px;margin-left:10px">New Signup Alert</span>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;padding:24px">
        <h3 style="color:#1e293b;margin:0 0 16px">New Workspace Request</h3>
        <table style="width:100%;border-collapse:collapse">
          <tr><td style="padding:6px 0;color:#64748b;width:120px">Name</td><td style="font-weight:600">{full_name}</td></tr>
          <tr><td style="padding:6px 0;color:#64748b">Email</td><td>{work_email}</td></tr>
          <tr><td style="padding:6px 0;color:#64748b">Company</td><td style="font-weight:600">{company_name}</td></tr>
          <tr><td style="padding:6px 0;color:#64748b">Use Case</td><td>{use_case or "—"}</td></tr>
        </table>
        <p style="margin:16px 0 0;color:#64748b;font-size:13px">Login to the Admin panel to approve or reject this request.</p>
      </div>
    </div>"""
    _send_html(admin_email, subject, plain, html)
    log.info("Signup alert sent to admin for %s (%s)", company_name, work_email)


def send_welcome_email(to_email: str, full_name: str, role: str, password: str, login_url: str, invited_by: str = "") -> None:
    """Send welcome email to newly created user with their login credentials."""
    subject = "Welcome to Zoiko AI Logistics — Your Account is Ready"
    plain = f"Hello {full_name},\n\nYour account is ready.\nLogin: {login_url}\nEmail: {to_email}\nPassword: {password}\nRole: {role.title()}\n\nPlease change your password after first login.\n\n— Zoiko AI Logistics"
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#1e3a8a;padding:20px 28px;border-radius:8px 8px 0 0">
        <span style="color:white;font-size:22px;font-weight:800">ZOIKO</span><span style="color:#60a5fa;font-size:22px;font-weight:800">AI</span>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;padding:28px">
        <h2 style="color:#1e293b">Welcome, {full_name}!</h2>
        <p style="color:#64748b">Your Zoiko AI Logistics account has been created.</p>
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin:20px 0">
          <p style="margin:6px 0"><strong>Login URL:</strong> <a href="{login_url}">{login_url}</a></p>
          <p style="margin:6px 0"><strong>Email:</strong> {to_email}</p>
          <p style="margin:6px 0"><strong>Password:</strong> <code style="background:#e2e8f0;padding:2px 6px;border-radius:4px">{password}</code></p>
          <p style="margin:6px 0"><strong>Role:</strong> {role.title()}</p>
        </div>
        <p style="color:#dc2626;font-size:12px">Please change your password after first login.</p>
        {"<p style='color:#64748b;font-size:12px'>Invited by: " + invited_by + "</p>" if invited_by else ""}
      </div>
    </div>"""
    _send_html(to_email, subject, plain, html)
    log.info("Welcome email sent to %s as %s (provider=%s)", to_email, role, EMAIL_PROVIDER)


def send_dispute_letter(
    to_email: str,
    carrier: str,
    case_id: str,
    letter_text: str,
    overcharge: float,
    currency: str,
    from_name: str = "Zoiko AI Logistics",
) -> None:
    """Send the AI-generated dispute letter to the carrier's email."""
    subject = f"Freight Overcharge Dispute — Case {case_id[:8].upper()} | {carrier}"
    sym = "₹" if currency == "INR" else ("$" if currency == "USD" else currency + " ")

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;color:#1e293b">
      <div style="background:#1e3a8a;padding:20px 28px;border-radius:8px 8px 0 0">
        <span style="color:white;font-size:22px;font-weight:800">ZOIKO</span>
        <span style="color:#60a5fa;font-size:22px;font-weight:800">AI</span>
        <span style="color:#94a3b8;font-size:12px;margin-left:12px">Freight Audit Platform</span>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;padding:28px">
        <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:12px 16px;margin-bottom:20px">
          <strong style="color:#dc2626">Formal Dispute Notice</strong>
          <span style="color:#64748b;font-size:12px;margin-left:8px">Case: {case_id[:8].upper()} | Overcharge: {sym}{overcharge:,.2f} {currency}</span>
        </div>
        <pre style="font-family:Arial,sans-serif;white-space:pre-wrap;font-size:13px;line-height:1.7;color:#1e293b">{letter_text}</pre>
        <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0"/>
        <p style="font-size:11px;color:#94a3b8">
          This letter was generated by <strong>Zoiko AI Logistics</strong> freight audit platform.
          Case reference: <code>{case_id}</code> | Cryptographic ACR available on request.
        </p>
      </div>
    </div>
    """

    _send_html(to_email, subject, letter_text, html)
    log.info("Dispute letter sent to %s for case %s (provider=%s)", to_email, case_id, EMAIL_PROVIDER)


def send_recovery_executed(
    to_email: str, to_name: str,
    case_id: str, carrier: str,
    amount: float, currency: str,
    envelope_id: str,
) -> None:
    """Notify managers when a claim settlement has been dispatched through all 8 gates."""
    sym = "₹" if currency == "INR" else ("$" if currency == "USD" else currency + " ")
    subject = f"Claim Settlement Dispatched — {sym}{amount:,.2f} {currency} | Case {case_id[:8].upper()}"
    plain = (
        f"Hello {to_name},\n\n"
        f"A claim settlement of {sym}{amount:,.2f} {currency} has been dispatched for carrier {carrier}.\n\n"
        f"  Carrier:     {carrier}\n"
        f"  Amount:      {sym}{amount:,.2f} {currency}\n"
        f"  Envelope ID: {envelope_id}\n"
        f"  Case ID:     {case_id}\n\n"
        f"All 8 execution gates passed. An expected recovery record has been automatically created.\n"
        f"You will receive a notification once the carrier confirms payment.\n\n"
        f"— Zoiko AI Logistics"
    )
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px">
      <div style="background:#1e3a8a;padding:16px 24px;border-radius:8px 8px 0 0">
        <span style="color:white;font-weight:800;font-size:18px">ZOIKO</span><span style="color:#60a5fa;font-weight:800;font-size:18px">AI</span>
        <span style="color:#94a3b8;font-size:11px;margin-left:10px">Claim Settlement Dispatched</span>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;padding:24px">
        <h3 style="color:#059669;margin:0 0 12px">✓ Claim Settlement Dispatched</h3>
        <p style="color:#475569">Hello {to_name}, a claim settlement has been dispatched for <strong>{carrier}</strong>.</p>
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin:16px 0">
          <table style="width:100%;border-collapse:collapse">
            <tr><td style="color:#64748b;padding:4px 0;width:140px">Carrier</td><td style="font-weight:700">{carrier}</td></tr>
            <tr><td style="color:#64748b;padding:4px 0">Settlement Amount</td><td style="font-weight:800;color:#059669;font-size:16px">{sym}{amount:,.2f} {currency}</td></tr>
            <tr><td style="color:#64748b;padding:4px 0">Envelope ID</td><td style="font-family:monospace;font-size:11px">{envelope_id}</td></tr>
          </table>
        </div>
        <a href="{APP_URL}/claims/{case_id}" style="display:inline-block;background:#059669;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:700;font-size:13px">View Claim</a>
        <p style="margin-top:16px;color:#94a3b8;font-size:11px">Case: {case_id}</p>
      </div>
    </div>"""
    _send_html(to_email, subject, plain, html)
    log.info("Recovery executed email sent to %s for case %s amount=%s %s", to_email, case_id, amount, currency)


def send_payment_confirmed(
    to_email: str, to_name: str,
    case_id: str, carrier: str,
    amount: float, currency: str,
    payment_ref: str,
) -> None:
    """Notify finance manager when carrier has confirmed actual payment receipt."""
    sym = "₹" if currency == "INR" else ("$" if currency == "USD" else currency + " ")
    subject = f"Payment Confirmed — {sym}{amount:,.2f} {currency} Received | Case {case_id[:8].upper()}"
    plain = (
        f"Hello {to_name},\n\n"
        f"Payment of {sym}{amount:,.2f} {currency} from {carrier} has been confirmed.\n\n"
        f"  Carrier:       {carrier}\n"
        f"  Amount:        {sym}{amount:,.2f} {currency}\n"
        f"  Payment Ref:   {payment_ref}\n"
        f"  Case ID:       {case_id}\n\n"
        f"Recovery is complete. Generate the final Recovery Proof from the case page.\n\n"
        f"— Zoiko AI Logistics"
    )
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px">
      <div style="background:#1e3a8a;padding:16px 24px;border-radius:8px 8px 0 0">
        <span style="color:white;font-weight:800;font-size:18px">ZOIKO</span><span style="color:#60a5fa;font-weight:800;font-size:18px">AI</span>
        <span style="color:#94a3b8;font-size:11px;margin-left:10px">Payment Confirmed</span>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;padding:24px">
        <h3 style="color:#059669;margin:0 0 12px">💰 Payment Confirmed — Recovery Complete</h3>
        <p style="color:#475569">Hello {to_name}, payment has been confirmed from <strong>{carrier}</strong>.</p>
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin:16px 0">
          <table style="width:100%;border-collapse:collapse">
            <tr><td style="color:#64748b;padding:4px 0;width:140px">Carrier</td><td style="font-weight:700">{carrier}</td></tr>
            <tr><td style="color:#64748b;padding:4px 0">Amount Received</td><td style="font-weight:800;color:#059669;font-size:18px">{sym}{amount:,.2f} {currency}</td></tr>
            <tr><td style="color:#64748b;padding:4px 0">Payment Reference</td><td style="font-family:monospace">{payment_ref}</td></tr>
          </table>
        </div>
        <a href="{APP_URL}/claims/{case_id}" style="display:inline-block;background:#059669;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:700;font-size:13px">Generate Recovery Proof</a>
        <p style="margin-top:16px;color:#94a3b8;font-size:11px">Case: {case_id}</p>
      </div>
    </div>"""
    _send_html(to_email, subject, plain, html)
    log.info("Payment confirmed email sent to %s for case %s ref=%s", to_email, case_id, payment_ref)


def send_claim_submitted(
    to_email: str, to_name: str,
    case_id: str, carrier: str,
    claim_type: str, amount: float, currency: str,
    evidence_count: int,
) -> None:
    """Notify reviewer when a manual claim is submitted."""
    sym = "₹" if currency == "INR" else ("$" if currency == "USD" else currency + " ")
    subject = f"New Carrier Claim — {carrier} | {sym}{amount:,.0f} {currency}"
    plain = (
        f"Hello {to_name},\n\n"
        f"A new carrier claim has been submitted and requires review.\n\n"
        f"  Carrier:        {carrier}\n"
        f"  Claim Type:     {claim_type}\n"
        f"  Claimed Amount: {sym}{amount:,.2f} {currency}\n"
        f"  Evidence Items: {evidence_count}\n"
        f"  Case ID:        {case_id}\n\n"
        f"— Zoiko AI Logistics"
    )
    ev_style = "color:#059669" if evidence_count > 0 else "color:#dc2626"
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px">
      <div style="background:#1e3a8a;padding:16px 24px;border-radius:8px 8px 0 0">
        <span style="color:white;font-weight:800;font-size:18px">ZOIKO</span><span style="color:#60a5fa;font-weight:800;font-size:18px">AI</span>
        <span style="color:#94a3b8;font-size:11px;margin-left:10px">New Carrier Claim</span>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;padding:24px">
        <h3 style="color:#1e293b;margin:0 0 12px">New Carrier Claim Requires Review</h3>
        <p style="color:#475569">Hello {to_name}, a new carrier claim has been submitted.</p>
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin:16px 0">
          <table style="width:100%;border-collapse:collapse">
            <tr><td style="color:#64748b;padding:4px 0;width:140px">Carrier</td><td style="font-weight:700">{carrier}</td></tr>
            <tr><td style="color:#64748b;padding:4px 0">Claim Type</td><td style="font-weight:600">{claim_type}</td></tr>
            <tr><td style="color:#64748b;padding:4px 0">Claimed Amount</td><td style="font-weight:800;color:#1e293b;font-size:16px">{sym}{amount:,.2f} {currency}</td></tr>
            <tr><td style="color:#64748b;padding:4px 0">Evidence Items</td><td style="font-weight:700;{ev_style}">{evidence_count} item(s)</td></tr>
          </table>
        </div>
        <a href="{APP_URL}/claims/{case_id}" style="display:inline-block;background:#2563eb;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:700;font-size:13px">Review Claim</a>
        <p style="margin-top:16px;color:#94a3b8;font-size:11px">Case: {case_id}</p>
      </div>
    </div>"""
    _send_html(to_email, subject, plain, html)
    log.info("Claim submitted email sent to %s for case %s", to_email, case_id)


def send_carrier_negotiation_update(
    to_email: str, to_name: str,
    case_id: str, carrier: str,
    action: str, new_status: str,
    approved_amount: float | None, currency: str,
    round_num: int, note: str = "",
) -> None:
    """Notify internal team when carrier negotiation status changes (counter, accept, reject)."""
    sym = "₹" if currency == "INR" else ("$" if currency == "USD" else currency + " ")
    action_labels = {
        "COUNTER":          "Counter-offered",
        "ACCEPT":           "Accepted in Full",
        "PARTIALLY_ACCEPT": "Partially Accepted",
        "REJECT":           "Rejected",
    }
    action_label = action_labels.get(action, action.replace("_", " ").title())
    subject = f"Carrier Negotiation — Round {round_num} | {carrier} | Case {case_id[:8].upper()}"

    amount_line = f"\n  Agreed Amount:   {sym}{approved_amount:,.2f} {currency}" if approved_amount is not None and action != "REJECT" else ""
    note_line   = f"\n  Note:            {note}" if note else ""
    plain = (
        f"Hello {to_name},\n\n"
        f"Carrier negotiation round {round_num} has been recorded.\n\n"
        f"  Carrier:         {carrier}\n"
        f"  Action:          {action_label}\n"
        f"  New Status:      {new_status.replace('_', ' ').title()}\n"
        f"  Round:           {round_num}"
        f"{amount_line}"
        f"{note_line}\n\n"
        f"Case ID: {case_id}\n\n— Zoiko AI Logistics"
    )

    status_colors = {
        "COUNTERED":          "#6366f1",
        "ACCEPTED":           "#059669",
        "PARTIALLY_ACCEPTED": "#d97706",
        "REJECTED":           "#dc2626",
    }
    color = status_colors.get(new_status, "#475569")
    amount_row = (
        f'<tr><td style="color:#64748b;padding:4px 0;width:140px">Agreed Amount</td>'
        f'<td style="font-weight:800;color:{color};font-size:16px">{sym}{approved_amount:,.2f} {currency}</td></tr>'
    ) if approved_amount is not None and action != "REJECT" else ""
    note_html = (
        f'<p style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;'
        f'padding:10px 12px;color:#475569;font-size:12px;font-style:italic;margin:12px 0">"{note}"</p>'
    ) if note else ""

    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px">
      <div style="background:#1e3a8a;padding:16px 24px;border-radius:8px 8px 0 0">
        <span style="color:white;font-weight:800;font-size:18px">ZOIKO</span><span style="color:#60a5fa;font-weight:800;font-size:18px">AI</span>
        <span style="color:#94a3b8;font-size:11px;margin-left:10px">Carrier Negotiation Update</span>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;padding:24px">
        <h3 style="color:#1e293b;margin:0 0 12px">Round {round_num} — <span style="color:{color}">{action_label}</span></h3>
        <p style="color:#475569">Hello {to_name}, carrier <strong>{carrier}</strong> {action_label.lower()} on round {round_num}.</p>
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin:16px 0">
          <table style="width:100%;border-collapse:collapse">
            <tr><td style="color:#64748b;padding:4px 0;width:140px">Carrier</td><td style="font-weight:700">{carrier}</td></tr>
            <tr><td style="color:#64748b;padding:4px 0">Status</td>
              <td><span style="font-weight:800;color:{color}">{new_status.replace("_", " ").title()}</span></td></tr>
            <tr><td style="color:#64748b;padding:4px 0">Round</td><td style="font-weight:600">{round_num}</td></tr>
            {amount_row}
          </table>
        </div>
        {note_html}
        <a href="{APP_URL}/claims/{case_id}" style="display:inline-block;background:#2563eb;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:700;font-size:13px">View Claim</a>
        <p style="margin-top:16px;color:#94a3b8;font-size:11px">Case: {case_id}</p>
      </div>
    </div>"""
    _send_html(to_email, subject, plain, html)
    log.info("Carrier negotiation email sent to %s case=%s round=%d action=%s", to_email, case_id, round_num, action)


def _log_notification(db_url: str, tenant_id: str, event_type: str,
                      recipient_email: str, recipient_role: str,
                      case_id: str | None, subject: str,
                      amount: float | None, currency: str | None,
                      status: str = "SENT", error: str | None = None) -> None:
    """Write to email_notification_log — best effort, never raises."""
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO email_notification_log
                    (tenant_id, event_type, recipient_email, recipient_role,
                     case_id, subject, amount, currency, status, error_detail, sent_at)
                VALUES (%s::uuid, %s, %s, %s,
                        %s::uuid, %s, %s, %s, %s, %s, NOW())
            """, (
                tenant_id, event_type, recipient_email, recipient_role,
                case_id, subject, amount, currency, status, error,
            ))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _send(to: str, subject: str, body: str, link: str) -> None:
    if EMAIL_PROVIDER == "sendgrid":
        _send_sendgrid(to, subject, body)
    elif EMAIL_PROVIDER == "smtp":
        _send_smtp(to, subject, body)
    else:
        # Dev fallback — log the link so admin can copy it manually
        log.info(
            "EMAIL (provider=none) | To: %s | Subject: %s | Link: %s",
            to, subject, link,
        )
        print(f"\n{'='*60}\nEMAIL TO: {to}\nSUBJECT: {subject}\nLINK: {link}\n{'='*60}\n")


def _send_html(to: str, subject: str, plain: str, html: str) -> None:
    """Send email with HTML body (falls back to plain text)."""
    if EMAIL_PROVIDER == "sendgrid":
        _send_sendgrid(to, subject, plain, html)
    elif EMAIL_PROVIDER == "smtp":
        _send_smtp(to, subject, plain)
    else:
        print(f"\n{'='*60}\nEMAIL TO: {to}\nSUBJECT: {subject}\n{'='*60}\n{plain}\n")


def _send_sendgrid(to: str, subject: str, body: str, html: str = "") -> None:
    api_key  = os.getenv("SENDGRID_API_KEY", "")
    sandbox  = os.getenv("SENDGRID_SANDBOX", "true").lower() == "true"
    if not api_key:
        raise RuntimeError("SENDGRID_API_KEY not set")
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, MailSettings, SandBoxMode
        sg   = sendgrid.SendGridAPIClient(api_key=api_key)
        mail = Mail(
            from_email        = EMAIL_FROM,
            to_emails         = to,
            subject           = subject,
            plain_text_content= body,
            html_content      = html or body,
        )
        # Sandbox mode — email is validated but NOT delivered (safe for testing)
        if sandbox:
            mail.mail_settings = MailSettings()
            mail.mail_settings.sandbox_mode = SandBoxMode(enable=True)
            log.info("SendGrid SANDBOX mode — email validated but not delivered")
        resp = sg.send(mail)
        log.info("SendGrid response: %s (sandbox=%s)", resp.status_code, sandbox)
    except ImportError:
        raise RuntimeError("sendgrid package not installed. Run: pip install sendgrid")


def _send_smtp(to: str, subject: str, body: str) -> None:
    import smtplib
    from email.mime.text import MIMEText
    host     = os.getenv("SMTP_HOST", "")
    port     = int(os.getenv("SMTP_PORT", "587"))
    user     = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    if not host:
        raise RuntimeError("SMTP_HOST not set")
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = to
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        if user:
            server.login(user, password)
        server.sendmail(EMAIL_FROM, [to], msg.as_string())
