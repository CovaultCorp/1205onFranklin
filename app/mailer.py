from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path

from app.config import Settings, get_settings


def send_email(
    *,
    recipient: str,
    subject: str,
    body: str,
    attachments: list[Path] | None = None,
    settings: Settings | None = None,
) -> Path | None:
    settings = settings or get_settings()
    attachments = attachments or []
    if not settings.enable_email:
        preview_dir = settings.export_dir / "email_previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        path = preview_dir / f"email_preview_{subject.lower().replace(' ', '_')[:40]}.html"
        path.write_text(
            f"<h1>{subject}</h1><p><strong>To:</strong> {recipient}</p><pre>{body}</pre>",
            encoding="utf-8",
        )
        return path

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email or settings.admin_email
    message["To"] = recipient
    message.set_content(body)
    for attachment in attachments:
        message.add_attachment(
            attachment.read_bytes(),
            maintype="application",
            subtype="octet-stream",
            filename=attachment.name,
        )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
    return None

