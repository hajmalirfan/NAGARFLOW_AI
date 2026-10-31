"""Outgoing email.

In production this sends through SMTP. When no SMTP server is configured
it falls back to a development mode that writes each message to
``backend/dev_emails/`` and logs it, so the password reset flow can be
exercised locally without a mail server. The fallback is deliberately
loud: nothing silently pretends an email was delivered.
"""

import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

from app.core.clock import utcnow
from app.core.config import settings

logger = logging.getLogger(__name__)

DEV_EMAIL_DIR = Path(__file__).resolve().parents[2] / "dev_emails"


def send_email(to: str, subject: str, body: str) -> None:
    """Send one plain-text email, or write it to disk in development."""
    if not settings.smtp_host:
        _write_development_email(to, subject, body)
        return

    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        # The caller must not be able to tell, from the response, whether
        # delivery worked, because that would reveal whether the address
        # is registered. Log the failure for the operator instead.
        logger.exception("Could not send email to %s", to)
        return

    logger.info("Sent %r to %s", subject, to)


def _write_development_email(to: str, subject: str, body: str) -> None:
    DEV_EMAIL_DIR.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().strftime("%Y%m%dT%H%M%S%f")
    path = DEV_EMAIL_DIR / f"{stamp}-{to.replace('@', '-at-')}.txt"
    path.write_text(
        f"To: {to}\nFrom: {settings.email_from}\nSubject: {subject}\n\n{body}\n",
        encoding="utf-8",
    )
    logger.warning(
        "SMTP_HOST is not set, so no real email was sent. "
        "The message for %s was written to %s",
        to,
        path,
    )
