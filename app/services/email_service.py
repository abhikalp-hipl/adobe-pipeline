import logging
import os
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import certifi

logger = logging.getLogger(__name__)


class EmailServiceError(Exception):
    pass


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        raise EmailServiceError(f"Missing required environment variable: {name}")
    return str(value).strip()


def _int_from_env(name: str, default: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        if default is None:
            raise EmailServiceError(f"Missing required environment variable: {name}")
        return default
    try:
        return int(str(raw).strip())
    except ValueError as exc:
        raise EmailServiceError(f"Invalid integer value for {name}: {raw!r}") from exc


def _build_tls_context(*, ca_file: str, insecure_tls: bool) -> ssl.SSLContext:
    if insecure_tls:
        logger.warning("SMTP TLS certificate verification is disabled via SMTP_TLS_INSECURE.")
        context = ssl._create_unverified_context()  # noqa: SLF001
    elif ca_file:
        context = ssl.create_default_context(cafile=ca_file)
    else:
        # certifi helps avoid macOS trust-store issues in some Python installs.
        context = ssl.create_default_context(cafile=certifi.where())

    # Enforce modern TLS for SMTP transport security.
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> None:
    """
    Send a single HTML email using SMTP + STARTTLS.

    Required env vars:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM
    """
    smtp_host = _require_env("SMTP_HOST")
    smtp_port = _int_from_env("SMTP_PORT")
    smtp_user = _require_env("SMTP_USER")
    smtp_password = _require_env("SMTP_PASSWORD")
    email_from = _require_env("EMAIL_FROM")
    use_ssl = os.getenv("SMTP_USE_SSL", "").strip().lower() in {"1", "true", "yes", "y"}
    ca_file = os.getenv("SMTP_TLS_CA_FILE", "").strip()
    insecure_tls = os.getenv("SMTP_TLS_INSECURE", "").strip().lower() in {"1", "true", "yes", "y"}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = to_email

    part = MIMEText(html_content, "html")
    msg.attach(part)
    for filename, content_bytes, mime_type in attachments or []:
        main_type, _, sub_type = mime_type.partition("/")
        attachment = MIMEBase(main_type or "application", sub_type or "octet-stream")
        attachment.set_payload(content_bytes)
        encoders.encode_base64(attachment)
        attachment.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        msg.attach(attachment)

    try:
        if insecure_tls:
            context = ssl._create_unverified_context()  # noqa: SLF001
        elif ca_file:
            context = ssl.create_default_context(cafile=ca_file)
        else:
            # python.org macOS builds often lack a usable default CA store; certifi fixes SMTP TLS.
            context = ssl.create_default_context(cafile=certifi.where())
        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user,
            password=smtp_password,
            start_tls=not use_ssl,
            use_tls=use_ssl,
            tls_context=context,
            sender=email_from,
            recipients=[to_email],
        )
    except Exception as exc:
        logger.exception("SMTP send failed: host=%s port=%s to=%s", smtp_host, smtp_port, to_email)
        raise EmailServiceError("SMTP send failed.") from exc
