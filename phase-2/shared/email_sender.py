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


def _send_sendgrid(to: str, subject: str, body: str) -> None:
    api_key = os.getenv("SENDGRID_API_KEY", "")
    if not api_key:
        raise RuntimeError("SENDGRID_API_KEY not set")
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        sg   = sendgrid.SendGridAPIClient(api_key=api_key)
        mail = Mail(from_email=EMAIL_FROM, to_emails=to, subject=subject, plain_text_content=body)
        resp = sg.send(mail)
        log.info("SendGrid response: %s", resp.status_code)
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
