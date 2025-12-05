# app/comm/email.py
import os
import logging
from typing import Dict, Any, Optional

import requests
import html as html_module
from email.message import EmailMessage
import smtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape
from premailer import transform
from datetime import datetime

logger = logging.getLogger(__name__)

# --- Resend implementation (replaces SendGrid) ---
def send_email_resend(api_key: str,
                      from_email: str,
                      to_email: str,
                      subject: str,
                      body: str,
                      timeout: int = 15) -> Dict[str, Any]:
    """
    Send an email using Resend API (https://resend.com).
    Returns {"ok": True, "status_code": <int>, "id": <message_id>} on success,
    otherwise raises RuntimeError with actionable message.
    """
    if not api_key:
        raise ValueError("Resend API key required (RESEND_API_KEY).")
    if not from_email:
        raise ValueError("Sender address required (RESEND_FROM_EMAIL).")
    if not to_email:
        raise ValueError("Recipient address required.")

    # Enforce Resend testing-mode constraints when using onboarding sender.
    # If using Resend's onboarding/testing sender (`onboarding@resend.dev`),
    # Resend requires the recipient to be the account owner email (the one you signed up with).
    # To make that explicit, the code checks `RESEND_OWNER_EMAIL` env var when onboarding sender is used.
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": body,
    }

    # Testing / onboarding mode guard: if the developer is using Resend's onboarding sender,
    # require that `RESEND_OWNER_EMAIL` is set and matches the recipient email.
    onboarding_addr = "onboarding@resend.dev"
    if (from_email or "").strip().lower() == onboarding_addr:
        owner = os.getenv("RESEND_OWNER_EMAIL")
        if not owner:
            raise RuntimeError("Using Resend onboarding sender requires setting RESEND_OWNER_EMAIL to your account email.")
        if owner.strip().lower() != to_email.strip().lower():
            raise RuntimeError("Resend onboarding mode: recipient must be the account owner email set in RESEND_OWNER_EMAIL.")

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as e:
        logger.exception("Resend request failed")
        raise RuntimeError(f"Resend request failed: {e}") from e

    # Accept any 2xx as success
    if 200 <= r.status_code < 300:
        try:
            data = r.json()
        except Exception:
            data = {}
        return {"ok": True, "status_code": r.status_code, "id": data.get("id")}

    # Attempt to parse JSON response for detailed error
    try:
        resp = r.json()
    except Exception:
        resp = r.text
    logger.error("Resend API error: %s %s", r.status_code, resp)

    if r.status_code == 401:
        raise RuntimeError("Resend authentication failed (401). Check RESEND_API_KEY.")
    if r.status_code == 403:
        raise RuntimeError("Resend forbidden (403). Check API key permissions and sender verification.")

    raise RuntimeError(f"Resend API error {r.status_code}: {resp}")


# --- Optional simple SMTP fallback (kept for local testing) ---
def send_email_smtp(host: str,
                    port: int,
                    user: str,
                    password: str,
                    to_email: str,
                    subject: str,
                    body: str,
                    html_body: Optional[str] = None,
                    timeout: int = 30) -> Dict[str, Any]:
    """
    Send email using SMTP over SSL. Returns {"ok": True} or raises RuntimeError with actionable message.
    """
    if not all([host, port, user, password]):
        raise ValueError("SMTP host/port/user/password must be provided for SMTP backend.")
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_email
    msg["Subject"] = subject
    # Set plain-text content
    msg.set_content(body)
    # If HTML provided, add as alternative
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP_SSL(host, port, timeout=timeout) as s:
            s.login(user, password)
            s.send_message(msg)
        return {"ok": True}
    except smtplib.SMTPAuthenticationError as e:
        logger.exception("SMTP auth error")
        raise RuntimeError("SMTP authentication failed. Check username/password or app-password settings.") from e
    except smtplib.SMTPConnectError as e:
        logger.exception("SMTP connection error")
        raise RuntimeError("Unable to connect to SMTP server. Check host/port and network.") from e
    except Exception as e:
        logger.exception("SMTP send failed")
        raise RuntimeError(f"SMTP send failed: {e}") from e


def send_email(
    to_email: str,
    subject: str,
    body: str,
    body_html: Optional[str] = None,
    resend_api_key: Optional[str] = None,
    from_email: Optional[str] = None,
    smtp_host: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_pass: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Generic send wrapper: try Resend first (if API key provided), fall back to SMTP if Resend fails
    due to domain verification / 403 errors. Returns a dict including which backend was used:
      {"ok": True, "used": "resend"|"smtp", ...}

    Behavior:
    - If `resend_api_key` and `from_email` are provided, attempt Resend.
    - On RuntimeError from Resend that indicates verification or 403, attempt SMTP using provided
      SMTP args or environment variables `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`.
    - If SMTP not configured, re-raise the original Resend error.
    """
    # Resolve env defaults if args not provided
    resend_api_key = resend_api_key or os.getenv("RESEND_API_KEY")
    from_email = from_email or os.getenv("RESEND_FROM_EMAIL")

    smtp_host = smtp_host or os.getenv("SMTP_HOST")
    smtp_port = smtp_port or (int(os.getenv("SMTP_PORT")) if os.getenv("SMTP_PORT") else None)
    smtp_user = smtp_user or os.getenv("SMTP_USER")
    smtp_pass = smtp_pass or os.getenv("SMTP_PASS")

    # Try Resend first if available
    if resend_api_key and from_email:
        try:
            # Ensure we have an HTML body for Resend. Prefer Jinja2 template rendering with premailer inlining.
            if body_html:
                html_to_send = body_html
            else:
                try:
                    html_to_send = render_template_html(subject, body)
                except Exception:
                    html_to_send = format_email_html(subject, body)
            res = send_email_resend(api_key=resend_api_key,
                                    from_email=from_email,
                                    to_email=to_email,
                                    subject=subject,
                                    body=html_to_send,
                                    timeout=timeout)
            # mark backend used
            res["used"] = "resend"
            return res
        except Exception as e:
            msg = str(e).lower()
            logger.warning("Resend send failed: %s", e)
            # Detect verification/forbidden related errors and fall back to SMTP
            should_fallback = False
            if "403" in msg or "forbidden" in msg or "not verified" in msg or "verification" in msg:
                should_fallback = True
            # Also fallback when resend indicates onboarding mismatch
            if "onboarding" in msg and "owner" in msg:
                should_fallback = True

            if not should_fallback:
                # re-raise original exception for non-verification failures
                raise
            # attempt SMTP fallback below

    # SMTP fallback: require all SMTP params
    if smtp_host and smtp_port and smtp_user and smtp_pass:
        try:
            # For SMTP, send both plain text and an HTML alternative (if available)
            if body_html:
                html_to_send = body_html
            else:
                try:
                    html_to_send = render_template_html(subject, body)
                except Exception:
                    html_to_send = format_email_html(subject, body)
            smtp_resp = send_email_smtp(host=smtp_host,
                                       port=int(smtp_port),
                                       user=smtp_user,
                                       password=smtp_pass,
                                       to_email=to_email,
                                       subject=subject,
                                       body=body,
                                       html_body=html_to_send,
                                       timeout=timeout)
            smtp_resp["used"] = "smtp"
            return smtp_resp
        except Exception as smtp_e:
            logger.exception("SMTP fallback failed: %s", smtp_e)
            # Raise a combined error message for debugging
            raise RuntimeError(f"Both Resend and SMTP send failed. SMTP error: {smtp_e}") from smtp_e

    # If we reach here, Resend either wasn't configured or fallback not possible
    raise RuntimeError("Email sending failed: Resend not configured or failed, and SMTP fallback not available.")


def format_email_html(subject: str, plain_body: str) -> str:
    """
    Build a simple, clean HTML version of the plain text email body.
    Basic heuristics:
      - Lines beginning with 'Original clause:' or 'Proposed redline:' become bold headings.
      - Blank lines separate paragraphs.
      - Preserve indentation/formatting using <pre> for longer blocks.
    """
    if not plain_body:
        return f"<html><body><h2>{html_module.escape(subject)}</h2></body></html>"

    lines = plain_body.splitlines()
    parts = [f"<h2 style='font-family:Arial,Helvetica,sans-serif'>{html_module.escape(subject)}</h2>"]
    buffer = []

    def flush_buffer_as_paragraph():
        nonlocal buffer
        if not buffer:
            return
        text = "\n".join(buffer).strip()
        # If multi-line with long content, show in preformatted block
        if any(len(l) > 80 for l in buffer) or len(buffer) > 2:
            parts.append(f"<pre style='font-family:inherit;background:#f6f8fa;padding:10px;border-radius:6px'>{html_module.escape(text)}</pre>")
        else:
            parts.append(f"<p style='font-family:Arial,Helvetica,sans-serif'>{html_module.escape(text)}</p>")
        buffer = []

    for ln in lines:
        s = ln.strip()
        if not s:
            flush_buffer_as_paragraph()
            continue
        low = s.lower()
        if low.startswith("original clause:") or low.startswith("proposed redline:") or low.startswith("proposed redline"):
            # flush previous
            flush_buffer_as_paragraph()
            parts.append(f"<h4 style='font-family:Arial,Helvetica,sans-serif;margin-bottom:6px'>{html_module.escape(s)}</h4>")
            continue
        buffer.append(s)

    flush_buffer_as_paragraph()

    html = "<html><body style='line-height:1.4;color:#111'>" + "\n".join(parts) + "</body></html>"
    return html


def render_template_html(subject: str, plain_body: str) -> str:
    """
    Render the Jinja2 HTML template and inline CSS using premailer.
    Returns the final HTML string.
    """
    # Prepare blocks from plain text (similar heuristics as format_email_html)
    lines = (plain_body or "").splitlines()
    blocks = []
    buf = []

    def flush_paragraph():
        nonlocal buf
        if not buf:
            return
        text = "\n".join(buf).strip()
        # detect long block
        if any(len(l) > 80 for l in buf) or len(buf) > 3:
            blocks.append({"type": "pre", "text": text})
        else:
            blocks.append({"type": "para", "text": text})
        buf = []

    for ln in lines:
        s = ln.strip()
        if not s:
            flush_paragraph()
            continue
        low = s.lower()
        if low.startswith("original clause:"):
            flush_paragraph()
            blocks.append({"type": "heading", "text": s})
            continue
        if low.startswith("proposed redline"):
            flush_paragraph()
            # treat following lines as a redline block
            blocks.append({"type": "redline", "text": s})
            continue
        buf.append(s)

    flush_paragraph()

    # Render template
    tmpl_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(tmpl_dir), autoescape=select_autoescape(["html", "xml"]))
    tpl = env.get_template("email_template.html")
    rendered = tpl.render(subject=subject, blocks=blocks, ts=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), app_name="Contract Risk Analyzer")
    # Inline CSS for better email client compatibility
    try:
        inlined = transform(rendered)
        return inlined
    except Exception:
        return rendered
