import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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


def send_email(to_email: str, subject: str, html_content: str) -> None:
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

    try:
        if insecure_tls:
            context = ssl._create_unverified_context()  # noqa: SLF001
        else:
            context = ssl.create_default_context()
            if ca_file:
                context.load_verify_locations(cafile=ca_file)
        if use_ssl:
            server_cm = smtplib.SMTP_SSL(smtp_host, smtp_port, context=context)
        else:
            server_cm = smtplib.SMTP(smtp_host, smtp_port)

        with server_cm as server:
            server.ehlo()
            if not use_ssl:
                if not server.has_extn("starttls"):
                    raise EmailServiceError("SMTP server does not support STARTTLS. Set SMTP_USE_SSL=true for port 465.")
                server.starttls(context=context)
                server.ehlo()

            if not server.has_extn("auth"):
                raise EmailServiceError("SMTP server did not advertise AUTH; cannot log in.")

            server.login(smtp_user, smtp_password)
            server.sendmail(email_from, to_email, msg.as_string())
    except smtplib.SMTPException as exc:
        logger.exception("SMTP send failed: host=%s port=%s to=%s", smtp_host, smtp_port, to_email)
        raise EmailServiceError("SMTP send failed.") from exc
