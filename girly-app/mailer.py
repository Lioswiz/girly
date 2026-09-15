"""Girly 🌸 — optional SMTP support for admin password resets.

Python port of smtp.go. Configured via data/smtp.json (see
data/smtp.example.json) or SMTP_* env vars. When absent, resets simply
return the temp password to the admin.
"""

import json
import os
import smtplib
from email.message import EmailMessage


class SMTPConfig:
    def __init__(self, host, port, user, password, from_addr):
        self.host = host
        self.port = int(port or 587)
        self.user = user
        self.password = password
        self.from_addr = from_addr


def load_smtp_config(data_dir):
    # env vars win
    if os.environ.get("SMTP_HOST"):
        return SMTPConfig(
            host=os.environ["SMTP_HOST"],
            port=os.environ.get("SMTP_PORT", 587),
            user=os.environ.get("SMTP_USER", ""),
            password=os.environ.get("SMTP_PASS", ""),
            from_addr=os.environ.get("SMTP_FROM", ""),
        )
    path = os.path.join(data_dir, "smtp.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not cfg.get("host"):
        return None
    return SMTPConfig(
        host=cfg["host"],
        port=cfg.get("port", 587),
        user=cfg.get("user", ""),
        password=cfg.get("password", ""),
        from_addr=cfg.get("from", ""),
    )


def send_reset_email(cfg, to, temp_password):
    """Deliver the temporary password. Returns an error only when configured
    but failed; a None config means "not configured" (caller reports
    emailed=False rather than failing the reset)."""
    if cfg is None:
        return None

    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = cfg.from_addr
    msg["Subject"] = "Your Girly temporary password"
    msg.set_content(
        "Hi,\n\n"
        "An administrator reset your Girly password.\n\n"
        f"Temporary password: {temp_password}\n\n"
        "Sign in at your Girly app and change it from there.\n\n"
        "Stay gentle with yourself,\nThe Girly Team 🌸\n"
    )

    try:
        with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as smtp:
            try:
                smtp.starttls()
            except smtplib.SMTPException:
                pass  # server doesn't offer STARTTLS; try plaintext
            if cfg.user:
                smtp.login(cfg.user, cfg.password)
            smtp.send_message(msg, from_addr=cfg.from_addr, to_addrs=[to])
    except (OSError, smtplib.SMTPException) as err:
        return err
    return None
