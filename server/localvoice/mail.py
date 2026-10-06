import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

from .models import OutboxMail
from .util import now

log = logging.getLogger(__name__)


def send_mail(db, to_address, subject, body):
    """Record the mail and deliver it with the configured backend."""
    cfg = current_app.config["LV"]
    m = OutboxMail(to_address=to_address, subject=subject, body=body)
    db.add(m)
    if cfg.MAIL_BACKEND == "smtp" and cfg.SMTP_HOST:
        msg = EmailMessage()
        msg["From"] = cfg.MAIL_FROM
        msg["To"] = to_address
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT, timeout=10) as s:
                s.starttls()
                if cfg.SMTP_USER:
                    s.login(cfg.SMTP_USER, cfg.SMTP_PASSWORD)
                s.send_message(msg)
            m.sent_at = now()
        except Exception:  # delivery failure must not leak whether the account exists
            log.exception("mail delivery failed")
    else:
        log.info("mail queued (log backend) subject=%s", subject)
    return m
