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


def send_welcome_otp(to_email: str, full_name: str, role: str, otp: str, app_url: str = "") -> None:
    """Send OTP email when admin creates a user (no password set yet)."""
    subject = "ZoikoAI — You've been added! Set your password"
    login_url = app_url or APP_URL
    plain = (
        f"Hello {full_name},\n\n"
        f"Your admin has added you as {role.title()} in Zoiko AI Logistics.\n\n"
        f"Use the OTP below to create your password:\n\n"
        f"Your OTP: {otp}\n\n"
        f"This code is valid for 10 minutes.\n\n"
        f"After entering the OTP, you'll be able to set your password and log in.\n\n"
        f"Visit: {login_url}/forgot-password\n\n"
        f"Best regards,\nZoikoAI Logistics Team"
    )
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#1e3a8a;padding:20px 28px;border-radius:8px 8px 0 0">
        <span style="color:white;font-size:22px;font-weight:800">ZOIKO</span><span style="color:#60a5fa;font-size:22px;font-weight:800">AI</span>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;padding:28px">
        <h2 style="color:#1e293b;margin:0 0 8px">Welcome, {full_name}!</h2>
        <p style="color:#64748b;margin:0 0 16px">Your admin has added you as <strong>{role.title()}</strong> in Zoiko AI Logistics.</p>
        <p style="color:#475569;font-size:14px;margin:0 0 8px">Use the OTP below to create your password:</p>
        <div style="background:#f8fafc;border:2px dashed #3b82f6;border-radius:12px;padding:20px;text-align:center;margin:16px 0">
          <span style="font-size:36px;font-weight:900;letter-spacing:8px;color:#1d4ed8;font-family:monospace">{otp}</span>
        </div>
        <p style="color:#64748b;font-size:12px;margin:0 0 4px">This code is valid for <strong>10 minutes</strong>.</p>
        <p style="color:#64748b;font-size:12px;margin:0 0 20px">
          Visit <a href="{login_url}/forgot-password" style="color:#2563eb">{login_url}/forgot-password</a> to enter the OTP and set your password.
        </p>
        <hr style="border:none;border-top:1px solid #e2e8f0;margin:16px 0"/>
        <p style="color:#94a3b8;font-size:11px">If you didn't expect this invitation, please ignore this email.</p>
      </div>
    </div>"""
    _send_html(to_email, subject, plain, html)
    log.info("Welcome OTP sent to %s as %s (provider=%s)", to_email, role, EMAIL_PROVIDER)


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
