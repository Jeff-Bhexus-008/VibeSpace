"""Email delivery for verification and password reset.

When SMTP is not configured the message is not sent — the action link is logged
(and returned in development) so a self-hosted setup can be completed without a
mail provider. In production, configure SMTP or these flows stay unusable.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("vibespace.email")


def build_action_link(path: str, token: str) -> str:
    return f"{settings.public_app_url.rstrip('/')}{path}?token={token}"


def send_email(to: str, subject: str, html: str, text: str | None = None) -> bool:
    if not settings.email_delivery_configured:
        logger.warning(
            "SMTP is not configured — '%s' for %s was not delivered. Set SMTP_* variables to enable delivery.",
            subject,
            to,
        )
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = to
    message.set_content(text or "Open this message in an HTML capable client.")
    message.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
        return True
    except Exception as exc:  # pragma: no cover - provider dependent
        logger.error("failed to send '%s' to %s: %s", subject, to, exc)
        return False


def verification_email(username: str, token: str) -> tuple[str, str, str]:
    link = build_action_link("/verify-email", token)
    subject = "Confirm your VibeSpace account"
    html = (
        f"<p>Welcome to VibeSpace, {username}.</p>"
        f"<p>Confirm your email address to unlock uploading and battles:</p>"
        f'<p><a href="{link}">Confirm my email</a></p>'
        f"<p>This link expires in 24 hours.</p>"
    )
    text = f"Confirm your VibeSpace account: {link}"
    return subject, html, text


def password_reset_email(username: str, token: str) -> tuple[str, str, str]:
    link = build_action_link("/reset-password", token)
    subject = "Reset your VibeSpace password"
    html = (
        f"<p>Hi {username},</p>"
        f"<p>Use the link below to choose a new password:</p>"
        f'<p><a href="{link}">Reset my password</a></p>'
        f"<p>If you did not request this, you can ignore this message. The link expires in 60 minutes.</p>"
    )
    text = f"Reset your VibeSpace password: {link}"
    return subject, html, text